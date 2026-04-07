import type {
  CoreEditDraft,
  CoreProjectRuntimeState,
  CoreScene,
  CoreShot,
  CoreWorkspaceSnapshot,
} from "../services/coreClient";

export type PlannerActionType =
  | "reply_only"
  | "ask_clarification"
  | "update_goal"
  | "set_selection_context"
  | "create_retrieval_request"
  | "inspect_candidates"
  | "apply_patch"
  | "render_preview";

export type RuntimeScope = "global" | "scene" | "shot";
export type RuntimeFactStatus = "confirmed" | "assumed";
export type FeedbackDisposition = "accepted" | "rejected" | "partial" | "unclear";
export type CandidatePoolStatus = "idle" | "ready" | "insufficient" | "failed";
export type ExecutionStatus = "idle" | "running" | "succeeded" | "failed";

export interface GoalConstraintFact {
  key: string;
  value: string;
  status: RuntimeFactStatus;
  sourceTurnId?: string | null;
}

export interface GoalState {
  brief?: string | null;
  audience?: string | null;
  durationTargetMs?: number | null;
  styleHints: string[];
  requiredItems: string[];
  forbiddenItems: string[];
  isPartialEdit: boolean;
  constraints: GoalConstraintFact[];
}

export interface DraftState {
  editDraft: CoreEditDraft | null;
  draftVersion: number | null;
  previewDraftVersion: number | null;
  hasUnrenderedChanges: boolean;
  lastSyncedAt: string | null;
}

export interface SelectionState {
  scope: RuntimeScope;
  selectedSceneId: string | null;
  selectedShotId: string | null;
  lockedSceneFields: Array<NonNullable<CoreScene["locked_fields"]>[number]>;
  lockedShotFields: Array<NonNullable<CoreShot["locked_fields"]>[number]>;
}

export interface RetrievalRequestSummary {
  summary: string;
  query?: string | null;
  targetSceneId?: string | null;
  targetShotId?: string | null;
  requestedAt: string;
}

export interface CandidateClipSummary {
  clipId: string;
  summary: string;
  sourceAssetId: string;
  deepInspected: boolean;
  score?: number | null;
}

export interface RetrievalFailureSummary {
  code: string;
  message: string;
  failedAt: string;
}

export interface RetrievalState {
  latestRequest: RetrievalRequestSummary | null;
  candidatePool: CandidateClipSummary[];
  candidatePoolStatus: CandidatePoolStatus;
  insufficiencyReason?: string | null;
  lastFailure: RetrievalFailureSummary | null;
}

export interface ExecutionRecord {
  action: PlannerActionType;
  summary: string;
  status: Exclude<ExecutionStatus, "idle">;
  startedAt: string;
  completedAt?: string | null;
  targetSceneId?: string | null;
  targetShotId?: string | null;
}

export interface ExecutionState {
  status: ExecutionStatus;
  currentAction: PlannerActionType | null;
  lastPatchSummary?: string | null;
  recentActions: ExecutionRecord[];
}

export interface ConfirmedConversationFact {
  key: string;
  value: string;
  sourceTurnId?: string | null;
}

export interface OpenConversationQuestion {
  question: string;
  raisedBy: "user" | "agent";
  sourceTurnId?: string | null;
}

export interface ConversationState {
  confirmedFacts: ConfirmedConversationFact[];
  openQuestions: OpenConversationQuestion[];
  latestFeedback: {
    disposition: FeedbackDisposition;
    summary: string;
    sourceTurnId?: string | null;
  } | null;
  clarificationRequired: boolean;
}

export interface SessionRuntimeState {
  sessionId: string;
  projectId: string | null;
  createdAt: string;
  updatedAt: string;
  goal: GoalState;
  draft: DraftState;
  selection: SelectionState;
  retrieval: RetrievalState;
  execution: ExecutionState;
  conversation: ConversationState;
}

