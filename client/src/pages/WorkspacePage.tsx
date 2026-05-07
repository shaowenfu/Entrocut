import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  ChevronRight,
  ChevronDown,
  Download,
  Film,
  FolderUp,
  GripVertical,
  KeyRound,
  Layers,
  ListVideo,
  Loader2,
  MessageSquare,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  Scissors,
  Search,
  ScanSearch,
  Send,
  Settings,
  Settings2,
  Sparkles,
  Tag,
  Trash2,
  Undo2,
  Upload,
  Wand2,
  X,
  type LucideIcon,
} from "lucide-react";
import AccountMenu from "../components/account/AccountMenu";
import { BrandIcon } from "../components/icons/BrandIcon";
import {
  isElectronEnvironment,
  toDesktopMediaFileReferences,
  type MediaPickMode,
} from "../services/electronBridge";
import type { CoreAgentStepItem } from "../services/coreClient";
import {
  createThumbnailFromMediaUrl,
  getProjectMediaSource,
  registerProjectPersistedMediaSources,
} from "../services/localMediaRegistry";
import { getOrCreateSessionId } from "../utils/session";
import {
  useWorkspaceStore,
  type AssistantDecisionTurn,
  type ChatTurn,
} from "../store/useWorkspaceStore";
import { useAuthStore } from "../store/useAuthStore";

type WorkspacePageProps = {
  workspaceId: string;
  workspaceName: string;
  onBackLaunchpad?: () => void;
};

type MediaTab = "assets" | "clips";
type DraggingTarget = "left" | "mid" | null;
type PreviewSelection =
  | { kind: "asset"; assetId: string }
  | { kind: "clip"; clipId: string }
  | { kind: "scene"; sceneId: string }
  | null;

const SUGGESTION_CHIPS = [
  "Generate rough cut",
  "Match music beat",
  "Replace scene 2 with a cleaner close-up",
  "Make pacing slightly slower",
];


interface EmptyMediaGuidanceProps {
  onUploadClick: (mode?: MediaPickMode) => void;
  isDisabled: boolean;
  isElectron: boolean;
}

function EmptyMediaGuidance({ onUploadClick, isDisabled, isElectron }: EmptyMediaGuidanceProps) {
  return (
    <div className="empty-media-guidance">
      <Upload size={32} />
      <h3>Start with a plan or upload media</h3>
      <p>You can discuss the edit goal first, then upload videos when you are ready to cut.</p>
      <div className="empty-media-actions">
        <button onClick={() => onUploadClick(isElectron ? "electron-files" : "browser-files")} disabled={isDisabled}>
          Upload Videos
        </button>
        {isElectron ? (
          <button onClick={() => onUploadClick("electron-folder")} disabled={isDisabled}>
            Select Folder
          </button>
        ) : null}
      </div>
      <small>Or drag and drop files directly into this panel</small>
    </div>
  );
}

