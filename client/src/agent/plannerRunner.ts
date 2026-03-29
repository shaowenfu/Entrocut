import type { ActionContextPacket } from "./contextAssembler";
import type { PlannerRunner } from "./executionLoop";
import type { PlannerOutput } from "./plannerOutput";

type DraftExcerpt =
  | null
  | {
      kind: "global";
      summary: {
        asset_count: number;
        clip_count: number;
        shot_count: number;
        scene_count: number;
        status: string;
      };
    }
  | {
      kind: "scene";
      scene: {
        id: string;
        intent?: string | null;
        label?: string | null;
        shots: Array<{
          id: string;
          clip_id: string;
          intent?: string | null;
          note?: string | null;
        }>;
      };
    }
  | {
      kind: "shot";
      shot: {
        id: string;
        clip_id: string;
        intent?: string | null;
        note?: string | null;
      };
    };

type CandidateExcerpt = {
  latest_request?: {
    summary: string;
    query?: string | null;
  } | null;
  candidates?: Array<{
    clip_id: string;
    asset_id: string;
    summary: string;
    deep_inspected: boolean;
    score?: number | null;
  }>;
};

export function createHeuristicPlannerRunner(): PlannerRunner {
  return {
    plan({ packet }) {
      switch (packet.action_type) {
        case "create_retrieval_request":
          return planRetrieval(packet);
        case "inspect_candidates":
          return planInspect(packet);
        case "apply_patch":
          return planPatch(packet);
        case "render_preview":
          return planPreview(packet);
        case "ask_clarification":
          return clarificationDecision(packet, "Need user clarification to proceed.");
        case "reply_only":
          return {
            header: {
              action: "reply_only",
              ready: true,
              reason: "reply_only_requested",
            },
            payload: { kind: "none" },
            meta: {
              target_scope: packet.scope,
              target_scene_id: packet.selected_scene_id,
              target_shot_id: packet.selected_shot_id,
            },
          };
        case "set_selection_context":
          return {
            header: {
              action: "set_selection_context",
              ready: true,
              reason: "selection_context_requested",
            },
            payload: {
              kind: "selection_update",
              scope: packet.scope,
              scene_id: packet.selected_scene_id,
              shot_id: packet.selected_shot_id,
            },
            meta: {
              target_scope: packet.scope,
              target_scene_id: packet.selected_scene_id,
              target_shot_id: packet.selected_shot_id,
            },
          };
        case "update_goal":
          return {
            header: {
              action: "update_goal",
              ready: true,
              reason: "goal_update_requested",
            },
            payload: {
              kind: "goal_update",
              changes: {
                goal_summary: packet.goal_summary,
              },
            },
            meta: {
              target_scope: packet.scope,
              target_scene_id: packet.selected_scene_id,
              target_shot_id: packet.selected_shot_id,
            },
          };
        default:
          return clarificationDecision(packet, "Unsupported action type.");
      }
    },
  };
}

function planRetrieval(packet: ActionContextPacket): PlannerOutput {
  const query = deriveRetrievalQuery(packet);
  if (!query) {
    return clarificationDecision(packet, "Need a clearer editing goal before retrieval.");
  }

  return {
    header: {
      action: "create_retrieval_request",
      ready: true,
      reason: "enough_goal_and_scope_to_search_candidates",
    },
    payload: {
      kind: "retrieval_request",
      request: {
        project_id: packet.project_id,
        session_id: packet.session_id,
        intent: packet.scope === "global" ? "gather_options" : "replace_scene",
        query,
        scope: packet.scope,
        target_scene_id: packet.selected_scene_id,
        target_shot_id: packet.selected_shot_id,
        constraints: {},
        preferences: {},
        policy: {
          broad_top_k: 12,
          rerank_top_k: 5,
          allow_query_relaxation: true,
          allow_constraint_relaxation: true,
        },
        requested_at: packet.assembled_at,
      },
    },
    meta: {
      target_scope: packet.scope,
      target_scene_id: packet.selected_scene_id,
      target_shot_id: packet.selected_shot_id,
    },
  };
}

function planInspect(packet: ActionContextPacket): PlannerOutput {
  const candidateExcerpt = (packet.candidate_excerpt ?? null) as CandidateExcerpt | null;
  const candidates = candidateExcerpt?.candidates ?? [];
  if (candidates.length === 0) {
    return clarificationDecision(packet, "No candidate clips are available to inspect.");
  }

  return {
    header: {
      action: "inspect_candidates",
      ready: true,
      reason: "candidate_pool_available_for_reranking",
    },
    payload: {
      kind: "candidate_inspection",
      request: {
        project_id: packet.project_id,
        session_id: packet.session_id,
        mode: "choose",
        question: `Which candidate best fits ${packet.goal_summary}?`,
        scope: packet.scope,
        target_scene_id: packet.selected_scene_id,
        target_shot_id: packet.selected_shot_id,
        candidates,
        require_visual_reasoning: false,
        requested_at: packet.assembled_at,
      },
    },
    meta: {
      target_scope: packet.scope,
      target_scene_id: packet.selected_scene_id,
      target_shot_id: packet.selected_shot_id,
    },
  };
}