export function createEmptySessionRuntimeState(now: string = new Date().toISOString()): SessionRuntimeState {
  return {
    sessionId: `session_${now}`,
    projectId: null,
    createdAt: now,
    updatedAt: now,
    goal: {
      brief: null,
      audience: null,
      durationTargetMs: null,
      styleHints: [],
      requiredItems: [],
      forbiddenItems: [],
      isPartialEdit: false,
      constraints: [],
    },
    draft: {
      editDraft: null,
      draftVersion: null,
      previewDraftVersion: null,
      hasUnrenderedChanges: false,
      lastSyncedAt: null,
    },
    selection: {
      scope: "global",
      selectedSceneId: null,
      selectedShotId: null,
      lockedSceneFields: [],
      lockedShotFields: [],
    },
    retrieval: {
      latestRequest: null,
      candidatePool: [],
      candidatePoolStatus: "idle",
      insufficiencyReason: null,
      lastFailure: null,
    },
    execution: {
      status: "idle",
      currentAction: null,
      lastPatchSummary: null,
      recentActions: [],
    },
    conversation: {
      confirmedFacts: [],
      openQuestions: [],
      latestFeedback: null,
      clarificationRequired: false,
    },
  };
}

export function syncRuntimeStateFromWorkspace(
  state: SessionRuntimeState,
  workspace: CoreWorkspaceSnapshot,
  now: string = new Date().toISOString(),
): SessionRuntimeState {
  const coreRuntimeState = workspace.runtime_state;
  const selectedSceneId =
    coreRuntimeState.focus_state.scene_id ?? workspace.edit_draft.selected_scene_id ?? null;
  const selectedShotId =
    coreRuntimeState.focus_state.shot_id ?? workspace.edit_draft.selected_shot_id ?? null;
  const selectedScene = workspace.edit_draft.scenes?.find((scene) => scene.id === selectedSceneId) ?? null;
  const selectedShot = workspace.edit_draft.shots.find((shot) => shot.id === selectedShotId) ?? null;
  const candidatePool = buildCandidatePool(workspace);

  return {
    ...state,
    projectId: workspace.project.id,
    updatedAt: now,
    goal: {
      ...state.goal,
      brief: coreRuntimeState.goal_state.brief ?? null,
      constraints: coreRuntimeState.goal_state.constraints.map((value, index) => ({
        key: `constraint_${index}`,
        value,
        status: "confirmed",
      })),
    },
    draft: {
      ...state.draft,
      editDraft: workspace.edit_draft,
      draftVersion: workspace.edit_draft.version,
      lastSyncedAt: now,
    },
    selection: {
      scope:
        coreRuntimeState.focus_state.scope_type === "shot"
          ? "shot"
          : coreRuntimeState.focus_state.scope_type === "scene"
          ? "scene"
          : "global",
      selectedSceneId,
      selectedShotId,
      lockedSceneFields: selectedScene?.locked_fields ?? [],
      lockedShotFields: selectedShot?.locked_fields ?? [],
    },
    retrieval: {
      latestRequest: coreRuntimeState.retrieval_state.last_query
        ? {
            summary: coreRuntimeState.retrieval_state.last_query,
            query: coreRuntimeState.retrieval_state.last_query,
            targetSceneId: selectedSceneId,
            targetShotId: selectedShotId,
            requestedAt: coreRuntimeState.retrieval_state.updated_at ?? now,
          }
        : null,
      candidatePool,
      candidatePoolStatus: deriveCandidatePoolStatus(coreRuntimeState, candidatePool),
      insufficiencyReason: coreRuntimeState.retrieval_state.blocking_reason ?? null,
      lastFailure: coreRuntimeState.execution_state.last_error
        ? {
            code: String(coreRuntimeState.execution_state.last_error.code ?? "runtime_error"),
            message: String(coreRuntimeState.execution_state.last_error.message ?? "runtime_error"),
            failedAt: coreRuntimeState.execution_state.updated_at ?? now,
          }
        : null,
    },
    execution: {
      ...state.execution,
      status: mapExecutionStatus(coreRuntimeState.execution_state.agent_run_state),
      currentAction: mapCurrentAction(coreRuntimeState.execution_state.last_tool_name),
      lastPatchSummary:
        coreRuntimeState.execution_state.last_tool_name === "patch"
          ? "server_runtime_patch_applied"
          : state.execution.lastPatchSummary,
    },
    conversation: {
      confirmedFacts: coreRuntimeState.conversation_state.confirmed_facts.map((value, index) => ({
        key: `fact_${index}`,
        value,
      })),
      openQuestions: coreRuntimeState.conversation_state.pending_questions.map((question) => ({
        question,
        raisedBy: "agent",
      })),
      latestFeedback: {
        disposition: mapFeedbackDisposition(coreRuntimeState.conversation_state.latest_user_feedback),
        summary: coreRuntimeState.conversation_state.latest_user_feedback,
      },
      clarificationRequired: coreRuntimeState.conversation_state.pending_questions.length > 0,
    },
  };
}

