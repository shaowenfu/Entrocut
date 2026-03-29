import type { CoreClip, CoreEditDraft, CoreScene, CoreShot } from "../services/coreClient";
import type {
  CandidateClipSummary,
  PlannerActionType,
  SessionRuntimeState,
} from "./sessionRuntimeState";

export interface ActionContextPacket {
  project_id: string;
  session_id: string;
  action_type: PlannerActionType;
  assembled_at: string;

  task_summary: string;
  goal_summary: string;

  scope: "global" | "scene" | "shot";
  selected_scene_id?: string | null;
  selected_shot_id?: string | null;
  locked_fields?: string[];

  draft_version?: number | null;
  draft_excerpt?: unknown;

  candidate_excerpt?: unknown;
  recent_failures?: string[];
  recent_actions?: string[];

  confirmed_facts?: Array<{
    key: string;
    value: string;
  }>;
  open_questions?: string[];

  available_tools: string[];
}

export interface ContextAssemblyMeta {
  action_type: PlannerActionType;
  used_sections: string[];
  omitted_sections: string[];
  warnings: string[];
  assembled_at: string;
}

export type ContextAssemblyErrorCode =
  | "RUNTIME_STATE_MISSING"
  | "ACTION_TYPE_INVALID"
  | "REQUIRED_FACT_MISSING"
  | "EVIDENCE_REF_INVALID"
  | "ASSEMBLY_BUDGET_EXCEEDED";

export interface ContextAssemblyError {
  code: ContextAssemblyErrorCode;
  message: string;
  action_type?: PlannerActionType;
  missing_fields?: string[];
}

export interface ContextAssemblyInput {
  actionType: PlannerActionType;
  runtimeState: SessionRuntimeState | null;
  assembledAt?: string;
  candidateLimit?: number;
  actionHistoryLimit?: number;
  includeRecentFailures?: boolean;
}

export type ContextAssemblyResult =
  | {
      ok: true;
      packet: ActionContextPacket;
      assemblyMeta: ContextAssemblyMeta;
    }
  | {
      ok: false;
      error: ContextAssemblyError;
    };

const DEFAULT_CANDIDATE_LIMIT = 5;
const DEFAULT_ACTION_HISTORY_LIMIT = 5;

const AVAILABLE_TOOLS_BY_ACTION: Record<PlannerActionType, string[]> = {
  reply_only: ["read"],
  ask_clarification: ["read"],
  update_goal: ["read"],
  set_selection_context: ["read"],
  create_retrieval_request: ["read", "retrieve"],
  inspect_candidates: ["read", "inspect"],
  apply_patch: ["read", "patch", "preview"],
  render_preview: ["read", "preview"],
};

