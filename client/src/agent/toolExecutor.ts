import type { ToolExecutionResult, ToolExecutor } from "./executionLoop";
import type {
  EditDraftPatchPayload,
  PlannerOutput,
  RetrievalRequestPayload,
} from "./plannerOutput";
import type { SessionRuntimeState } from "./sessionRuntimeState";

export function createLocalToolExecutor(): ToolExecutor {
  return {
    execute({ plannerOutput, runtimeState }) {
      switch (plannerOutput.header.action) {
        case "create_retrieval_request":
          return executeRetrieval(plannerOutput, runtimeState);
        case "inspect_candidates":
          return executeInspect(plannerOutput, runtimeState);
        case "apply_patch":
          return executePatch(plannerOutput, runtimeState);
        case "render_preview":
          return executePreview(plannerOutput, runtimeState);
        default:
          throw new Error(`unsupported_tool_action:${plannerOutput.header.action}`);
      }
    },
  };
}

function executeRetrieval(plannerOutput: PlannerOutput, runtimeState: SessionRuntimeState): ToolExecutionResult {
  if (plannerOutput.payload.kind !== "retrieval_request") {
    throw new Error("retrieval_payload_mismatch");
  }

  const draft = runtimeState.draft.editDraft;
  if (!draft) {
    throw new Error("draft_missing_for_retrieval");
  }

  const candidates = rankClips(draft.clips, plannerOutput.payload.request).slice(
    0,
    plannerOutput.payload.request.policy.rerank_top_k,
  );

  return {
    kind: "tool",
    summary: `retrieved_${candidates.length}_candidates`,
    nextRuntimeState: {
      ...runtimeState,
      updatedAt: new Date().toISOString(),
      retrieval: {
        ...runtimeState.retrieval,
        latestRequest: {
          summary: plannerOutput.payload.request.intent,
          query: plannerOutput.payload.request.query,
          targetSceneId: plannerOutput.payload.request.target_scene_id,
          targetShotId: plannerOutput.payload.request.target_shot_id,
          requestedAt: plannerOutput.payload.request.requested_at,
        },
        candidatePool: candidates,
        candidatePoolStatus: candidates.length > 0 ? "ready" : "insufficient",
        insufficiencyReason: candidates.length > 0 ? null : "no_candidate_match",
        lastFailure:
          candidates.length > 0
            ? null
            : {
                code: "CANDIDATES_INSUFFICIENT",
                message: "no_candidate_match",
                failedAt: new Date().toISOString(),
              },
      },
    },
    shouldContinue: candidates.length > 0,
    waitForUser: candidates.length === 0,
  };
}

function executeInspect(plannerOutput: PlannerOutput, runtimeState: SessionRuntimeState): ToolExecutionResult {
  if (plannerOutput.payload.kind !== "candidate_inspection") {
    throw new Error("inspect_payload_mismatch");
  }

  const rankedPool = [...runtimeState.retrieval.candidatePool]
    .sort((left, right) => (right.score ?? 0) - (left.score ?? 0))
    .map((candidate, index) => ({
      ...candidate,
      deepInspected: index < 3,
    }));

  return {
    kind: "tool",
    summary: `inspected_${rankedPool.length}_candidates`,
    nextRuntimeState: {
      ...runtimeState,
      updatedAt: new Date().toISOString(),
      retrieval: {
        ...runtimeState.retrieval,
        candidatePool: rankedPool,
        candidatePoolStatus: rankedPool.length > 0 ? "ready" : "insufficient",
      },
    },
    shouldContinue: rankedPool.length > 0,
    waitForUser: rankedPool.length === 0,
  };
}

function executePatch(plannerOutput: PlannerOutput, runtimeState: SessionRuntimeState): ToolExecutionResult {
  if (plannerOutput.payload.kind !== "edit_draft_patch") {
    throw new Error("patch_payload_mismatch");
  }

  const draft = runtimeState.draft.editDraft;
  if (!draft) {
    throw new Error("draft_missing_for_patch");
  }

  const nextDraft = applyPatchToDraft(draft, plannerOutput.payload.patch);

  return {
    kind: "tool",
    summary: `patch_applied_${plannerOutput.payload.patch.operations.length}_ops`,
    nextRuntimeState: {
      ...runtimeState,
      updatedAt: new Date().toISOString(),
      draft: {
        ...runtimeState.draft,
        editDraft: nextDraft,
        draftVersion: nextDraft.version,
        hasUnrenderedChanges: true,
      },
      execution: {
        ...runtimeState.execution,
        lastPatchSummary: plannerOutput.payload.patch.operations.map((op) => op.summary).join("; "),
      },
    },
    shouldContinue: true,
    waitForUser: false,
  };
}

function executePreview(plannerOutput: PlannerOutput, runtimeState: SessionRuntimeState): ToolExecutionResult {
  if (plannerOutput.payload.kind !== "preview_request") {
    throw new Error("preview_payload_mismatch");
  }

  return {
    kind: "tool",
    summary: `preview_ready_v${plannerOutput.payload.request.draft_version}`,
    nextRuntimeState: {
      ...runtimeState,
      updatedAt: new Date().toISOString(),
      draft: {
        ...runtimeState.draft,
        previewDraftVersion: plannerOutput.payload.request.draft_version,
        hasUnrenderedChanges: false,
      },
    },
    shouldContinue: false,
    waitForUser: true,
  };
}

function rankClips(
  clips: NonNullable<SessionRuntimeState["draft"]["editDraft"]>["clips"],
  request: RetrievalRequestPayload,
) {
  const queryTokens = tokenize(request.query);
  return clips
    .map((clip) => {
      const haystack = `${clip.visual_desc} ${clip.semantic_tags.join(" ")}`.toLowerCase();
      const lexicalScore = queryTokens.reduce((score, token) => score + (haystack.includes(token) ? 1 : 0), 0);
      const baseScore = typeof clip.confidence === "number" ? clip.confidence : 0;
      return {
        clipId: clip.id,
        summary: clip.visual_desc,
        sourceAssetId: clip.asset_id,
        deepInspected: false,
        score: lexicalScore + baseScore,
      };
    })
    .sort((left, right) => (right.score ?? 0) - (left.score ?? 0));
}

function tokenize(input: string): string[] {
  return input
    .toLowerCase()
    .split(/[^a-z0-9_]+/)
    .map((item) => item.trim())
    .filter((item) => item.length >= 3);
}

function applyPatchToDraft(
  draft: NonNullable<SessionRuntimeState["draft"]["editDraft"]>,
  patch: EditDraftPatchPayload,
) {
  const nextShots = draft.shots.map((shot) => ({ ...shot }));

  for (const operation of patch.operations) {
    if (operation.type === "replace_shot" && operation.target_shot_id && operation.clip_id) {
      const targetShot = nextShots.find((shot) => shot.id === operation.target_shot_id);
      if (targetShot) {
        targetShot.clip_id = operation.clip_id;
      }
      continue;
    }
    if (
      operation.type === "trim_shot" &&
      operation.target_shot_id &&
      typeof operation.source_in_ms === "number" &&
      typeof operation.source_out_ms === "number"
    ) {
      const targetShot = nextShots.find((shot) => shot.id === operation.target_shot_id);
      if (targetShot) {
        targetShot.source_in_ms = operation.source_in_ms;
        targetShot.source_out_ms = operation.source_out_ms;
      }
    }
  }

  return {
    ...draft,
    shots: nextShots,
    version: draft.version + 1,
    updated_at: new Date().toISOString(),
  };
}
