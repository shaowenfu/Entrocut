import type {
  CoreEditDraft,
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
  const selectedSceneId = workspace.edit_draft.selected_scene_id ?? null;
  const selectedShotId = workspace.edit_draft.selected_shot_id ?? null;
  const selectedScene = workspace.edit_draft.scenes?.find((scene) => scene.id === selectedSceneId) ?? null;
  const selectedShot = workspace.edit_draft.shots.find((shot) => shot.id === selectedShotId) ?? null;

  return {
    ...state,
    projectId: workspace.project.id,
    updatedAt: now,
    draft: {
      ...state.draft,
      editDraft: workspace.edit_draft,
      draftVersion: workspace.edit_draft.version,
      lastSyncedAt: now,
    },
    selection: {
      scope: selectedShotId ? "shot" : selectedSceneId ? "scene" : "global",
      selectedSceneId,
      selectedShotId,
      lockedSceneFields: selectedScene?.locked_fields ?? [],
      lockedShotFields: selectedShot?.locked_fields ?? [],
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