export function assembleActionContext(input: ContextAssemblyInput): ContextAssemblyResult {
  if (!input.runtimeState) {
    return {
      ok: false,
      error: {
        code: "RUNTIME_STATE_MISSING",
        message: "runtime_state_missing",
        action_type: input.actionType,
      },
    };
  }

  const runtimeState = input.runtimeState;
  const assembledAt = input.assembledAt ?? new Date().toISOString();
  const candidateLimit = input.candidateLimit ?? DEFAULT_CANDIDATE_LIMIT;
  const actionHistoryLimit = input.actionHistoryLimit ?? DEFAULT_ACTION_HISTORY_LIMIT;
  const warnings: string[] = [];
  const omittedSections: string[] = [];

  if (!AVAILABLE_TOOLS_BY_ACTION[input.actionType]) {
    return {
      ok: false,
      error: {
        code: "ACTION_TYPE_INVALID",
        message: "action_type_invalid",
        action_type: input.actionType,
      },
    };
  }

  const taskSummary = buildTaskSummary(runtimeState, input.actionType);
  const goalSummary = buildGoalSummary(runtimeState);
  const lockedFields = [
    ...runtimeState.selection.lockedSceneFields,
    ...runtimeState.selection.lockedShotFields,
  ];

  const draftExcerptResult = buildDraftExcerpt(runtimeState, input.actionType);
  if (!draftExcerptResult.ok) {
    return {
      ok: false,
      error: {
        code: "REQUIRED_FACT_MISSING",
        message: draftExcerptResult.message,
        action_type: input.actionType,
        missing_fields: draftExcerptResult.missingFields,
      },
    };
  }

  const candidateExcerpt = buildCandidateExcerpt(runtimeState, input.actionType, candidateLimit);
  if (candidateExcerpt === null) {
    omittedSections.push("candidate_excerpt");
  }

  const recentFailures =
    input.includeRecentFailures === false ? [] : buildRecentFailures(runtimeState, input.actionType);
  if (recentFailures.length === 0) {
    omittedSections.push("recent_failures");
  }

  const recentActions = buildRecentActions(runtimeState, input.actionType, actionHistoryLimit);
  if (recentActions.length === 0) {
    omittedSections.push("recent_actions");
  }

  const confirmedFacts = runtimeState.conversation.confirmedFacts.slice(0, 8).map((fact) => ({
    key: fact.key,
    value: fact.value,
  }));
  if (confirmedFacts.length === 0) {
    omittedSections.push("confirmed_facts");
  }

  const openQuestions = runtimeState.conversation.openQuestions.slice(0, 5).map((item) => item.question);
  if (openQuestions.length === 0) {
    omittedSections.push("open_questions");
  }

  if (!runtimeState.projectId) {
    warnings.push("project_id_missing");
  }
  if (runtimeState.selection.scope !== "global" && !runtimeState.draft.editDraft) {
    warnings.push("selection_without_draft");
  }

  return {
    ok: true,
    packet: {
      project_id: runtimeState.projectId ?? "",
      session_id: runtimeState.sessionId,
      action_type: input.actionType,
      assembled_at: assembledAt,
      task_summary: taskSummary,
      goal_summary: goalSummary,
      scope: runtimeState.selection.scope,
      selected_scene_id: runtimeState.selection.selectedSceneId,
      selected_shot_id: runtimeState.selection.selectedShotId,
      locked_fields: lockedFields,
      draft_version: runtimeState.draft.draftVersion,
      draft_excerpt: draftExcerptResult.value,
      candidate_excerpt: candidateExcerpt ?? undefined,
      recent_failures: recentFailures.length > 0 ? recentFailures : undefined,
      recent_actions: recentActions.length > 0 ? recentActions : undefined,
      confirmed_facts: confirmedFacts.length > 0 ? confirmedFacts : undefined,
      open_questions: openQuestions.length > 0 ? openQuestions : undefined,
      available_tools: AVAILABLE_TOOLS_BY_ACTION[input.actionType],
    },
    assemblyMeta: {
      action_type: input.actionType,
      used_sections: [
        "action_frame",
        "goal_frame",
        "scope_frame",
        "draft_frame",
        ...(candidateExcerpt ? ["evidence_frame"] : []),
        "tool_frame",
      ],
      omitted_sections: omittedSections,
      warnings,
      assembled_at: assembledAt,
    },
  };
}

function buildTaskSummary(runtimeState: SessionRuntimeState, actionType: PlannerActionType): string {
  const selection =
    runtimeState.selection.scope === "global"
      ? "global"
      : runtimeState.selection.scope === "scene"
      ? `scene:${runtimeState.selection.selectedSceneId ?? "unknown"}`
      : `shot:${runtimeState.selection.selectedShotId ?? "unknown"}`;
  const goal = runtimeState.goal.brief?.trim() || "unspecified_goal";
  return `${actionType} for ${selection} under goal ${goal}`;
}

function buildGoalSummary(runtimeState: SessionRuntimeState): string {
  const parts: string[] = [];
  if (runtimeState.goal.brief?.trim()) {
    parts.push(runtimeState.goal.brief.trim());
  }
  if (runtimeState.goal.audience?.trim()) {
    parts.push(`audience=${runtimeState.goal.audience.trim()}`);
  }
  if (typeof runtimeState.goal.durationTargetMs === "number") {
    parts.push(`duration_target_ms=${runtimeState.goal.durationTargetMs}`);
  }
  if (runtimeState.goal.styleHints.length > 0) {
    parts.push(`style=${runtimeState.goal.styleHints.join(",")}`);
  }
  if (runtimeState.goal.requiredItems.length > 0) {
    parts.push(`must=${runtimeState.goal.requiredItems.join(",")}`);
  }
  if (runtimeState.goal.forbiddenItems.length > 0) {
    parts.push(`forbid=${runtimeState.goal.forbiddenItems.join(",")}`);
  }
  if (runtimeState.goal.isPartialEdit) {
    parts.push("partial_edit=true");
  }
  return parts.length > 0 ? parts.join(" | ") : "goal_not_confirmed";
}

