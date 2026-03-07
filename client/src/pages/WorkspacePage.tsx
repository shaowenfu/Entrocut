import { useEffect, useMemo, useRef, useState, type DragEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  ArrowLeft,
  ChevronRight,
  Download,
  Film,
  GripVertical,
  Layers,
  ListVideo,
  Loader2,
  MessageSquare,
  Pause,
  Play,
  Scissors,
  Send,
  Settings,
  Sparkles,
  Tag,
  Upload,
  Wand2,
} from "lucide-react";
import {
  createInitialHealthSnapshot,
  probeServiceHealth,
  type HealthState,
  type ServiceHealthSnapshot,
  type ServiceTarget,
} from "../services/health";
import { createThumbnailFromMediaUrl, getProjectMediaSource } from "../services/localMediaRegistry";
import { getOrCreateSessionId } from "../utils/session";
import {
  useWorkspaceStore,
  type AssistantDecisionTurn,
  type ChatTurn,
} from "../store/useWorkspaceStore";

type WorkspacePageProps = {
  workspaceId: string;
  workspaceName: string;
  onBackLaunchpad?: () => void;
};

type MediaTab = "assets" | "clips";
type DraggingTarget = "left" | "mid" | null;
type EventStreamVisualState = "online" | "checking" | "offline";
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
const HEALTH_POLL_INTERVAL_MS = 10000;

function isDecisionTurn(turn: ChatTurn): turn is AssistantDecisionTurn {
  return turn.role === "assistant";
}

interface EmptyMediaGuidanceProps {
  onUploadClick: () => void;
  isDisabled: boolean;
}

