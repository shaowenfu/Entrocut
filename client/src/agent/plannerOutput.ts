import type { PlannerActionType, RuntimeScope } from "./sessionRuntimeState";

export interface RetrievalRequestPayload {
  project_id: string;
  session_id?: string | null;
  intent: string;
  query: string;
  scope: RuntimeScope;
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  constraints?: Record<string, unknown>;
  preferences?: Record<string, unknown>;
  policy: {
    broad_top_k: number;
    rerank_top_k: number;
    allow_query_relaxation: boolean;
    allow_constraint_relaxation: boolean;
  };
  requested_at: string;
}

export interface InspectToolRequestPayload {
  project_id: string;
  session_id?: string | null;
  mode: "rank" | "compare" | "choose" | "verify";
  question: string;
  scope: RuntimeScope;
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  candidates: Array<{
    clip_id: string;
    asset_id: string;
    summary: string;
    score?: number | null;
  }>;
  require_visual_reasoning?: boolean;
  requested_at: string;
}

export interface EditDraftPatchPayload {
  project_id: string;
  draft_id: string;
  base_version: number;
  scope: RuntimeScope;
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  operations: Array<{
    op_id: string;
    type:
      | "insert_shot"
      | "remove_shot"
      | "replace_shot"
      | "trim_shot"
      | "move_shot"
      | "group_scene"
      | "ungroup_scene"
      | "lock_fields";
    target_scene_id?: string | null;
    target_shot_id?: string | null;
    after_shot_id?: string | null;
    clip_id?: string | null;
    source_in_ms?: number | null;
    source_out_ms?: number | null;
    shot_ids?: string[];
    locked_fields?: string[];
    summary: string;
  }>;
  created_at: string;
}

export interface PreviewToolRequestPayload {
  project_id: string;
  draft_id: string;
  draft_version: number;
  scope: RuntimeScope;
  scene_id?: string | null;
  shot_id?: string | null;
  options?: {
    quality?: "draft" | "standard";
    muted?: boolean;
  };
  requested_at: string;
}

export interface PlannerDecisionHeader {
  action: PlannerActionType;
  ready: boolean;
  reason: string;
}

export type PlannerDecisionPayload =
  | { kind: "none" }
  | { kind: "clarification"; questions: string[] }
  | { kind: "goal_update"; changes: Record<string, unknown> }
  | {
      kind: "selection_update";
      scope: RuntimeScope;
      scene_id?: string | null;
      shot_id?: string | null;
    }
  | { kind: "retrieval_request"; request: RetrievalRequestPayload }
  | { kind: "candidate_inspection"; request: InspectToolRequestPayload }
  | { kind: "edit_draft_patch"; patch: EditDraftPatchPayload }
  | { kind: "preview_request"; request: PreviewToolRequestPayload };

export interface PlannerDecisionMeta {
  target_scope: RuntimeScope;
  target_scene_id?: string | null;
  target_shot_id?: string | null;
  warnings?: string[];
}

export interface PlannerOutput {
  header: PlannerDecisionHeader;
  payload: PlannerDecisionPayload;
  meta: PlannerDecisionMeta;
}

export type PlannerOutputValidationErrorCode =
  | "MISSING_HEADER"
  | "MISSING_PAYLOAD"
  | "MISSING_META"
  | "INVALID_ACTION"
  | "ACTION_PAYLOAD_MISMATCH"
  | "INVALID_READY_REASON"
  | "INVALID_TARGET_SCOPE";

export interface PlannerOutputValidationError {
  code: PlannerOutputValidationErrorCode;
  message: string;
}

const EXPECTED_PAYLOAD_KIND_BY_ACTION: Record<PlannerActionType, PlannerDecisionPayload["kind"]> = {
  reply_only: "none",
  ask_clarification: "clarification",
  update_goal: "goal_update",
  set_selection_context: "selection_update",
  create_retrieval_request: "retrieval_request",
  inspect_candidates: "candidate_inspection",
  apply_patch: "edit_draft_patch",
  render_preview: "preview_request",
};

const VALID_ACTIONS = new Set<PlannerActionType>(Object.keys(EXPECTED_PAYLOAD_KIND_BY_ACTION) as PlannerActionType[]);
const VALID_SCOPES = new Set<RuntimeScope>(["global", "scene", "shot"]);

export function validatePlannerOutput(output: PlannerOutput): PlannerOutputValidationError[] {
  const errors: PlannerOutputValidationError[] = [];

  if (!output.header) {
    errors.push({ code: "MISSING_HEADER", message: "missing_header" });
    return errors;
  }
  if (!output.payload) {
    errors.push({ code: "MISSING_PAYLOAD", message: "missing_payload" });
    return errors;
  }
  if (!output.meta) {
    errors.push({ code: "MISSING_META", message: "missing_meta" });
    return errors;
  }

  if (!output.header.reason || output.header.reason.trim().length === 0) {
    errors.push({ code: "INVALID_READY_REASON", message: "header_reason_required" });
  }

  if (!VALID_ACTIONS.has(output.header.action)) {
    errors.push({
      code: "INVALID_ACTION",
      message: `invalid_action_${String(output.header.action)}`,
    });
    return errors;
  }

  const expectedPayloadKind = EXPECTED_PAYLOAD_KIND_BY_ACTION[output.header.action];
  if (output.payload.kind !== expectedPayloadKind) {
    errors.push({
      code: "ACTION_PAYLOAD_MISMATCH",
      message: `action_${output.header.action}_expects_${expectedPayloadKind}_got_${output.payload.kind}`,
    });
  }

  if (!VALID_SCOPES.has(output.meta.target_scope)) {
    errors.push({
      code: "INVALID_TARGET_SCOPE",
      message: "invalid_target_scope",
    });
  }

  errors.push(...validatePayloadConsistency(output));

  return errors;
}