function planPatch(packet: ActionContextPacket): PlannerOutput {
  const candidateExcerpt = (packet.candidate_excerpt ?? null) as CandidateExcerpt | null;
  const bestCandidate = candidateExcerpt?.candidates?.[0] ?? null;
  if (!bestCandidate) {
    return clarificationDecision(packet, "No inspected candidate is available to patch the draft.");
  }

  const draftExcerpt = packet.draft_excerpt as DraftExcerpt;
  const targetShotId =
    packet.selected_shot_id ??
    (draftExcerpt && draftExcerpt.kind === "scene" ? draftExcerpt.scene.shots[0]?.id ?? null : null);
  if (!targetShotId) {
    return clarificationDecision(packet, "No target shot is available for patching.");
  }
  if (packet.draft_version == null) {
    return clarificationDecision(packet, "Current draft version is missing.");
  }

  return {
    header: {
      action: "apply_patch",
      ready: true,
      reason: "best_candidate_and_target_shot_are_available",
    },
    payload: {
      kind: "edit_draft_patch",
      patch: {
        project_id: packet.project_id,
        draft_id: "current_draft",
        base_version: packet.draft_version,
        scope: packet.scope,
        target_scene_id: packet.selected_scene_id,
        target_shot_id: targetShotId,
        operations: [
          {
            op_id: `replace_${targetShotId}`,
            type: "replace_shot",
            target_scene_id: packet.selected_scene_id,
            target_shot_id: targetShotId,
            clip_id: bestCandidate.clip_id,
            summary: `Replace ${targetShotId} with ${bestCandidate.clip_id}`,
          },
        ],
        created_at: packet.assembled_at,
      },
    },
    meta: {
      target_scope: packet.scope,
      target_scene_id: packet.selected_scene_id,
      target_shot_id: targetShotId,
    },
  };
}

function planPreview(packet: ActionContextPacket): PlannerOutput {
  if (packet.draft_version == null) {
    return clarificationDecision(packet, "No draft version is available for preview.");
  }

  return {
    header: {
      action: "render_preview",
      ready: true,
      reason: "draft_patch_completed_and_preview_is_needed",
    },
    payload: {
      kind: "preview_request",
      request: {
        project_id: packet.project_id,
        draft_id: "current_draft",
        draft_version: packet.draft_version,
        scope: packet.scope,
        scene_id: packet.selected_scene_id,
        shot_id: packet.selected_shot_id,
        options: {
          quality: "draft",
          muted: true,
        },
        requested_at: packet.assembled_at,
      },
    },
    meta: {
      target_scope: packet.scope,
      target_scene_id: packet.selected_scene_id,
      target_shot_id: packet.selected_shot_id,
    },
  };
}

function clarificationDecision(packet: ActionContextPacket, question: string): PlannerOutput {
  return {
    header: {
      action: "ask_clarification",
      ready: true,
      reason: "required_fact_missing_for_next_action",
    },
    payload: {
      kind: "clarification",
      questions: [question],
    },
    meta: {
      target_scope: packet.scope,
      target_scene_id: packet.selected_scene_id,
      target_shot_id: packet.selected_shot_id,
      warnings: ["clarification_required"],
    },
  };
}

function deriveRetrievalQuery(packet: ActionContextPacket): string {
  const draftExcerpt = packet.draft_excerpt as DraftExcerpt;
  const parts: string[] = [];

  if (packet.goal_summary && packet.goal_summary !== "goal_not_confirmed") {
    parts.push(packet.goal_summary);
  }
  if (draftExcerpt && draftExcerpt.kind === "scene") {
    if (draftExcerpt.scene.intent?.trim()) {
      parts.push(draftExcerpt.scene.intent.trim());
    }
    if (draftExcerpt.scene.label?.trim()) {
      parts.push(draftExcerpt.scene.label.trim());
    }
  }
  if (draftExcerpt && draftExcerpt.kind === "shot") {
    if (draftExcerpt.shot.intent?.trim()) {
      parts.push(draftExcerpt.shot.intent.trim());
    }
    if (draftExcerpt.shot.note?.trim()) {
      parts.push(draftExcerpt.shot.note.trim());
    }
  }

  const query = parts
    .join(" ")
    .replace(/\|/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return query;
}