function buildDraftExcerpt(
  runtimeState: SessionRuntimeState,
  actionType: PlannerActionType,
):
  | { ok: true; value: unknown }
  | { ok: false; message: string; missingFields: string[] } {
  const draft = runtimeState.draft.editDraft;
  if (!draft) {
    if (actionType === "reply_only" || actionType === "ask_clarification" || actionType === "update_goal") {
      return { ok: true, value: null };
    }
    return {
      ok: false,
      message: "draft_missing_for_action",
      missingFields: ["draft.editDraft"],
    };
  }

  if (runtimeState.selection.scope === "shot") {
    const shot = draft.shots.find((item) => item.id === runtimeState.selection.selectedShotId);
    if (!shot) {
      return {
        ok: false,
        message: "selected_shot_missing_in_draft",
        missingFields: ["selection.selectedShotId"],
      };
    }
    const clip = draft.clips.find((item) => item.id === shot.clip_id) ?? null;
    return {
      ok: true,
      value: {
        kind: "shot",
        shot: toShotExcerpt(shot, clip),
      },
    };
  }

  if (runtimeState.selection.scope === "scene") {
    const scene = draft.scenes?.find((item) => item.id === runtimeState.selection.selectedSceneId) ?? null;
    if (!scene) {
      return {
        ok: false,
        message: "selected_scene_missing_in_draft",
        missingFields: ["selection.selectedSceneId"],
      };
    }
    return {
      ok: true,
      value: {
        kind: "scene",
        scene: toSceneExcerpt(draft, scene),
      },
    };
  }

  return {
    ok: true,
    value: {
      kind: "global",
      summary: {
        asset_count: draft.assets.length,
        clip_count: draft.clips.length,
        shot_count: draft.shots.length,
        scene_count: draft.scenes?.length ?? 0,
        status: draft.status,
      },
    },
  };
}

function toShotExcerpt(shot: CoreShot, clip: CoreClip | null) {
  return {
    id: shot.id,
    clip_id: shot.clip_id,
    order: shot.order,
    intent: shot.intent ?? null,
    note: shot.note ?? null,
    source_in_ms: shot.source_in_ms,
    source_out_ms: shot.source_out_ms,
    locked_fields: shot.locked_fields ?? [],
    clip_summary: clip
      ? {
          visual_desc: clip.visual_desc,
          semantic_tags: clip.semantic_tags,
          asset_id: clip.asset_id,
        }
      : null,
  };
}

function toSceneExcerpt(draft: CoreEditDraft, scene: CoreScene) {
  const shotsById = new Map(draft.shots.map((shot) => [shot.id, shot]));
  const clipsById = new Map(draft.clips.map((clip) => [clip.id, clip]));
  const shotExcerpts = scene.shot_ids
    .map((shotId) => shotsById.get(shotId))
    .filter((shot): shot is CoreShot => Boolean(shot))
    .sort((left, right) => left.order - right.order)
    .map((shot) => toShotExcerpt(shot, clipsById.get(shot.clip_id) ?? null));

  return {
    id: scene.id,
    label: scene.label ?? null,
    intent: scene.intent ?? null,
    enabled: scene.enabled,
    order: scene.order,
    locked_fields: scene.locked_fields ?? [],
    shots: shotExcerpts,
  };
}

function buildCandidateExcerpt(
  runtimeState: SessionRuntimeState,
  actionType: PlannerActionType,
  candidateLimit: number,
): unknown | null {
  const shouldInclude =
    actionType === "create_retrieval_request" ||
    actionType === "inspect_candidates" ||
    actionType === "apply_patch";
  if (!shouldInclude) {
    return null;
  }

  const candidates = runtimeState.retrieval.candidatePool.slice(0, candidateLimit).map(toCandidateExcerpt);
  if (candidates.length === 0 && !runtimeState.retrieval.latestRequest) {
    return null;
  }

  return {
    latest_request: runtimeState.retrieval.latestRequest,
    status: runtimeState.retrieval.candidatePoolStatus,
    insufficiency_reason: runtimeState.retrieval.insufficiencyReason ?? null,
    candidates,
  };
}

function toCandidateExcerpt(candidate: CandidateClipSummary) {
  return {
    clip_id: candidate.clipId,
    asset_id: candidate.sourceAssetId,
    summary: candidate.summary,
    deep_inspected: candidate.deepInspected,
    score: candidate.score ?? null,
  };
}

function buildRecentFailures(runtimeState: SessionRuntimeState, actionType: PlannerActionType): string[] {
  const failures: string[] = [];
  if (
    (actionType === "create_retrieval_request" ||
      actionType === "inspect_candidates" ||
      actionType === "apply_patch") &&
    runtimeState.retrieval.lastFailure
  ) {
    failures.push(
      `${runtimeState.retrieval.lastFailure.code}:${runtimeState.retrieval.lastFailure.message}`,
    );
  }
  return failures;
}

function buildRecentActions(
  runtimeState: SessionRuntimeState,
  actionType: PlannerActionType,
  limit: number,
): string[] {
  const relatedActions = runtimeState.execution.recentActions.filter((record) => {
    if (actionType === "create_retrieval_request") {
      return (
        record.action === "create_retrieval_request" ||
        record.action === "inspect_candidates" ||
        record.action === "apply_patch"
      );
    }
    if (actionType === "apply_patch") {
      return record.action === "apply_patch" || record.action === "inspect_candidates";
    }
    return true;
  });

  return relatedActions.slice(0, limit).map((record) => `${record.action}:${record.summary}`);
}
