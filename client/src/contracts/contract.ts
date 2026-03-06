export const CONTRACT_VERSION = "1.0.0";

export type DecisionType =
  | "UPDATE_PROJECT_CONTRACT"
  | "APPLY_PATCH_ONLY"
  | "ASK_USER_CLARIFICATION";

export interface AgentOperation {
  op: string;
  target_item_id?: string | null;
  new_clip_id?: string | null;
  note?: string | null;
}

export interface TimelineFilters {
  speed: number;
  volume_db: number;
}

export interface TimelineItem {
  item_id: string;
  source_clip_id: string;
  timeline_start_ms: number;
  source_in_ms: number;
  source_out_ms: number;
  filters: TimelineFilters;
  reasoning: string;
}

export interface TimelineTrack {
  track_id: string;
  track_type: "video" | "audio";
  items: TimelineItem[];
}

export interface ProjectTimeline {
  tracks: TimelineTrack[];
}

export interface ProjectAsset {
  asset_id: string;
  file_path: string;
  duration_ms: number;
}

export interface ProjectClip {
  clip_id: string;
  asset_id: string;
  start_ms: number;
  end_ms: number;
  embedding_ref: string;
}

export interface EntroVideoProject {
  contract_version: string;
  project_id: string;
  user_id: string;
  updated_at: string;
  assets: ProjectAsset[];
  clip_pool: ProjectClip[];
  timeline: ProjectTimeline;
  reasoning_summary: string;
}

export interface PatchPayload {
  patch_version: string;
  operations: AgentOperation[];
}