export function isPlannerOutputExecutable(output: PlannerOutput): boolean {
  return output.header.ready && validatePlannerOutput(output).length === 0;
}

export function normalizePlannerOutput(input: unknown): PlannerOutput {
  const raw = input as Record<string, unknown>;
  const header = (raw.header ?? {}) as Record<string, unknown>;
  const payload = (raw.payload ?? {}) as Record<string, unknown>;
  const meta = (raw.meta ?? {}) as Record<string, unknown>;

  const action = normalizeAction(header.action);
  const payloadKind = normalizePayloadKind(payload.kind, action);
  const targetScope = normalizeScope(meta.target_scope);

  return {
    header: {
      action,
      ready: Boolean(header.ready),
      reason: typeof header.reason === "string" ? header.reason.trim() : "",
    },
    payload: normalizePayload(payloadKind, payload, targetScope),
    meta: {
      target_scope: targetScope,
      target_scene_id: typeof meta.target_scene_id === "string" ? meta.target_scene_id : null,
      target_shot_id: typeof meta.target_shot_id === "string" ? meta.target_shot_id : null,
      warnings: Array.isArray(meta.warnings) ? meta.warnings.filter((item): item is string => typeof item === "string") : undefined,
    },
  };
}

function normalizeAction(value: unknown): PlannerActionType {
  const asString = typeof value === "string" ? value.trim() : "";
  if (VALID_ACTIONS.has(asString as PlannerActionType)) {
    return asString as PlannerActionType;
  }
  throw new Error(`invalid_action_${asString || "unknown"}`);
}

function normalizePayloadKind(value: unknown, action: PlannerActionType): PlannerDecisionPayload["kind"] {
  const asString = typeof value === "string" ? value.trim() : "";
  if (!asString) {
    return EXPECTED_PAYLOAD_KIND_BY_ACTION[action];
  }
  return asString as PlannerDecisionPayload["kind"];
}

function normalizeScope(value: unknown): RuntimeScope {
  const asString = typeof value === "string" ? value.trim() : "";
  if (VALID_SCOPES.has(asString as RuntimeScope)) {
    return asString as RuntimeScope;
  }
  throw new Error(`invalid_target_scope_${asString || "unknown"}`);
}

function normalizePayload(
  kind: PlannerDecisionPayload["kind"],
  payload: Record<string, unknown>,
  targetScope: RuntimeScope,
): PlannerDecisionPayload {
  switch (kind) {
    case "none":
      return { kind: "none" };
    case "clarification":
      return {
        kind: "clarification",
        questions: Array.isArray(payload.questions)
          ? payload.questions.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
          : [],
      };
    case "goal_update":
      return {
        kind: "goal_update",
        changes: isRecord(payload.changes) ? payload.changes : {},
      };
    case "selection_update":
      return {
        kind: "selection_update",
        scope: normalizeScope(payload.scope ?? targetScope),
        scene_id: typeof payload.scene_id === "string" ? payload.scene_id : null,
        shot_id: typeof payload.shot_id === "string" ? payload.shot_id : null,
      };
    case "retrieval_request":
      return {
        kind: "retrieval_request",
        request: (payload.request ?? {}) as RetrievalRequestPayload,
      };
    case "candidate_inspection":
      return {
        kind: "candidate_inspection",
        request: (payload.request ?? {}) as InspectToolRequestPayload,
      };
    case "edit_draft_patch":
      return {
        kind: "edit_draft_patch",
        patch: (payload.patch ?? {}) as EditDraftPatchPayload,
      };
    case "preview_request":
      return {
        kind: "preview_request",
        request: (payload.request ?? {}) as PreviewToolRequestPayload,
      };
    default:
      throw new Error(`unsupported_payload_kind_${kind}`);
  }
}

function validatePayloadConsistency(output: PlannerOutput): PlannerOutputValidationError[] {
  const errors: PlannerOutputValidationError[] = [];
  switch (output.payload.kind) {
    case "clarification":
      if (output.payload.questions.length === 0) {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "clarification_questions_required" });
      }
      break;
    case "selection_update":
      if (output.payload.scope === "scene" && !output.payload.scene_id) {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "selection_scene_id_required" });
      }
      if (output.payload.scope === "shot" && !output.payload.shot_id) {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "selection_shot_id_required" });
      }
      break;
    case "retrieval_request":
      if (!output.payload.request.query?.trim()) {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "retrieval_query_required" });
      }
      if (!output.payload.request.policy) {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "retrieval_policy_required" });
      }
      break;
    case "candidate_inspection":
      if (!Array.isArray(output.payload.request.candidates) || output.payload.request.candidates.length === 0) {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "inspection_candidates_required" });
      }
      break;
    case "edit_draft_patch":
      if (!Array.isArray(output.payload.patch.operations) || output.payload.patch.operations.length === 0) {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "patch_operations_required" });
      }
      break;
    case "preview_request":
      if (typeof output.payload.request.draft_version !== "number") {
        errors.push({ code: "ACTION_PAYLOAD_MISMATCH", message: "preview_draft_version_required" });
      }
      break;
    default:
      break;
  }
  return errors;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