function EmptyMediaGuidance({ onUploadClick, isDisabled }: EmptyMediaGuidanceProps) {
  return (
    <div className="empty-media-guidance">
      <Upload size={32} />
      <h3>Start by uploading media</h3>
      <p>Upload videos to enable AI-powered editing capabilities.</p>
      <button onClick={onUploadClick} disabled={isDisabled}>
        Upload Videos
      </button>
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

function healthStateLabel(state: HealthState): string {
  switch (state) {
    case "online":
      return "online";
    case "offline":
      return "offline";
    default:
      return "checking";
  }
}

function buildHealthTitle(target: ServiceTarget, snapshot: ServiceHealthSnapshot): string {
  if (snapshot.state === "online") {
    return `${target} is online (${snapshot.latencyMs ?? "-"}ms)`;
  }
  if (snapshot.state === "checking") {
    return `${target} is checking`;
  }
  return `${target} is offline (${snapshot.message ?? "unknown"})`;
}

function toEventStreamVisualState(
  state: "disconnected" | "connecting" | "connected"
): EventStreamVisualState {
  if (state === "connected") {
    return "online";
  }
  if (state === "connecting") {
    return "checking";
  }
  return "offline";
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

function extractDroppedPath(event: DragEvent<HTMLDivElement>): string | null {
  const firstFile = event.dataTransfer.files?.item(0);
  const electronPath = (firstFile as File & { path?: string } | null)?.path;
  return typeof electronPath === "string" && electronPath.trim().length > 0 ? electronPath : null;
}

function extractDroppedFiles(event: DragEvent<HTMLDivElement>): File[] {
  return Array.from(event.dataTransfer.files ?? []).filter((file) => file.size > 0);
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
  const [isAssetDropHovering, setIsAssetDropHovering] = useState(false);
  const [serviceHealth, setServiceHealth] = useState<Record<ServiceTarget, ServiceHealthSnapshot>>({
    core: createInitialHealthSnapshot(),
    server: createInitialHealthSnapshot(),
  });

  const assets = useWorkspaceStore((state) => state.assets);
  const clips = useWorkspaceStore((state) => state.clips);
  const storyboard = useWorkspaceStore((state) => state.storyboard);
  const chatTurns = useWorkspaceStore((state) => state.chatTurns);
  const loadState = useWorkspaceStore((state) => state.loadState);
  const chatState = useWorkspaceStore((state) => state.chatState);
  const activeTask = useWorkspaceStore((state) => state.activeTask);
  const workflowState = useWorkspaceStore((state) => state.workflowState);
  const exportResult = useWorkspaceStore((state) => state.exportResult);
  const eventStreamState = useWorkspaceStore((state) => state.eventStreamState);
  const reconnectState = useWorkspaceStore((state) => state.reconnectState);
  const lastError = useWorkspaceStore((state) => state.lastError);
  const initializeWorkspace = useWorkspaceStore((state) => state.initializeWorkspace);
  const uploadAssets = useWorkspaceStore((state) => state.uploadAssets);
  const sendChat = useWorkspaceStore((state) => state.sendChat);
  const exportProject = useWorkspaceStore((state) => state.exportProject);
  const clearLastError = useWorkspaceStore((state) => state.clearLastError);

  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const latestAssistantIdRef = useRef<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scrubberTrackRef = useRef<HTMLDivElement | null>(null);

  const totalDurationSec = storyboard.reduce(
    (total, scene) => total + parseSceneDurationSeconds(scene.duration),
    0
  );
  const safeTotalDurationSec = Math.max(1, totalDurationSec);
  const sessionLabel = `Session #${sessionId.slice(-8).toUpperCase()}`;
  const eventStreamVisualState = toEventStreamVisualState(eventStreamState);
  const isLoadingWorkspace = loadState === "loading";
  const isThinking = chatState === "responding";
  const isMediaProcessing = activeTask?.type === "ingest" && activeTask.status === "running";
  const isExporting = activeTask?.type === "render" && activeTask.status === "running";
  const mediaStatusText =
    isMediaProcessing || isExporting ? activeTask?.message ?? null : null;
  const canSendChat =
    !isEditLocked &&
    assets.length > 0 &&
    chatState !== "responding" &&
    workflowState !== "rendering" &&
    !(activeTask && activeTask.status === "running");
  const canUploadAssets = !isEditLocked && workflowState !== "rendering";
  const canExport =
    workflowState === "ready" &&
    !isEditLocked &&
    !(activeTask && activeTask.status === "running");

  const reconnectingPill: EventStreamVisualState = useMemo(() => {
    if (reconnectState === "reconnecting") {
      return "checking";
    }
    return eventStreamVisualState;
  }, [reconnectState, eventStreamVisualState]);

  const activeSceneIndex = useMemo(
    () =>
      previewSelection?.kind === "scene"
        ? storyboard.findIndex((scene) => scene.id === previewSelection.sceneId)
        : -1,
    [previewSelection, storyboard]
  );

  const selectedClip = useMemo(() => {
    if (previewSelection?.kind === "clip") {
      return clips.find((clip) => clip.id === previewSelection.clipId) ?? null;
    }
    if (previewSelection?.kind === "scene") {
      return clips[Math.max(activeSceneIndex, 0)] ?? null;
    }
    return null;
  }, [activeSceneIndex, clips, previewSelection]);

  const selectedAsset = useMemo(() => {
    if (previewSelection?.kind === "asset") {
      return assets.find((asset) => asset.id === previewSelection.assetId) ?? null;
    }
    if (selectedClip) {
      return assets.find((asset) => asset.name === selectedClip.parent) ?? null;
    }
    return assets[0] ?? null;
  }, [assets, previewSelection, selectedClip]);

  const selectedPreviewSource = useMemo(() => {
    if (!selectedAsset) {
      return null;
    }
    return getProjectMediaSource(workspaceId, selectedAsset.name);
  }, [selectedAsset, workspaceId]);

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
    return thumbnailUrls[selectedAsset.name] ?? null;
  }, [selectedAsset, thumbnailUrls]);

  useEffect(() => {
    void initializeWorkspace(workspaceId, workspaceName);
  }, [initializeWorkspace, workspaceId, workspaceName]);

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
    let cancelled = false;
    async function generateThumbnails() {
      const updates: Record<string, string> = {};
      for (const asset of assets) {
        if (thumbnailUrls[asset.name]) {
          continue;
        }
        const source = getProjectMediaSource(workspaceId, asset.name);
        if (!source) {
          continue;
        }
        const thumbnailUrl = await createThumbnailFromMediaUrl(source.url);
        if (cancelled || !thumbnailUrl) {
          continue;
        }
        updates[asset.name] = thumbnailUrl;
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
  }, [assets, thumbnailUrls, workspaceId]);

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
    let disposed = false;
    let polling = false;
    let intervalId: number | null = null;

    async function pollHealth() {
      if (disposed || polling) {
        return;
      }
      polling = true;
      try {
        const [coreSnapshot, serverSnapshot] = await Promise.all([
          probeServiceHealth("core"),
          probeServiceHealth("server"),
        ]);
        if (!disposed) {
          setServiceHealth({
            core: coreSnapshot,
            server: serverSnapshot,
          });
        }
      } finally {
        polling = false;
      }
    }

    void pollHealth();
    intervalId = window.setInterval(() => {
      void pollHealth();
    }, HEALTH_POLL_INTERVAL_MS);

    return () => {
      disposed = true;
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
    };
  }, []);

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

  async function handleAssetBrowse() {
    await uploadAssets({ shouldPickMedia: true });
  }

  async function handleAssetDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsAssetDropHovering(false);
    const droppedPath = extractDroppedPath(event);
    const droppedFiles = extractDroppedFiles(event);
    if (!droppedPath && droppedFiles.length === 0) {
      return;
    }
    await uploadAssets({
      folderPath: droppedPath ?? undefined,
      files: droppedFiles,
    });
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
            <span className="brand-icon-shell">
              <Sparkles size={14} />
            </span>
            <h1>EntroCut</h1>
          </div>
          <div className="topbar-divider" />
          <div className="workspace-path">
            <span>Workspace</span>
            <ChevronRight size={12} />
            <span className="workspace-path-current">{workspaceName}</span>
          </div>
        </div>

        <div className="topbar-right">
          <div className="health-cluster">
            <span
              className={`health-pill health-pill-${serviceHealth.core.state}`}
              title={buildHealthTitle("core", serviceHealth.core)}
            >
              <span className={`health-dot health-dot-${serviceHealth.core.state}`} />
              core {healthStateLabel(serviceHealth.core.state)}
            </span>
            <span
              className={`health-pill health-pill-${reconnectingPill}`}
              title={`core event stream ${eventStreamState}${reconnectState !== "idle" ? ` - reconnecting` : ""}`}
            >
              <span className={`health-dot health-dot-${reconnectingPill}`} />
              ws {reconnectState === "reconnecting" ? "reconnecting" : eventStreamState}
            </span>
            <span
              className={`health-pill health-pill-${serviceHealth.server.state}`}
              title={buildHealthTitle("server", serviceHealth.server)}
            >
              <span className={`health-dot health-dot-${serviceHealth.server.state}`} />
              server {healthStateLabel(serviceHealth.server.state)}
            </span>
            {isMediaProcessing ? <span className="lock-pill">{mediaStatusText ?? "MEDIA PROCESSING"}</span> : null}
            {isExporting ? <span className="lock-pill">EXPORTING</span> : null}
            {isEditLocked && !isExporting ? <span className="lock-pill">EDIT LOCKED</span> : null}
          </div>
          <button className="icon-btn topbar-icon-btn" type="button" aria-label="settings">
            <Settings size={18} />
          </button>
          <button
            className="export-btn"
            type="button"
            onClick={handleExport}
            disabled={isExporting || isMediaProcessing}
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
                <div
                  className={`asset-upload-entry ${isAssetDropHovering ? "is-hovering" : ""} ${
                    !canUploadAssets ? "is-disabled" : ""
                  }`}
                  onClick={() => {
                    if (canUploadAssets) {
                      void handleAssetBrowse();
                    }
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setIsAssetDropHovering(true);
                  }}
                  onDragLeave={() => setIsAssetDropHovering(false)}
                  onDrop={handleAssetDrop}
                >
                  <Upload size={14} />
                  <span>Upload videos or drop folder here</span>
                </div>

                {assets.length === 0 ? (
                  <EmptyMediaGuidance
                    onUploadClick={handleAssetBrowse}
                    isDisabled={!canUploadAssets}
                  />
                ) : (
                  <div className="asset-grid">
                    {assets.map((asset) => (
                      <article
                        key={asset.id}
                        className={`asset-card ${
                          previewSelection?.kind === "asset" && previewSelection.assetId === asset.id ? "is-active" : ""
                        }`}
                        onClick={() => {
                          setPreviewSelection({ kind: "asset", assetId: asset.id });
                          setCurrentTimeSec(0);
                          setIsPlaying(true);
                        }}
                      >
                        <div className="asset-thumb">
                          {thumbnailUrls[asset.name] ? (
                            <img src={thumbnailUrls[asset.name]} alt={asset.name} className="asset-thumb-image" />
                          ) : (
                            <Film size={14} />
                          )}
                          <span>{asset.duration}</span>
                        </div>
                        <p title={asset.name}>{asset.name}</p>
                      </article>
                    ))}
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
                        {thumbnailUrls[clip.parent] ? (
                          <img src={thumbnailUrls[clip.parent]} alt={clip.parent} className="clip-thumb-image" />
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
            <span className="session-badge">{sessionLabel}</span>
          </div>

          <div className="chat-thread">
            {chatTurns.map((turn) => (
              <div key={turn.id} className={turn.role === "user" ? "chat-row chat-row-user" : "chat-row"}>
                {turn.role === "user" ? (
                  <div className="chat-bubble">{turn.content}</div>
                ) : (
                  <article className="decision-card">
                    <header>
                      <Sparkles size={14} />
                      <span>AI DECISION</span>
                    </header>
                    {isDecisionTurn(turn) ? (
                      <div className="decision-content">
                        <p>{turn.reasoning_summary}</p>
                        <div className="decision-ops">
                          {turn.ops.map((op) => (
                            <div
                              key={`${op.action}_${op.target}_${op.summary}`}
                              className="decision-op"
                            >
                              <span />
                              <code>{formatOperation(op)}</code>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </article>
                )}
              </div>
            ))}

            {isMediaProcessing ? (
              <div className="thinking-box">
                <Loader2 size={16} />
                <span>{mediaStatusText ?? "Processing media..."}</span>
              </div>
            ) : null}

            {isThinking ? (
              <div className="thinking-box">
                <Loader2 size={16} />
                <span>Analyzing footage and generating edit...</span>
              </div>
            ) : null}

            {!isThinking && !isMediaProcessing && !isLoadingWorkspace && chatTurns.length === 0 ? (
              <div className="thinking-box">
                <Sparkles size={16} />
                <span>Send a prompt to start AI editing.</span>
              </div>
            ) : null}
            {/* 无素材时的提示 */}
            {assets.length === 0 && chatTurns.length === 0 && !isThinking && !isMediaProcessing && !isLoadingWorkspace && (
              <div className="chat-limitation-notice">
                <Sparkles size={14} />
                <span>AI editing is limited without media. Upload videos first.</span>
              </div>
            )}
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
                assets.length === 0
                  ? "Upload media first to enable full AI editing, or describe your idea..."
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
                  <span>PREVIEW SOURCE UNAVAILABLE</span>
                </div>
              )}
              <div className="timecode">{formatTimecode(currentTimeSec)}</div>
              {!isThinking && !isMediaProcessing && !isLoadingWorkspace ? (
                <div className="preview-meta">
                  <strong>{previewTitle}</strong>
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
                    {thumbnailUrls[(clips[index] ?? selectedClip)?.parent ?? ""] ? (
                      <img
                        src={thumbnailUrls[(clips[index] ?? selectedClip)?.parent ?? ""]}
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