function parseSceneDurationSeconds(duration: string): number {
  const parsed = Number.parseInt(duration.replace(/[^\d]/g, ""), 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function parseDurationSeconds(duration: string): number {
  const parsed = Number.parseInt(duration.replace(/[^\d]/g, ""), 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatClock(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function formatTimecode(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const hrs = Math.floor(safe / 3600);
  const mins = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return `TC ${hrs.toString().padStart(2, "0")}:${mins
    .toString()
    .padStart(2, "0")}:${secs.toString().padStart(2, "0")}:00`;
}

function formatOperation(op: AssistantDecisionTurn["ops"][number]): string {
  const parts = [op.action];
  if (op.target) {
    parts.push(`target=${op.target}`);
  }
  if (op.summary) {
    parts.push(`summary=${op.summary}`);
  }
  return parts.join(" | ");
}

function getIconForPhase(phase: string) {
  const p = phase.toLowerCase();
  if (p.includes("retriev") || p.includes("search")) return Search;
  if (p.includes("inspect")) return ScanSearch;
  if (p.includes("patch") || p.includes("edit") || p.includes("cut")) return Scissors;
  return Settings;
}

type AgentStepStatus = "loading" | "success" | "error";

function getStringDetail(details: Record<string, unknown>, key: string): string | null {
  const value = details[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function getBooleanDetail(details: Record<string, unknown>, key: string): boolean | null {
  const value = details[key];
  return typeof value === "boolean" ? value : null;
}

function getToolNameForStep(step: CoreAgentStepItem): string | null {
  const fromDetails = getStringDetail(step.details, "tool_name");
  if (fromDetails) {
    return fromDetails;
  }
  const phase = step.phase.toLowerCase();
  if (phase.includes("retriev")) return "retrieve";
  if (phase.includes("inspect")) return "inspect";
  if (phase.includes("patch") || phase.includes("edit")) return "patch";
  if (phase.includes("preview")) return "preview";
  return null;
}

function getAgentStepStatus(step: CoreAgentStepItem, isLastStep: boolean, isThinking: boolean): AgentStepStatus {
  const rawStatus = typeof step.status === "string" ? step.status.toLowerCase() : "";
  const successDetail = getBooleanDetail(step.details, "success");
  if (rawStatus === "failed" || rawStatus === "error" || successDetail === false) {
    return "error";
  }
  if (rawStatus === "success" || rawStatus === "succeeded" || rawStatus === "complete" || successDetail === true) {
    return "success";
  }
  if (rawStatus === "running" || rawStatus === "pending" || rawStatus === "queued") {
    return "loading";
  }
  return isThinking && isLastStep ? "loading" : "success";
}

function getAgentStepTitle(step: CoreAgentStepItem): string {
  const toolName = getToolNameForStep(step);
  const toolInputSummary = getStringDetail(step.details, "tool_input_summary");
  if (toolInputSummary && toolName) {
    return `${toolName}: ${toolInputSummary}`;
  }
  return step.summary || step.phase;
}

function getAgentStepSummary(step: CoreAgentStepItem, status: AgentStepStatus): string {
  const prefix = status === "error" ? "Failed" : status === "loading" ? "Running" : "Done";
  return `${prefix}: ${step.summary || step.phase}`;
}

function getAgentStepKey(step: CoreAgentStepItem, index: number): string {
  return `${getAgentStepSignature(step)}:${index}`;
}

function getAgentStepSignature(step: CoreAgentStepItem): string {
  const toolName = getToolNameForStep(step) ?? "step";
  const details = formatAgentDetailValue(step.details);
  return [
    step.emitted_at,
    step.iteration,
    step.phase,
    toolName,
    step.summary,
    details,
  ].filter((part) => part !== undefined && part !== null && String(part).length > 0).join(":");
}

function formatAgentDetailValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function UserMessageView({ text }: { text: string }) {
  return (
    <div className="chat-row chat-row-user">
      <div className="chat-bubble">{text}</div>
    </div>
  );
}

function AgentFinalMessageView({ turn }: { turn: AssistantDecisionTurn }) {
  return (
    <article className="decision-card">
      <header>
        <Sparkles size={14} />
        <span>AI DECISION</span>
      </header>
      <div className="decision-content">
        <p>{turn.reasoning_summary}</p>
        {turn.ops.length > 0 ? (
          <div className="decision-ops">
            {turn.ops.map((op) => (
              <div key={op.id || `${op.action}_${op.target}_${op.summary}`} className="decision-op">
                <span />
                <code>{formatOperation(op)}</code>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function AgentStepItem({
  status,
  title,
  summary,
  icon: Icon,
  children,
}: {
  status: AgentStepStatus;
  title: string;
  summary: string;
  icon: LucideIcon;
  children?: ReactNode;
}) {
  const [isExpanded, setIsExpanded] = useState(status === "loading" || status === "error");
  const [manualOverride, setManualOverride] = useState(false);

  useEffect(() => {
    if (manualOverride) {
      return;
    }
    if (status === "loading" || status === "error") {
      setIsExpanded(true);
      return;
    }
    const timer = window.setTimeout(() => setIsExpanded(false), 1200);
    return () => window.clearTimeout(timer);
  }, [manualOverride, status]);

  const StatusIcon = status === "loading" ? Loader2 : status === "error" ? AlertCircle : Icon;

  return (
    <section className={`agent-step agent-step-${status} ${isExpanded ? "expanded" : "collapsed"}`}>
      <button
        type="button"
        className="agent-step-header"
        onClick={() => {
          setManualOverride(true);
          setIsExpanded((current) => !current);
        }}
        aria-expanded={isExpanded}
      >
        <span className={`agent-step-icon ${status}`}>
          <StatusIcon size={14} />
        </span>
        <span className="step-title">{isExpanded ? title : summary}</span>
        <ChevronDown size={14} className="step-chevron" />
      </button>

      <div className={`agent-step-content-wrapper ${isExpanded ? "expanded" : "collapsed"}`}>
        <div className="agent-step-content-inner">
          <div className="agent-step-content">{children}</div>
        </div>
      </div>
    </section>
  );
}

function AgentStepArtifact({
  step,
  clips,
  onClipSelect,
}: {
  step: CoreAgentStepItem;
  clips: ReturnType<typeof useWorkspaceStore.getState>["clips"];
  onClipSelect: (clipId: string) => void;
}) {
  const toolName = getToolNameForStep(step);
  const details = step.details ?? {};
  const candidateClipIds = Array.isArray(details.candidate_clip_ids)
    ? details.candidate_clip_ids.filter((item): item is string => typeof item === "string")
    : [];
  const matchedClips = candidateClipIds
    .map((clipId) => clips.find((clip) => clip.id === clipId))
    .filter((clip): clip is (typeof clips)[number] => Boolean(clip));

  if (toolName === "retrieve" && matchedClips.length > 0) {
    return (
      <div className="agent-artifact agent-retrieve-artifact">
        {matchedClips.slice(0, 4).map((clip) => (
          <button key={clip.id} type="button" className="agent-clip-match" onClick={() => onClipSelect(clip.id)}>
            <span className={`agent-clip-thumb ${clip.thumbClass}`} />
            <span className="agent-clip-copy">
              <strong>{clip.parent}</strong>
              <small>{clip.start} - {clip.end} · Match {clip.score}</small>
            </span>
          </button>
        ))}
      </div>
    );
  }

  if (toolName === "inspect") {
    const inspectionSummary = getStringDetail(details, "inspection_summary") ?? getStringDetail(details, "summary");
    return inspectionSummary ? (
      <div className="agent-artifact agent-inspect-artifact">
        <ScanSearch size={13} />
        <span>{inspectionSummary}</span>
      </div>
    ) : null;
  }

  if (toolName === "patch") {
    const draftVersion = details.draft_version;
    const clipId = getStringDetail(details, "clip_id");
    return clipId || draftVersion ? (
      <div className="agent-artifact agent-patch-artifact">
        <Scissors size={13} />
        <span>
          {clipId ? `clip=${clipId}` : "draft patched"}
          {draftVersion ? ` · draft_version=${formatAgentDetailValue(draftVersion)}` : ""}
        </span>
      </div>
    ) : null;
  }

  const visibleDetails = Object.entries(details)
    .filter(([key]) => key !== "candidate_clip_ids")
    .slice(0, 4);

  if (visibleDetails.length === 0) {
    return null;
  }

  return (
    <dl className="agent-artifact agent-detail-list">
      {visibleDetails.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{formatAgentDetailValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function extractDroppedFiles(event: DragEvent<HTMLDivElement>): File[] {
  return Array.from(event.dataTransfer.files ?? []).filter((file) => file.size > 0);
}

function formatAssetError(error?: Record<string, unknown> | null): string {
  if (!error) {
    return "";
  }
  const code = typeof error.code === "string" ? error.code : "";
  const message = typeof error.message === "string" ? error.message : "";
  const summary = [code, message].filter(Boolean).join(": ");
  return summary || JSON.stringify(error);
}

function parseClipTimeSeconds(time: string): number {
  const parsed = Number.parseInt(time.replace(/[^\d]/g, ""), 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function WorkspacePage({ workspaceId, workspaceName, onBackLaunchpad }: WorkspacePageProps) {
  const [sessionId] = useState(() => getOrCreateSessionId(workspaceId));
  const [promptText, setPromptText] = useState("");
  const [mediaTab, setMediaTab] = useState<MediaTab>("clips");
  const [highlightItem, setHighlightItem] = useState("");
  const [leftWidth, setLeftWidth] = useState(280);
  const [midWidth, setMidWidth] = useState(400);
  const [dragging, setDragging] = useState<DraggingTarget>(null);
  const [isEditLocked, setIsEditLocked] = useState(false);
  const [reasoningOverlay, setReasoningOverlay] = useState<string | null>(null);
  const [patchPulseId, setPatchPulseId] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeSec, setCurrentTimeSec] = useState(12);
  const [previewSelection, setPreviewSelection] = useState<PreviewSelection>(null);
  const [thumbnailUrls, setThumbnailUrls] = useState<Record<string, string>>({});
  const [mediaRegistryVersion, setMediaRegistryVersion] = useState(0);
  const [missingMediaAssetIds, setMissingMediaAssetIds] = useState<Set<string>>(() => new Set());
  const [isAssetDropHovering, setIsAssetDropHovering] = useState(false);
  const [isAssetPickerOpen, setIsAssetPickerOpen] = useState(false);
  const [showDeletedAssets, setShowDeletedAssets] = useState(false);

  const assets = useWorkspaceStore((state) => state.assets);
  const clips = useWorkspaceStore((state) => state.clips);
  const storyboard = useWorkspaceStore((state) => state.storyboard);
  const chatTurns = useWorkspaceStore((state) => state.chatTurns);
  const modelPrefs = useAuthStore((state) => state.modelPrefs);
  const setModelPrefs = useAuthStore((state) => state.setModelPrefs);
  const platformProviders = useAuthStore((state) => state.platformProviders);
  const modelCatalogState = useAuthStore((state) => state.modelCatalogState);
  const modelCatalogWarning = useAuthStore((state) => state.modelCatalogWarning);
  const refreshModelCatalog = useAuthStore((state) => state.refreshModelCatalog);
  const loadByokProviderKey = useAuthStore((state) => state.loadByokProviderKey);
  const saveByokProviderKey = useAuthStore((state) => state.saveByokProviderKey);
  const deleteByokProviderKey = useAuthStore((state) => state.deleteByokProviderKey);
  const loadState = useWorkspaceStore((state) => state.loadState);
  const chatState = useWorkspaceStore((state) => state.chatState);
  const summaryState = useWorkspaceStore((state) => state.summaryState);
  const coreCapabilities = useWorkspaceStore((state) => state.coreCapabilities);
  const coreMediaSummary = useWorkspaceStore((state) => state.coreMediaSummary);
  const coreRuntimeState = useWorkspaceStore((state) => state.coreRuntimeState);
  const currentProject = useWorkspaceStore((state) => state.currentProject);
  const eventStreamState = useWorkspaceStore((state) => state.eventStreamState);
  const reconnectState = useWorkspaceStore((state) => state.reconnectState);
  const activeTasks = useWorkspaceStore((state) => state.activeTasks);
  const exportResult = useWorkspaceStore((state) => state.exportResult);
  const previewResult = useWorkspaceStore((state) => state.previewResult);
  const agentSteps = useWorkspaceStore((state) => state.agentSteps);
  const lastError = useWorkspaceStore((state) => state.lastError);
  const initializeWorkspace = useWorkspaceStore((state) => state.initializeWorkspace);
  const setSelectionContext = useWorkspaceStore((state) => state.setSelectionContext);
  const uploadAssets = useWorkspaceStore((state) => state.uploadAssets);
  const retryAsset = useWorkspaceStore((state) => state.retryAsset);
  const deleteAsset = useWorkspaceStore((state) => state.deleteAsset);
  const restoreAsset = useWorkspaceStore((state) => state.restoreAsset);
  const renameProject = useWorkspaceStore((state) => state.renameProject);
  const sendChat = useWorkspaceStore((state) => state.sendChat);
  const exportProject = useWorkspaceStore((state) => state.exportProject);
  const clearLastError = useWorkspaceStore((state) => state.clearLastError);

  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const latestAssistantIdRef = useRef<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scrubberTrackRef = useRef<HTMLDivElement | null>(null);
  const [platformCustomModelSelected, setPlatformCustomModelSelected] = useState(false);
  const [byokCustomModelSelected, setByokCustomModelSelected] = useState(false);
  const [isRenamingProject, setIsRenamingProject] = useState(false);
  const [projectTitleDraft, setProjectTitleDraft] = useState(workspaceName);

  const totalDurationSec = storyboard.reduce(
    (total, scene) => total + parseSceneDurationSeconds(scene.duration),
    0
  );
  const activePlatformProvider =
    platformProviders.find((provider) => provider.id === modelPrefs.platformProvider) ?? platformProviders[0] ?? null;
  const activePlatformModels = activePlatformProvider?.models ?? [];
  const selectedPlatformModel =
    activePlatformModels.find((model) => model.id === modelPrefs.platformModel) ?? activePlatformModels[0] ?? null;
  const byokProviderLabel = modelPrefs.byokProvider === "deepseek" ? "DeepSeek" : modelPrefs.byokProvider;
  const byokKeySaved = Boolean(modelPrefs.byokKeySavedByProvider[modelPrefs.byokProvider]);
  const platformCustomModelActive = platformCustomModelSelected || Boolean(modelPrefs.platformCustomModel.trim());
  const byokCustomModelActive = byokCustomModelSelected || Boolean(modelPrefs.byokCustomModel.trim());
  const platformRoutingReady =
    modelPrefs.routingMode !== "Platform" ||
    Boolean(
      activePlatformProvider?.available &&
        (platformCustomModelActive ? modelPrefs.platformCustomModel.trim() : selectedPlatformModel?.available)
    );
  const safeTotalDurationSec = Math.max(1, totalDurationSec);
  const sessionLabel = `Session #${sessionId.slice(-8).toUpperCase()}`;
  const projectTitle = typeof currentProject?.title === "string" ? currentProject.title : workspaceName;
  const isElectron = useMemo(() => isElectronEnvironment(), []);
  const mediaTask = activeTasks.find((task) => task.slot === "media") ?? null;
  const exportTask = activeTasks.find((task) => task.slot === "export") ?? null;
  const agentTask = activeTasks.find((task) => task.slot === "agent") ?? null;
  const isLoadingWorkspace = loadState === "loading";
  const isThinking =
    chatState === "responding" ||
    coreRuntimeState?.execution_state.agent_run_state === "planning" ||
    coreRuntimeState?.execution_state.agent_run_state === "executing_tool";
  const isMediaProcessing =
    summaryState === "media_processing" ||
    (mediaTask?.type === "ingest" && mediaTask.status === "running");
  const isExporting =
    summaryState === "exporting" ||
    (exportTask?.type === "render" && exportTask.status === "running");
  const mediaStatusText = isMediaProcessing
    ? mediaTask?.message ?? "Processing media..."
    : isExporting
    ? exportTask?.message ?? "Exporting..."
    : null;
  const canSendChat =
    !isEditLocked &&
    !isLoadingWorkspace &&
    (coreCapabilities?.can_send_chat ?? true) &&
    platformRoutingReady &&
    !isExporting &&
    !(agentTask && (agentTask.status === "queued" || agentTask.status === "running"));
  const canUploadAssets =
    !isEditLocked &&
    !isExporting &&
    !(exportTask && (exportTask.status === "queued" || exportTask.status === "running"));
  const canExport =
    !isEditLocked &&
    (coreCapabilities?.can_export ?? false) &&
    !(agentTask && (agentTask.status === "queued" || agentTask.status === "running")) &&
    !(exportTask && (exportTask.status === "queued" || exportTask.status === "running"));
  const activeSceneIndex = useMemo(
    () =>
      previewSelection?.kind === "scene"
        ? storyboard.findIndex((scene) => scene.id === previewSelection.sceneId)
        : -1,
    [previewSelection, storyboard]
  );
  const deletedAssetCount = assets.filter((asset) => asset.lifecycleState === "deleted").length;
  const visibleAssets = useMemo(
    () => assets.filter((asset) => (showDeletedAssets ? asset.lifecycleState === "deleted" : asset.lifecycleState !== "deleted")),
    [assets, showDeletedAssets]
  );

  const selectedClip = useMemo(() => {
    if (previewSelection?.kind === "clip") {
      return clips.find((clip) => clip.id === previewSelection.clipId) ?? null;
    }
    if (previewSelection?.kind === "scene") {
      const activeScene = activeSceneIndex >= 0 ? storyboard[activeSceneIndex] : null;
      if (!activeScene?.primaryClipId) {
        return null;
      }
      return clips.find((clip) => clip.id === activeScene.primaryClipId) ?? null;
    }
    return null;
  }, [activeSceneIndex, clips, previewSelection]);

  const selectedAsset = useMemo(() => {
    if (previewSelection?.kind === "asset") {
      return assets.find((asset) => asset.id === previewSelection.assetId) ?? null;
    }
    if (selectedClip) {
      return assets.find((asset) => asset.id === selectedClip.assetId) ?? null;
    }
    return assets[0] ?? null;
  }, [assets, previewSelection, selectedClip]);

  const selectedPreviewSource = useMemo(() => {
    const outputUrl = typeof previewResult?.output_url === "string" ? previewResult.output_url : null;
    if (outputUrl && outputUrl.startsWith("file://")) {
      return { url: outputUrl, kind: "draft" as const };
    }
    if (!selectedAsset) {
      return null;
    }
    const source = getProjectMediaSource(workspaceId, selectedAsset.id);
    return source ? { ...source, kind: "source" as const } : null;
  }, [mediaRegistryVersion, previewResult, selectedAsset, workspaceId]);
  const selectedAssetSourceMissing = Boolean(
    selectedAsset?.sourcePath && missingMediaAssetIds.has(selectedAsset.id)
  );
  const visibleAgentSteps = useMemo(() => {
    const seen = new Set<string>();
    return agentSteps.filter((step) => {
      const signature = getAgentStepSignature(step);
      if (seen.has(signature)) {
        return false;
      }
      seen.add(signature);
      return true;
    });
  }, [agentSteps]);
  const latestChatTurn = chatTurns[chatTurns.length - 1] ?? null;
  const shouldShowAgentSteps =
    visibleAgentSteps.length > 0 && (isThinking || latestChatTurn?.role !== "assistant");

  const previewDurationSec = useMemo(() => {
    if (selectedClip) {
      return Math.max(1, parseClipTimeSeconds(selectedClip.end) - parseClipTimeSeconds(selectedClip.start));
    }
    if (selectedAsset) {
      return Math.max(1, parseDurationSeconds(selectedAsset.duration));
    }
    return safeTotalDurationSec;
  }, [safeTotalDurationSec, selectedAsset, selectedClip]);

  const playbackProgress = Math.min(1, currentTimeSec / Math.max(1, previewDurationSec));

  const previewTitle = useMemo(() => {
    if (previewSelection?.kind === "scene" && activeSceneIndex >= 0) {
      return storyboard[activeSceneIndex]?.title ?? "Storyboard Scene";
    }
    if (selectedClip) {
      return selectedClip.parent;
    }
    return selectedAsset?.name ?? "Preview Stage";
  }, [activeSceneIndex, previewSelection, selectedAsset, selectedClip, storyboard]);

  const previewSubtitle = useMemo(() => {
    if (previewSelection?.kind === "scene" && activeSceneIndex >= 0) {
      return storyboard[activeSceneIndex]?.intent ?? null;
    }
    if (selectedClip) {
      return `${selectedClip.start} - ${selectedClip.end}`;
    }
    return selectedAsset?.duration ?? null;
  }, [activeSceneIndex, previewSelection, selectedAsset, selectedClip, storyboard]);

  const clipThumbnailUrl = useMemo(() => {
    if (!selectedAsset) {
      return null;
    }
    return thumbnailUrls[selectedAsset.id] ?? null;
  }, [selectedAsset, thumbnailUrls]);

  useEffect(() => {
    void initializeWorkspace(workspaceId, workspaceName);
  }, [initializeWorkspace, workspaceId, workspaceName]);

  useEffect(() => {
    if (!isRenamingProject) {
      setProjectTitleDraft(projectTitle);
    }
  }, [isRenamingProject, projectTitle]);

  useEffect(() => {
    let cancelled = false;
    async function restorePersistedMediaSources() {
      const result = await registerProjectPersistedMediaSources(workspaceId, assets);
      if (!cancelled) {
        setMissingMediaAssetIds(new Set(result.missingAssetIds));
        setMediaRegistryVersion((current) => current + 1);
      }
    }
    void restorePersistedMediaSources();
    return () => {
      cancelled = true;
    };
  }, [assets, workspaceId]);

  useEffect(() => {
    if (modelCatalogState === "idle") {
      void refreshModelCatalog();
    }
  }, [modelCatalogState, refreshModelCatalog]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatTurns, isThinking, isMediaProcessing]);

  useEffect(() => {
    if (storyboard.length === 0) {
      setHighlightItem("");
      return;
    }
    setHighlightItem((current) =>
      current && storyboard.some((scene) => scene.id === current) ? current : storyboard[0].id
    );
  }, [storyboard]);

  useEffect(() => {
    if (previewSelection) {
      return;
    }
    if (storyboard[0]) {
      setPreviewSelection({ kind: "scene", sceneId: storyboard[0].id });
      return;
    }
    if (clips[0]) {
      setPreviewSelection({ kind: "clip", clipId: clips[0].id });
      return;
    }
    if (assets[0]) {
      setPreviewSelection({ kind: "asset", assetId: assets[0].id });
    }
  }, [assets, clips, previewSelection, storyboard]);

  useEffect(() => {
    if (previewSelection?.kind === "scene") {
      setSelectionContext({
        scope: "scene",
        selectedSceneId: previewSelection.sceneId,
      });
      return;
    }
    setSelectionContext({ scope: "global" });
  }, [previewSelection, setSelectionContext]);

  useEffect(() => {
    let cancelled = false;
    async function generateThumbnails() {
      const updates: Record<string, string> = {};
      for (const asset of assets) {
        if (thumbnailUrls[asset.id]) {
          continue;
        }
        const source = getProjectMediaSource(workspaceId, asset.id);
        if (!source) {
          continue;
        }
        const thumbnailUrl = await createThumbnailFromMediaUrl(source.url);
        if (cancelled || !thumbnailUrl) {
          continue;
        }
        updates[asset.id] = thumbnailUrl;
      }
      if (!cancelled && Object.keys(updates).length > 0) {
        setThumbnailUrls((current) => ({
          ...current,
          ...updates,
        }));
      }
    }

    void generateThumbnails();
    return () => {
      cancelled = true;
    };
  }, [assets, mediaRegistryVersion, thumbnailUrls, workspaceId]);

  useEffect(() => {
    const latest = [...chatTurns].reverse().find((turn) => turn.role === "assistant");
    if (!latest || latestAssistantIdRef.current === latest.id) {
      return;
    }
    latestAssistantIdRef.current = latest.id;
    const assistantTurn = latest as AssistantDecisionTurn;
    setReasoningOverlay(assistantTurn.reasoning_summary);
    window.setTimeout(() => setReasoningOverlay(null), 2200);
    if (storyboard[0]) {
      setPatchPulseId(storyboard[0].id);
      window.setTimeout(() => setPatchPulseId(null), 1200);
    }
  }, [chatTurns, storyboard]);

  useEffect(() => {
    function handleMouseMove(event: MouseEvent) {
      if (!dragging) {
        return;
      }
      document.body.style.userSelect = "none";
      if (dragging === "left") {
        const nextWidth = Math.max(220, Math.min(event.clientX, 450));
        setLeftWidth(nextWidth);
      } else {
        const nextMid = Math.max(320, Math.min(event.clientX - leftWidth - 16, 600));
        setMidWidth(nextMid);
      }
    }

    function handleMouseUp() {
      setDragging(null);
      document.body.style.userSelect = "auto";
    }

    if (dragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [dragging, leftWidth]);

  useEffect(() => {
    if (currentTimeSec > previewDurationSec) {
      setCurrentTimeSec(previewDurationSec);
    }
  }, [currentTimeSec, previewDurationSec]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !selectedPreviewSource) {
      return;
    }
    const clipStartSec = selectedClip ? parseClipTimeSeconds(selectedClip.start) : 0;
    video.currentTime = clipStartSec;
    setCurrentTimeSec(0);
    if (isPlaying) {
      void video.play().catch(() => {
        setIsPlaying(false);
      });
    } else {
      video.pause();
    }
  }, [isPlaying, selectedClip, selectedPreviewSource]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }

    const handleTimeUpdate = () => {
      const clipStartSec = selectedClip ? parseClipTimeSeconds(selectedClip.start) : 0;
      const clipEndSec = selectedClip ? parseClipTimeSeconds(selectedClip.end) : Number.POSITIVE_INFINITY;
      setCurrentTimeSec(Math.max(0, video.currentTime - clipStartSec));
      if (video.currentTime >= clipEndSec) {
        video.pause();
        setIsPlaying(false);
      }
    };

    const handleLoadedMetadata = () => {
      const clipStartSec = selectedClip ? parseClipTimeSeconds(selectedClip.start) : 0;
      video.currentTime = clipStartSec;
      setCurrentTimeSec(0);
    };

    const handleEnded = () => {
      setIsPlaying(false);
    };
    const handlePlay = () => {
      setIsPlaying(true);
    };
    const handlePause = () => {
      setIsPlaying(false);
    };

    video.addEventListener("timeupdate", handleTimeUpdate);
    video.addEventListener("loadedmetadata", handleLoadedMetadata);
    video.addEventListener("ended", handleEnded);
    video.addEventListener("play", handlePlay);
    video.addEventListener("pause", handlePause);

    return () => {
      video.removeEventListener("timeupdate", handleTimeUpdate);
      video.removeEventListener("loadedmetadata", handleLoadedMetadata);
      video.removeEventListener("ended", handleEnded);
      video.removeEventListener("play", handlePlay);
      video.removeEventListener("pause", handlePause);
    };
  }, [selectedClip, selectedPreviewSource]);

  async function handleExport() {
    if (!canExport) {
      return;
    }
    setIsEditLocked(true);
    setReasoningOverlay("Export started. Editing is locked.");

    try {
      const result = await exportProject();
      if (result) {
        setReasoningOverlay(`Export finished: ${result.output_url}`);
        window.setTimeout(() => setReasoningOverlay(null), 3000);
      } else {
        setReasoningOverlay(null);
      }
    } catch {
      setReasoningOverlay(null);
    } finally {
      setIsEditLocked(false);
    }
  }

  function handleSuggestionPick(suggestion: string) {
    if (!canSendChat) {
      return;
    }
    setPromptText(suggestion);
  }

  async function handleSendChat() {
    const trimmed = promptText.trim();
    if (!trimmed || !canSendChat) {
      return;
    }
    setPromptText("");
    setIsPlaying(false);
    await sendChat(trimmed);
  }

  function handleTogglePlay() {
    if (chatState === "responding" || isMediaProcessing) {
      return;
    }
    const video = videoRef.current;
    if (!video || !selectedPreviewSource) {
      return;
    }
    if (video.paused) {
      if (currentTimeSec >= previewDurationSec) {
        const clipStartSec = selectedClip ? parseClipTimeSeconds(selectedClip.start) : 0;
        video.currentTime = clipStartSec;
        setCurrentTimeSec(0);
      }
      void video.play().catch(() => {
        setIsPlaying(false);
      });
      return;
    }
    video.pause();
  }

  function handleScrubberSeek(clientX: number) {
    const track = scrubberTrackRef.current;
    const video = videoRef.current;
    if (!track || !video || !selectedPreviewSource) {
      return;
    }
    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) {
      return;
    }
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const targetRelativeSec = ratio * previewDurationSec;
    const clipStartSec = selectedClip ? parseClipTimeSeconds(selectedClip.start) : 0;
    video.currentTime = clipStartSec + targetRelativeSec;
    setCurrentTimeSec(targetRelativeSec);
  }

  function handleScrubberPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    handleScrubberSeek(event.clientX);
    const track = scrubberTrackRef.current;
    track?.setPointerCapture(event.pointerId);
  }

  function handleScrubberPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if ((event.buttons & 1) !== 1) {
      return;
    }
    handleScrubberSeek(event.clientX);
  }

  function handleSceneSeek(sceneId: string, index: number) {
    if (isEditLocked) {
      return;
    }
    setHighlightItem(sceneId);
    void index;
    setPreviewSelection({ kind: "scene", sceneId });
    setCurrentTimeSec(0);
    setIsPlaying(true);
  }

  function handleAgentClipSelect(clipId: string) {
    const clip = clips.find((item) => item.id === clipId);
    if (!clip) {
      return;
    }
    setPreviewSelection({ kind: "clip", clipId });
    setCurrentTimeSec(0);
    setIsPlaying(true);
  }

  async function handleAssetBrowse(mode?: MediaPickMode) {
    const pickMode = mode ?? (isElectron ? "electron-files" : "browser-files");
    setIsAssetPickerOpen(false);
    await uploadAssets({ shouldPickMedia: true, pickMode });
  }

  function handleAssetUploadEntryClick() {
    if (!canUploadAssets) {
      return;
    }
    if (isElectron) {
      setIsAssetPickerOpen((current) => !current);
      return;
    }
    void handleAssetBrowse("browser-files");
  }

  async function handleAssetDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsAssetDropHovering(false);
    const droppedFiles = extractDroppedFiles(event);
    const desktopFiles = toDesktopMediaFileReferences(droppedFiles);
    if (desktopFiles.length === 0) {
      return;
    }
    setIsAssetPickerOpen(false);
    await uploadAssets({
      files: desktopFiles,
    });
  }

  async function handleProjectRenameCommit() {
    const trimmed = projectTitleDraft.trim();
    if (!trimmed || trimmed === projectTitle) {
      setProjectTitleDraft(projectTitle);
      setIsRenamingProject(false);
      return;
    }
    await renameProject(trimmed);
    setIsRenamingProject(false);
  }

  return (
    <div className="workspace-root">
      <header className="topbar">
        <div className="topbar-left">
          {onBackLaunchpad ? (
            <button
              className="icon-btn topbar-icon-btn topbar-back-btn"
              type="button"
              onClick={onBackLaunchpad}
              aria-label="back to launchpad"
            >
              <ArrowLeft size={16} />
              <span>Launchpad</span>
            </button>
          ) : null}
          <div className="brand">
            <BrandIcon size={20} />
            <h1>EntroCut</h1>
          </div>
          <div className="topbar-divider" />
          <div className="workspace-path">
            <span>Workspace</span>
            <ChevronRight size={12} />
            {isRenamingProject ? (
              <form
                className="workspace-title-editor"
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleProjectRenameCommit();
                }}
              >
                <input
                  value={projectTitleDraft}
                  onChange={(event) => setProjectTitleDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setProjectTitleDraft(projectTitle);
                      setIsRenamingProject(false);
                    }
                  }}
                  autoFocus
                />
                <button type="submit" className="icon-btn" aria-label="save project title">
                  <Check size={12} />
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="cancel project title edit"
                  onClick={() => {
                    setProjectTitleDraft(projectTitle);
                    setIsRenamingProject(false);
                  }}
                >
                  <X size={12} />
                </button>
              </form>
            ) : (
              <button
                type="button"
                className="workspace-title-button"
                onClick={() => setIsRenamingProject(true)}
                title="Rename project"
              >
                <span className="workspace-path-current">{projectTitle}</span>
                <Pencil size={11} />
              </button>
            )}
          </div>
        </div>

        <div className="topbar-right">
          <div className="workspace-status-cluster">
            {isMediaProcessing ? <span className="lock-pill">{mediaStatusText ?? "MEDIA PROCESSING"}</span> : null}
            {isExporting ? <span className="lock-pill">EXPORTING</span> : null}
            {isEditLocked && !isExporting ? <span className="lock-pill">EDIT LOCKED</span> : null}
            {eventStreamState !== "connected" ? (
              <span className="lock-pill">
                {reconnectState === "max_attempts_reached" ? "EVENTS POLLING" : "EVENTS RECONNECTING"}
              </span>
            ) : null}
          </div>
          <AccountMenu />
          <details className="byok-config" title={modelCatalogWarning ?? undefined}>
            <summary>
              <Settings2 size={13} />
              <span>{modelPrefs.routingMode === "BYOK" ? "BYOK" : "Platform"}</span>
            </summary>
            <div className="byok-config-panel">
              <label>
                <span>Mode</span>
                <select
                  value={modelPrefs.routingMode}
                  onChange={(event) => {
                    const routingMode = event.target.value === "BYOK" ? "BYOK" : "Platform";
                    if (routingMode === "Platform") {
                      setModelPrefs({
                        routingMode,
                        platformProvider: modelPrefs.platformProvider || activePlatformProvider?.id || "",
                        platformModel: modelPrefs.platformModel || selectedPlatformModel?.id || "",
                      });
                    } else {
                      setModelPrefs({ routingMode });
                    }
                    if (routingMode === "BYOK") {
                      void loadByokProviderKey(modelPrefs.byokProvider);
                    }
                  }}
                >
                  <option value="Platform">Platform</option>
                  <option value="BYOK">BYOK</option>
                </select>
              </label>
              <label>
                <span>Provider</span>
                {modelPrefs.routingMode === "BYOK" ? (
                  <select value={modelPrefs.byokProvider} onChange={(event) => {
                    const provider = event.target.value;
                    setByokCustomModelSelected(false);
                    setModelPrefs({ byokProvider: provider, byokModel: "deepseek-v4-flash", byokCustomModel: "" });
                    void loadByokProviderKey(provider);
                  }}>
                    <option value="deepseek">DeepSeek</option>
                  </select>
                ) : (
                  <select
                    value={modelPrefs.platformProvider || activePlatformProvider?.id || ""}
                    onChange={(event) => {
                      const provider = event.target.value;
                      const firstModel =
                        platformProviders.find((item) => item.id === provider)?.models[0]?.id ?? "";
                      setPlatformCustomModelSelected(false);
                      setModelPrefs({ platformProvider: provider, platformModel: firstModel, platformCustomModel: "" });
                    }}
                  >
                    {platformProviders.length === 0 ? (
                      <option value="" disabled>{modelCatalogState === "loading" ? "Loading providers..." : "No platform providers"}</option>
                    ) : null}
                    {platformProviders.map((provider) => (
                      <option key={provider.id} value={provider.id} disabled={!provider.available}>
                        {provider.label}
                      </option>
                    ))}
                  </select>
                )}
              </label>
              <label>
                <span>Model</span>
                {modelPrefs.routingMode === "BYOK" ? (
                  <select
                    value={byokCustomModelActive ? "__custom" : modelPrefs.byokModel}
                    onChange={(event) => {
                      const model = event.target.value;
                      if (model === "__custom") {
                        setByokCustomModelSelected(true);
                        setModelPrefs({ byokCustomModel: modelPrefs.byokCustomModel || modelPrefs.byokModel });
                        return;
                      }
                      setByokCustomModelSelected(false);
                      setModelPrefs({ byokModel: model, byokCustomModel: "" });
                    }}
                  >
                    <option value="deepseek-v4-flash">DeepSeek V4 Flash</option>
                    <option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
                    <option value="__custom">Custom model id</option>
                  </select>
                ) : (
                  <select
                    value={platformCustomModelActive ? "__custom" : modelPrefs.platformModel || selectedPlatformModel?.id || ""}
                    onChange={(event) => {
                      const model = event.target.value;
                      if (model === "__custom") {
                        setPlatformCustomModelSelected(true);
                        setModelPrefs({ platformCustomModel: modelPrefs.platformCustomModel || modelPrefs.platformModel });
                        return;
                      }
                      setPlatformCustomModelSelected(false);
                      setModelPrefs({ platformModel: model, platformCustomModel: "" });
                    }}
                  >
                    {activePlatformModels.length === 0 ? <option value="" disabled>No platform models</option> : null}
                    {activePlatformModels.map((model) => (
                      <option key={model.id} value={model.id} disabled={!model.available}>
                        {model.label} ({model.id})
                      </option>
                    ))}
                    <option value="__custom">Custom model id</option>
                  </select>
                )}
              </label>
              {modelPrefs.routingMode === "Platform" && platformCustomModelActive ? (
                <label>
                  <span>Custom model id</span>
                  <input
                    type="text"
                    value={modelPrefs.platformCustomModel}
                    onChange={(event) => setModelPrefs({ platformCustomModel: event.target.value })}
                    placeholder={modelPrefs.platformModel}
                  />
                </label>
              ) : null}
              {modelPrefs.routingMode === "BYOK" && byokCustomModelActive ? (
                <label>
                  <span>Custom model id</span>
                  <input
                    type="text"
                    value={modelPrefs.byokCustomModel}
                    onChange={(event) => setModelPrefs({ byokCustomModel: event.target.value })}
                    placeholder={modelPrefs.byokModel}
                  />
                </label>
              ) : null}
              {modelPrefs.routingMode === "BYOK" ? (
                <label>
                  <span>{byokProviderLabel} API Key</span>
                  <div className="byok-key-row">
                    <KeyRound size={13} />
                    <input
                      type="password"
                      value={modelPrefs.byokKey}
                      onChange={(event) => setModelPrefs({ byokKey: event.target.value })}
                      placeholder={byokKeySaved ? "Saved key" : "sk-..."}
                    />
                    <button
                      type="button"
                      onClick={() => void saveByokProviderKey(modelPrefs.byokProvider, modelPrefs.byokKey)}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteByokProviderKey(modelPrefs.byokProvider)}
                      disabled={!byokKeySaved && !modelPrefs.byokKey}
                    >
                      Delete
                    </button>
                  </div>
                </label>
              ) : null}
            </div>
          </details>
          <button
            className="export-btn"
            type="button"
            onClick={handleExport}
            disabled={!canExport}
          >
            <Download size={16} />
            <span>{isExporting ? "Exporting..." : "Export"}</span>
          </button>
        </div>
      </header>

      <main className="workspace-main">
        <section className="media-column panel" style={{ width: leftWidth }}>
          <div className="media-tabs">
            <button
              type="button"
              className={mediaTab === "assets" ? "active" : ""}
              onClick={() => !isEditLocked && setMediaTab("assets")}
              disabled={isEditLocked}
            >
              <Layers size={14} />
              <span>Assets</span>
            </button>
            <button
              type="button"
              className={mediaTab === "clips" ? "active" : ""}
              onClick={() => !isEditLocked && setMediaTab("clips")}
              disabled={isEditLocked}
            >
              <Scissors size={14} />
              <span>Clips</span>
            </button>
          </div>

          <div className="media-body">
            {mediaTab === "assets" ? (
              <>
                <div className="asset-upload-picker">
                  <div
                    className={`asset-upload-entry ${isAssetDropHovering ? "is-hovering" : ""} ${
                      !canUploadAssets ? "is-disabled" : ""
                    }`}
                    onClick={handleAssetUploadEntryClick}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setIsAssetDropHovering(true);
                    }}
                    onDragLeave={() => setIsAssetDropHovering(false)}
                    onDrop={handleAssetDrop}
                    aria-expanded={isAssetPickerOpen}
                  >
                    <Upload size={14} />
                    <span>{isElectron ? "Upload videos or select folder" : "Upload videos"}</span>
                  </div>

                  {isElectron && isAssetPickerOpen ? (
                    <div className="asset-upload-menu" role="menu" aria-label="asset upload source">
                      <button
                        type="button"
                        onClick={() => void handleAssetBrowse("electron-files")}
                        disabled={!canUploadAssets}
                        role="menuitem"
                      >
                        <Film size={14} />
                        <span>Select Videos</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleAssetBrowse("electron-folder")}
                        disabled={!canUploadAssets}
                        role="menuitem"
                      >
                        <FolderUp size={14} />
                        <span>Select Folder</span>
                      </button>
                    </div>
                  ) : null}
                </div>

                {deletedAssetCount > 0 ? (
                  <div className="asset-lifecycle-toggle">
                    <button
                      type="button"
                      className={showDeletedAssets ? "is-active" : ""}
                      onClick={() => setShowDeletedAssets((current) => !current)}
                    >
                      {showDeletedAssets ? "Show Active" : `Deleted (${deletedAssetCount})`}
                    </button>
                  </div>
                ) : null}

                {visibleAssets.length === 0 ? (
                  <EmptyMediaGuidance
                    onUploadClick={handleAssetBrowse}
                    isDisabled={!canUploadAssets}
                    isElectron={isElectron}
                  />
                ) : (
                  <div className="asset-grid">
                    {visibleAssets.map((asset) => {
                      const isReady = asset.processingStage === "ready";
                      const isFailed = asset.processingStage === "failed";
                      const isDeleted = asset.lifecycleState === "deleted";
                      const isLoading = !isReady && !isFailed;
                      const sourceMissing = !isDeleted && missingMediaAssetIds.has(asset.id);
                      const progress = asset.processingProgress ?? 0;
                      const assetErrorTitle = sourceMissing ? "SOURCE_MISSING: local source file is unavailable" : formatAssetError(asset.lastError);
                      
                      return (
                        <article
                          key={asset.id}
                          className={`asset-card ${
                            previewSelection?.kind === "asset" && previewSelection.assetId === asset.id ? "is-active" : ""
                          } ${!isReady ? "is-processing" : ""} ${isDeleted ? "is-deleted" : ""}`}
                          title={assetErrorTitle || asset.name}
                          onClick={() => {
                            if (isReady && !isDeleted) {
                              setPreviewSelection({ kind: "asset", assetId: asset.id });
                              setCurrentTimeSec(0);
                              setIsPlaying(!sourceMissing);
                            }
                          }}
                        >
                          <div className="asset-thumb">
                            {isReady ? (
                              sourceMissing ? (
                                <div className="asset-thumb-status warning">
                                  <AlertCircle size={20} />
                                  <span className="status-text">源文件缺失</span>
                                </div>
                              ) : thumbnailUrls[asset.id] ? (
                                <img src={thumbnailUrls[asset.id]} alt={asset.name} className="asset-thumb-image" />
                              ) : (
                                <Film size={14} />
                              )
                            ) : isFailed ? (
                              <div className="asset-thumb-status error">
                                <AlertCircle size={20} />
                                <span className="status-text">处理失败</span>
                              </div>
                            ) : (
                              <div className="asset-thumb-status loading">
                                <Loader2 size={20} className="spinner" />
                                <span className="status-text">
                                  {asset.processingStage === "segmenting" ? "镜头切分中" : "云端特征提取中"} {progress}%
                                </span>
                              </div>
                            )}
                            {isReady && <span>{asset.duration}</span>}
                          </div>
                          {isFailed || isReady || isDeleted ? (
                            <div className="asset-card-actions">
                              {sourceMissing ? (
                                <button
                                  type="button"
                                  className="asset-card-action"
                                  title="Re-upload source file"
                                  aria-label={`re-upload ${asset.name}`}
                                  disabled={!canUploadAssets}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void handleAssetBrowse(isElectron ? "electron-files" : "browser-files");
                                  }}
                                >
                                  <Upload size={13} />
                                </button>
                              ) : null}
                              {isFailed && !isDeleted ? (
                                <button
                                  type="button"
                                  className="asset-card-action"
                                  title={assetErrorTitle ? `Retry: ${assetErrorTitle}` : "Retry asset"}
                                  aria-label={`retry ${asset.name}`}
                                  disabled={!canUploadAssets}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void retryAsset(asset.id);
                                  }}
                                >
                                  <RefreshCw size={13} />
                                </button>
                              ) : null}
                              {isDeleted ? (
                                <button
                                  type="button"
                                  className="asset-card-action"
                                  title="Restore asset"
                                  aria-label={`restore ${asset.name}`}
                                  disabled={!canUploadAssets}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void restoreAsset(asset.id);
                                  }}
                                >
                                  <Undo2 size={13} />
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="asset-card-action"
                                  title="Delete asset"
                                  aria-label={`delete ${asset.name}`}
                                  disabled={!canUploadAssets}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void deleteAsset(asset.id);
                                  }}
                                >
                                  <Trash2 size={13} />
                                </button>
                              )}
                            </div>
                          ) : null}
                          <p title={asset.name}>{asset.name}</p>
                        </article>
                      );
                    })}
                  </div>
                )}
              </>
            ) : (
              <div className="clip-list">
                {clips.map((clip) => (
                  <article
                    key={clip.id}
                    className={`clip-card ${
                      previewSelection?.kind === "clip" && previewSelection.clipId === clip.id ? "is-active" : ""
                    }`}
                    onClick={() => {
                      setPreviewSelection({ kind: "clip", clipId: clip.id });
                      setCurrentTimeSec(0);
                      setIsPlaying(true);
                    }}
                  >
                    <div className="clip-head">
                      <span className="clip-parent">
                        <Tag size={10} />
                        {clip.parent}
                      </span>
                      <span className="clip-score">Match {clip.score}</span>
                    </div>
                    <div className="clip-range">
                      <span>
                        {clip.start} - {clip.end}
                      </span>
                    </div>
                    <div className="clip-body">
                      <div className={`clip-thumb ${clip.thumbClass}`}>
                        {thumbnailUrls[clip.assetId] ? (
                          <img src={thumbnailUrls[clip.assetId]} alt={clip.parent} className="clip-thumb-image" />
                        ) : null}
                        <span>{clip.start}</span>
                      </div>
                      <p title={clip.desc}>“{clip.desc}”</p>
                    </div>
                  </article>
                ))}
                {clips.length === 0 ? (
                  <article className="clip-card">
                    <p>No clips yet. Ingest will generate semantic clips here.</p>
                  </article>
                ) : null}
              </div>
            )}
            {lastError ? (
              <p className="workspace-error-banner" role="alert" onClick={clearLastError}>
                {lastError.code}: {lastError.message}
                {lastError.cause ? ` (${lastError.cause})` : ""}
                {lastError.requestId ? ` (request_id=${lastError.requestId})` : ""}
              </p>
            ) : null}
          </div>
        </section>

        <div
          className={`resize-handle ${isEditLocked ? "is-disabled" : ""}`}
          onMouseDown={() => !isEditLocked && setDragging("left")}
          role="separator"
        >
          <GripVertical size={12} />
        </div>

        <section className="copilot-column panel" style={{ width: midWidth }}>
          <div className="copilot-header">
            <h2>
              <MessageSquare size={16} />
              <span>AI Copilot</span>
            </h2>
            <div className="topbar-actions">
              <span className="session-badge">{sessionLabel}</span>
            </div>
          </div>

          <div className="chat-thread">
            {/* 1. Historical Turns */}
            {chatTurns.map((turn) => (
              <div key={turn.id} className={turn.role === "user" ? "chat-turn-user" : "chat-turn-assistant"}>
                {turn.role === "user" ? (
                  <UserMessageView text={turn.content} />
                ) : (
                  <AgentFinalMessageView turn={turn as AssistantDecisionTurn} />
                )}
              </div>
            ))}

            {/* 2. Active Execution Block */}
            {shouldShowAgentSteps ? (
              <div className="agent-execution-block">
                {visibleAgentSteps.map((step, idx) => {
                  const isLastStep = idx === visibleAgentSteps.length - 1;
                  const status = getAgentStepStatus(step, isLastStep, isThinking);
                  const Icon = getIconForPhase(getToolNameForStep(step) ?? step.phase);

                  return (
                    <AgentStepItem
                      key={getAgentStepKey(step, idx)}
                      status={status}
                      title={getAgentStepTitle(step)}
                      summary={getAgentStepSummary(step, status)}
                      icon={Icon}
                    >
                      <AgentStepArtifact step={step} clips={clips} onClipSelect={handleAgentClipSelect} />
                    </AgentStepItem>
                  );
                })}
              </div>
            ) : null}

            {isMediaProcessing ? (
              <div className="thinking-box">
                <Loader2 size={16} />
                <span>{mediaStatusText ?? "Processing media..."}</span>
              </div>
            ) : null}

            {isThinking && (!shouldShowAgentSteps || visibleAgentSteps.length === 0) ? (
              <div className="thinking-box">
                <Loader2 size={16} />
                <span>Analyzing footage and generating edit...</span>
              </div>
            ) : null}

            {!isThinking && !isMediaProcessing && !isLoadingWorkspace && chatTurns.length === 0 ? (
              <div className="thinking-box">
                <Sparkles size={16} />
                <span>
                  {coreCapabilities?.chat_mode === "planning_only"
                    ? "Describe the edit goal first, or upload media to enter editing mode."
                    : "Send a prompt to start AI editing."}
                </span>
              </div>
            ) : null}
            {assets.length === 0 && chatTurns.length === 0 && !isThinking && !isMediaProcessing && !isLoadingWorkspace && (
              <div className="chat-limitation-notice">
                <Sparkles size={14} />
                <span>
                  No media yet. Chat is in planning mode; retrieval and draft patching will unlock after indexing.
                </span>
              </div>
            )}
            {isMediaProcessing && coreMediaSummary ? (
              <div className="chat-limitation-notice">
                <Sparkles size={14} />
                <span>
                  Indexed clips {coreMediaSummary.indexed_clip_count}/{coreMediaSummary.total_clip_count}.
                </span>
              </div>
            ) : null}
            <div ref={chatEndRef} />
          </div>

          <div className="suggestion-row">
            {SUGGESTION_CHIPS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => handleSuggestionPick(suggestion)}
                disabled={!canSendChat}
              >
                {suggestion}
              </button>
            ))}
          </div>

          <div className="composer-wrap">
            <textarea
              value={promptText}
              onChange={(event) => setPromptText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSendChat();
                }
              }}
              disabled={!canSendChat}
              placeholder={
                coreCapabilities?.chat_mode === "planning_only"
                  ? "Describe the edit goal, pacing, audience, or footage you plan to upload..."
                  : "Describe your edit..."
              }
            />
            <button
              type="button"
              onClick={() => void handleSendChat()}
              disabled={!promptText.trim() || !canSendChat}
              aria-label="send"
            >
              <Send size={16} />
            </button>
          </div>
        </section>

        <div
          className={`resize-handle resize-handle-teal ${isEditLocked ? "is-disabled" : ""}`}
          onMouseDown={() => !isEditLocked && setDragging("mid")}
          role="separator"
        >
          <GripVertical size={12} />
        </div>

        <section className="stage-column">
          <div className="preview-panel">
            <div className="preview-frame">
              <div className="preview-layer" />
              {isThinking || isMediaProcessing || isLoadingWorkspace ? (
                <div className="preview-center">
                  <Loader2 size={32} />
                  <span>RENDERING PIPELINE</span>
                </div>
              ) : selectedPreviewSource ? (
                <video
                  ref={videoRef}
                  className="preview-video"
                  src={selectedPreviewSource.url}
                  muted
                  playsInline
                  controls={false}
                />
              ) : (
                <div className="preview-center">
                  <Film size={40} />
                  <span>{selectedAssetSourceMissing ? "SOURCE MISSING" : "PREVIEW SOURCE UNAVAILABLE"}</span>
                  {selectedAssetSourceMissing ? (
                    <button
                      type="button"
                      className="preview-source-action"
                      disabled={!canUploadAssets}
                      onClick={() => void handleAssetBrowse(isElectron ? "electron-files" : "browser-files")}
                    >
                      Re-upload Source
                    </button>
                  ) : null}
                </div>
              )}
              <div className="timecode">{formatTimecode(currentTimeSec)}</div>
              {!isThinking && !isMediaProcessing && !isLoadingWorkspace ? (
                <div className="preview-meta">
                  <strong>{previewTitle} {selectedPreviewSource?.kind === "draft" ? "(Draft Preview)" : "(Source Media)"}</strong>
                  <span>{previewSubtitle ?? "Select an asset, clip, or storyboard scene to preview."}</span>
                </div>
              ) : null}
              {!isThinking && !isMediaProcessing && !isLoadingWorkspace && clipThumbnailUrl ? (
                <div className="preview-thumbnail-chip">
                  <img src={clipThumbnailUrl} alt={previewTitle} />
                </div>
              ) : null}
              {reasoningOverlay ? <div className="reasoning-overlay">{reasoningOverlay}</div> : null}
            </div>

            <div className="scrubber">
              <button type="button" className="icon-btn" aria-label="play" onClick={handleTogglePlay}>
                {isPlaying ? <Pause size={14} /> : <Play size={14} />}
              </button>
              <div
                ref={scrubberTrackRef}
                className="scrubber-track"
                onPointerDown={handleScrubberPointerDown}
                onPointerMove={handleScrubberPointerMove}
              >
                <div
                  className="scrubber-progress"
                  style={{ width: `${Math.max(0, Math.min(100, playbackProgress * 100))}%` }}
                />
                <div
                  className="scrubber-thumb"
                  style={{ left: `${Math.max(0, Math.min(100, playbackProgress * 100))}%` }}
                />
              </div>
              <div className="scrubber-time">
                {formatClock(currentTimeSec)} / {formatClock(previewDurationSec)}
              </div>
            </div>
          </div>

          <div className="storyboard-panel">
            <div className="storyboard-head">
              <div className="storyboard-title">
                <ListVideo size={16} />
                <span>AI Storyboard</span>
                <small>READ ONLY</small>
              </div>
            </div>

            <div className="storyboard-rail">
              {storyboard.map((scene, index) => (
                <article
                  key={scene.id}
                  className={`story-card ${scene.bgClass} ${highlightItem === scene.id ? "active" : ""} ${
                    patchPulseId === scene.id ? "patch-pulse" : ""
                  }`}
                  onClick={() => handleSceneSeek(scene.id, index)}
                >
                  <div className={`story-thumb ${scene.colorClass}`}>
                    {thumbnailUrls[
                      (clips.find((clip) => clip.id === scene.primaryClipId) ?? selectedClip)?.assetId ?? ""
                    ] ? (
                      <img
                        src={
                          thumbnailUrls[
                            (clips.find((clip) => clip.id === scene.primaryClipId) ?? selectedClip)?.assetId ?? ""
                          ]
                        }
                        alt={scene.title}
                        className="story-thumb-image"
                      />
                    ) : null}
                    <span>SCENE {index + 1}</span>
                    <small>{scene.duration}</small>
                  </div>
                  <div className="story-body">
                    <h3>{scene.title}</h3>
                    <p>
                      <Wand2 size={12} />
                      <span>{scene.intent}</span>
                    </p>
                  </div>
                  {highlightItem === scene.id ? <div className="story-active-line" /> : null}
                </article>
              ))}

              {storyboard.length === 0 ? (
                <div className="story-end">
                  <ListVideo size={20} />
                  <span>No Storyboard Yet</span>
                </div>
              ) : (
                <div className="story-end">
                  <ListVideo size={20} />
                  <span>END</span>
                </div>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default WorkspacePage;
