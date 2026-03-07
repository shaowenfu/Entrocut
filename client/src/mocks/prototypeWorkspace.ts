import { MOCK_LAUNCHPAD_PROJECTS } from "./launchpad";

export type PrototypeDecisionType =
  | "UPDATE_PROJECT_CONTRACT"
  | "APPLY_PATCH_ONLY"
  | "ASK_USER_CLARIFICATION";

export interface PrototypeAgentOperation {
  op: string;
  target_item_id?: string | null;
  new_clip_id?: string | null;
  note?: string | null;
}

export interface PrototypeAsset {
  id: string;
  name: string;
  duration: string;
  type: "video" | "audio";
}

export interface PrototypeClip {
  id: string;
  parent: string;
  start: string;
  end: string;
  score: string;
  desc: string;
  thumbClass: string;
}

export interface PrototypeScene {
  id: string;
  title: string;
  duration: string;
  intent: string;
  colorClass: string;
  bgClass: string;
}

export interface PrototypeUserTurn {
  id: string;
  role: "user";
  content: string;
}

export interface PrototypeAssistantTurn {
  id: string;
  role: "assistant";
  type: "decision";
  decision_type: PrototypeDecisionType;
  reasoning_summary: string;
  ops: PrototypeAgentOperation[];
}

export type PrototypeChatTurn = PrototypeUserTurn | PrototypeAssistantTurn;

export interface PrototypeProjectSummary {
  id: string;
  title: string;
  thumbnailClassName: string;
  storageType: "cloud" | "local";
  lastActiveText: string;
  aiStatus: string;
  lastAiEdit: string;
}

export interface PrototypeProjectRecord extends PrototypeProjectSummary {
  assets: PrototypeAsset[];
  clips: PrototypeClip[];
  storyboard: PrototypeScene[];
  chatTurns: PrototypeChatTurn[];
}

const CLIP_THUMBS = ["thumb-blue", "thumb-indigo", "thumb-purple", "thumb-teal"] as const;
const SCENE_STYLES = [
  { colorClass: "scene-blue", bgClass: "scene-bg-blue" },
  { colorClass: "scene-indigo", bgClass: "scene-bg-indigo" },
  { colorClass: "scene-purple", bgClass: "scene-bg-purple" },
  { colorClass: "scene-cyan", bgClass: "scene-bg-cyan" },
] as const;

const registry = new Map<string, PrototypeProjectRecord>();