export function updateSelectionState(
  state: SessionRuntimeState,
  input: {
    scope: RuntimeScope;
    selectedSceneId?: string | null;
    selectedShotId?: string | null;
  },
  now: string = new Date().toISOString(),
): SessionRuntimeState {
  const editDraft = state.draft.editDraft;
  const selectedSceneId = input.scope === "global" ? null : input.selectedSceneId ?? null;
  const selectedShotId = input.scope === "shot" ? input.selectedShotId ?? null : null;
  const selectedScene = editDraft?.scenes?.find((scene) => scene.id === selectedSceneId) ?? null;
  const selectedShot = editDraft?.shots.find((shot) => shot.id === selectedShotId) ?? null;

  return {
    ...state,
    updatedAt: now,
    selection: {
      scope: input.scope,
      selectedSceneId,
      selectedShotId,
      lockedSceneFields: selectedScene?.locked_fields ?? [],
      lockedShotFields: selectedShot?.locked_fields ?? [],
    },
  };
}

export function recordExecutionAction(
  state: SessionRuntimeState,
  record: Omit<ExecutionRecord, "startedAt"> & { startedAt?: string },
  now: string = new Date().toISOString(),
): SessionRuntimeState {
  const startedAt = record.startedAt ?? now;
  const recentActions = [
    {
      ...record,
      startedAt,
    },
    ...state.execution.recentActions,
  ].slice(0, 20);

  return {
    ...state,
    updatedAt: now,
    execution: {
      ...state.execution,
      status: record.status,
      currentAction: record.status === "running" ? record.action : null,
      recentActions,
    },
  };
}

function buildCandidatePool(workspace: CoreWorkspaceSnapshot): CandidateClipSummary[] {
  const candidateIds = workspace.runtime_state.retrieval_state.candidate_clip_ids;
  const clipsById = new Map(workspace.edit_draft.clips.map((clip) => [clip.id, clip]));
  return candidateIds
    .map((clipId): CandidateClipSummary | null => {
      const clip = clipsById.get(clipId);
      if (!clip) {
        return null;
      }
      return {
        clipId,
        summary: clip.visual_desc,
        sourceAssetId: clip.asset_id,
        deepInspected: false,
        score: clip.confidence ?? null,
      };
    })
    .filter((item): item is CandidateClipSummary => item !== null);
}

function deriveCandidatePoolStatus(
  runtimeState: CoreProjectRuntimeState,
  candidatePool: CandidateClipSummary[],
): CandidatePoolStatus {
  if (candidatePool.length > 0) {
    return "ready";
  }
  if (!runtimeState.retrieval_state.retrieval_ready) {
    return "insufficient";
  }
  return "idle";
}

function mapExecutionStatus(agentRunState: CoreProjectRuntimeState["execution_state"]["agent_run_state"]): ExecutionStatus {
  if (agentRunState === "planning" || agentRunState === "executing_tool") {
    return "running";
  }
  if (agentRunState === "failed") {
    return "failed";
  }
  return "idle";
}

function mapCurrentAction(lastToolName: string | null | undefined): PlannerActionType | null {
  if (lastToolName === "retrieve") {
    return "create_retrieval_request";
  }
  if (lastToolName === "inspect") {
    return "inspect_candidates";
  }
  if (lastToolName === "patch") {
    return "apply_patch";
  }
  if (lastToolName === "preview") {
    return "render_preview";
  }
  return null;
}

function mapFeedbackDisposition(
  feedback: CoreProjectRuntimeState["conversation_state"]["latest_user_feedback"],
): FeedbackDisposition {
  if (feedback === "approve") {
    return "accepted";
  }
  if (feedback === "reject") {
    return "rejected";
  }
  if (feedback === "revise") {
    return "partial";
  }
  return "unclear";
}