function createId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 10)}`;
  }
  return `${prefix}_${Math.random().toString(16).slice(2, 12)}`;
}

function cloneRecord<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function toClock(totalSeconds: number): string {
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function buildAsset(name: string, index: number): PrototypeAsset {
  return {
    id: createId("asset"),
    name,
    duration: toClock(18 + index * 7),
    type: "video",
  };
}

function buildClip(asset: PrototypeAsset, index: number): PrototypeClip {
  const starts = ["00:00", "00:03", "00:07", "00:11"] as const;
  const ends = ["00:03", "00:07", "00:11", "00:15"] as const;
  const labels = [
    "Wide establishing moment",
    "Subject motion highlight",
    "Detail texture pickup",
    "Transition beat candidate",
  ] as const;
  return {
    id: createId("clip"),
    parent: asset.id,
    start: starts[index % starts.length],
    end: ends[index % ends.length],
    score: `${92 - index * 4}%`,
    desc: `${labels[index % labels.length]} from ${asset.name}`,
    thumbClass: CLIP_THUMBS[index % CLIP_THUMBS.length],
  };
}

function buildStoryboard(clips: PrototypeClip[], prompt?: string): PrototypeScene[] {
  const intentSeed = prompt?.trim() || "Prototype rough cut";
  if (clips.length === 0) {
    return [
      {
        id: "scene_waiting",
        title: "Waiting For Media",
        duration: "5s",
        intent: "Upload footage to generate the first storyboard.",
        colorClass: "scene-indigo",
        bgClass: "scene-bg-indigo",
      },
    ];
  }
  return clips.slice(0, 4).map((clip, index) => {
    const style = SCENE_STYLES[index % SCENE_STYLES.length];
    return {
      id: `scene_${clip.id}`,
      title: index === 0 ? "Cold Open" : index === 1 ? "Momentum Lift" : index === 2 ? "Hero Detail" : "Resolve",
      duration: index === 0 ? "4s" : index === 1 ? "6s" : index === 2 ? "5s" : "4s",
      intent: `${intentSeed} · ${clip.desc}`,
      colorClass: style.colorClass,
      bgClass: style.bgClass,
    };
  });
}

function buildAssistantTurn(
  summary: string,
  ops: PrototypeAgentOperation[],
  decisionType: PrototypeDecisionType = "UPDATE_PROJECT_CONTRACT"
): PrototypeAssistantTurn {
  return {
    id: createId("assistant"),
    role: "assistant",
    type: "decision",
    decision_type: decisionType,
    reasoning_summary: summary,
    ops,
  };
}

function inferProjectTitle(input: {
  prompt?: string;
  folderPath?: string;
  files?: File[];
  title?: string;
}): string {
  const explicit = input.title?.trim();
  if (explicit) {
    return explicit;
  }
  const folderName = input.folderPath?.split(/[\\/]/).filter(Boolean).at(-1)?.trim();
  if (folderName) {
    return folderName;
  }
  const firstFile = input.files?.[0]?.name?.trim();
  if (firstFile) {
    return firstFile.replace(/\.[^.]+$/, "");
  }
  const prompt = input.prompt?.trim();
  if (prompt) {
    return prompt.slice(0, 32);
  }
  return "Untitled Prototype";
}

function inferAssetNames(input: { folderPath?: string; files?: File[] }, title: string): string[] {
  if (input.files && input.files.length > 0) {
    return input.files.slice(0, 4).map((file) => file.name);
  }
  if (input.folderPath) {
    return [`${title}_wide.mp4`, `${title}_action.mp4`, `${title}_detail.mp4`];
  }
  return [];
}

function buildRecord(input: {
  id?: string;
  title: string;
  thumbnailClassName?: string;
  storageType?: "cloud" | "local";
  lastActiveText?: string;
  aiStatus?: string;
  lastAiEdit?: string;
  assetNames?: string[];
  prompt?: string;
  clipCount?: number;
}): PrototypeProjectRecord {
  const assets = (input.assetNames ?? []).map((name, index) => buildAsset(name, index));
  const clips: PrototypeClip[] = [];
  assets.forEach((asset, assetIndex) => {
    clips.push(buildClip(asset, assetIndex), buildClip(asset, assetIndex + 1));
  });
  const expandedClips =
    input.clipCount && input.clipCount > clips.length
      ? [
          ...clips,
          ...Array.from({ length: input.clipCount - clips.length }, (_, index) => {
            const sourceAsset = assets[index % Math.max(assets.length, 1)] ?? buildAsset(`${input.title}_${index + 1}.mp4`, index);
            return buildClip(sourceAsset, index);
          }),
        ]
      : clips;
  return {
    id: input.id ?? createId("proj"),
    title: input.title,
    thumbnailClassName: input.thumbnailClassName ?? "launch-thumb-zinc",
    storageType: input.storageType ?? "local",
    lastActiveText: input.lastActiveText ?? "刚刚",
    aiStatus: input.aiStatus ?? (assets.length > 0 ? "Prototype storyboard ready" : "Awaiting media"),
    lastAiEdit: input.lastAiEdit ?? "Reset to clean prototype shell",
    assets,
    clips: expandedClips,
    storyboard: buildStoryboard(expandedClips, input.prompt),
    chatTurns:
      assets.length > 0
        ? [
            buildAssistantTurn(
              "已进入 prototype mode，当前只保留 UI 和最小框架，分镜内容为本地示意数据。",
              [{ op: "prototype_bootstrap", note: "UI shell retained for rewrite" }],
              "APPLY_PATCH_ONLY"
            ),
          ]
        : [],
  };
}

function seedRegistry(): void {
  if (registry.size > 0) {
    return;
  }
  MOCK_LAUNCHPAD_PROJECTS.forEach((project, index) => {
    registry.set(
      project.id,
      buildRecord({
        id: project.id,
        title: project.title,
        thumbnailClassName: project.thumbnailClassName,
        storageType: project.storageType,
        lastActiveText: project.lastActiveText,
        aiStatus: project.aiStatus,
        lastAiEdit: project.lastAiEdit,
        assetNames: [
          `${project.title}_a.mp4`,
          `${project.title}_b.mp4`,
          `${project.title}_c.mp4`,
        ],
        clipCount: Math.max(4, Math.min(project.clipCount, 8)),
        prompt: index % 2 === 0 ? "High energy prototype montage" : "Calm cinematic prototype sequence",
      })
    );
  });
}

function writeRecord(record: PrototypeProjectRecord): PrototypeProjectRecord {
  registry.set(record.id, cloneRecord(record));
  return cloneRecord(record);
}

export function listPrototypeProjects(): PrototypeProjectSummary[] {
  seedRegistry();
  return Array.from(registry.values()).map((record) => ({
    id: record.id,
    title: record.title,
    thumbnailClassName: record.thumbnailClassName,
    storageType: record.storageType,
    lastActiveText: record.lastActiveText,
    aiStatus: record.aiStatus,
    lastAiEdit: record.lastAiEdit,
  }));
}

export function getPrototypeProject(projectId: string): PrototypeProjectRecord | null {
  seedRegistry();
  const record = registry.get(projectId);
  return record ? cloneRecord(record) : null;
}

export function createPrototypeProject(input: {
  prompt?: string;
  folderPath?: string;
  files?: File[];
  title?: string;
}): PrototypeProjectRecord {
  seedRegistry();
  const title = inferProjectTitle(input);
  return writeRecord(
    buildRecord({
      title,
      assetNames: inferAssetNames(input, title),
      prompt: input.prompt,
      storageType: input.folderPath || (input.files && input.files.length > 0) ? "local" : "cloud",
      aiStatus: input.folderPath || (input.files && input.files.length > 0) ? "Media linked for rewrite" : "Prompt-only prototype",
      lastAiEdit: "Created from clean-room prototype flow",
    })
  );
}

export function createEmptyPrototypeProject(title = "Untitled Prototype"): PrototypeProjectRecord {
  seedRegistry();
  return writeRecord(
    buildRecord({
      title,
      storageType: "local",
      aiStatus: "Awaiting media",
      lastAiEdit: "Empty prototype created",
    })
  );
}

export function addPrototypeAssets(
  projectId: string,
  input: { folderPath?: string; files?: File[] }
): PrototypeProjectRecord | null {
  seedRegistry();
  const existing = registry.get(projectId);
  if (!existing) {
    return null;
  }
  const currentAssetNames = existing.assets.map((asset) => asset.name);
  const mergedAssetNames = [...currentAssetNames, ...inferAssetNames(input, existing.title)].slice(0, 6);
  const updated = buildRecord({
    id: existing.id,
    title: existing.title,
    thumbnailClassName: existing.thumbnailClassName,
    storageType: existing.storageType,
    lastActiveText: "刚刚",
    aiStatus: "Prototype media refreshed",
    lastAiEdit: "Assets replaced for rewrite baseline",
    assetNames: mergedAssetNames,
    prompt: existing.storyboard[0]?.intent,
  });
  updated.chatTurns = [
    ...existing.chatTurns,
    buildAssistantTurn(
      `已导入 ${Math.max(mergedAssetNames.length - currentAssetNames.length, 0)} 个示意素材，当前仍处于 prototype mode。`,
      [{ op: "prototype_assets_added", note: "Refreshed local placeholder media" }],
      "APPLY_PATCH_ONLY"
    ),
  ];
  return writeRecord(updated);
}

export function applyPrototypePrompt(projectId: string, prompt: string): PrototypeProjectRecord | null {
  seedRegistry();
  const existing = registry.get(projectId);
  if (!existing) {
    return null;
  }
  const trimmedPrompt = prompt.trim();
  const nextTurns: PrototypeChatTurn[] = [
    ...existing.chatTurns,
    { id: createId("user"), role: "user", content: trimmedPrompt },
  ];

  if (existing.assets.length === 0) {
    return writeRecord({
      ...existing,
      aiStatus: "Awaiting media",
      lastAiEdit: "Prompt captured in prototype mode",
      chatTurns: [
        ...nextTurns,
        buildAssistantTurn(
          "当前仓库已经切到 clean-room rewrite，AI 逻辑被清空。先上传素材，再定义新的 ingest/chat/render 契约。",
          [
            { op: "upload_videos", note: "Link source footage before implementing real workflows" },
            { op: "define_contracts", note: "Freeze project/event/render schemas first" },
          ],
          "ASK_USER_CLARIFICATION"
        ),
      ],
    });
  }

  return writeRecord({
    ...existing,
    aiStatus: "Prototype storyboard updated",
    lastAiEdit: `Prompt applied: ${trimmedPrompt.slice(0, 24)}`,
    storyboard: buildStoryboard(existing.clips, trimmedPrompt),
    chatTurns: [
      ...nextTurns,
      buildAssistantTurn(
        `已基于“${trimmedPrompt}”刷新 UI 示意分镜。注意：这不是最终算法结果，而是重构前的原型占位。`,
        [
          { op: "refresh_storyboard", note: "Regenerated prototype storyboard cards" },
          { op: "freeze_contracts", note: "Keep UI stable while backend is rebuilt" },
        ]
      ),
    ],
  });
}

export function exportPrototypeProject(projectId: string): {
  render_type: "export";
  output_url: string;
  duration_ms: number;
  file_size_bytes: number;
  thumbnail_url: null;
  format: string;
  quality: null;
  resolution: string;
} | null {
  seedRegistry();
  const existing = registry.get(projectId);
  if (!existing) {
    return null;
  }
  const timestamp = Date.now();
  const durationMs = Math.max(existing.storyboard.length, 1) * 5000;
  return {
    render_type: "export",
    output_url: `file:///tmp/entrocut_prototype_${projectId}_${timestamp}.mp4`,
    duration_ms: durationMs,
    file_size_bytes: durationMs * 320,
    thumbnail_url: null,
    format: "mp4",
    quality: null,
    resolution: "original",
  };
}
