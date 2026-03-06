import { useEffect, useRef, useState, type DragEvent } from "react";
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

function parseSceneDurationSeconds(duration: string): number {
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

function extractDroppedPath(event: DragEvent<HTMLDivElement>): string | null {
  const firstFile = event.dataTransfer.files?.item(0);
  const electronPath = (firstFile as File & { path?: string } | null)?.path;
  return typeof electronPath === "string" && electronPath.trim().length > 0 ? electronPath : null;
}

function extractDroppedFiles(event: DragEvent<HTMLDivElement>): File[] {
  return Array.from(event.dataTransfer.files ?? []).filter((file) => file.size > 0);
}

function WorkspacePage({ workspaceId, workspaceName, onBackLaunchpad }: WorkspacePageProps) {
  const [sessionId] = useState(() => getOrCreateSessionId(workspaceId));
  const [promptText, setPromptText] = useState("");
  const [mediaTab, setMediaTab] = useState<MediaTab>("clips");
  const [highlightItem, setHighlightItem] = useState("");
  const [leftWidth, setLeftWidth] = useState(280);
  const [midWidth, setMidWidth] = useState(400);
  const [dragging, setDragging] = useState<DraggingTarget>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isEditLocked, setIsEditLocked] = useState(false);
  const [reasoningOverlay, setReasoningOverlay] = useState<string | null>(null);
  const [patchPulseId, setPatchPulseId] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeSec, setCurrentTimeSec] = useState(12);
  const [isAssetDropHovering, setIsAssetDropHovering] = useState(false);
  const [serviceHealth, setServiceHealth] = useState<Record<ServiceTarget, ServiceHealthSnapshot>>({
    core: createInitialHealthSnapshot(),
    server: createInitialHealthSnapshot(),
  });

  const assets = useWorkspaceStore((state) => state.assets);
  const clips = useWorkspaceStore((state) => state.clips);
  const storyboard = useWorkspaceStore((state) => state.storyboard);
  const chatTurns = useWorkspaceStore((state) => state.chatTurns);
  const isLoadingWorkspace = useWorkspaceStore((state) => state.isLoadingWorkspace);
  const isThinking = useWorkspaceStore((state) => state.isThinking);
  const isMediaProcessing = useWorkspaceStore((state) => state.isMediaProcessing);
  const mediaStatusText = useWorkspaceStore((state) => state.mediaStatusText);
  const lastError = useWorkspaceStore((state) => state.lastError);
  const initializeWorkspace = useWorkspaceStore((state) => state.initializeWorkspace);
  const uploadAssets = useWorkspaceStore((state) => state.uploadAssets);
  const sendChat = useWorkspaceStore((state) => state.sendChat);
  const clearLastError = useWorkspaceStore((state) => state.clearLastError);

  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const latestAssistantIdRef = useRef<string | null>(null);

  const totalDurationSec = storyboard.reduce(
    (total, scene) => total + parseSceneDurationSeconds(scene.duration),
    0
  );
  const safeTotalDurationSec = Math.max(1, totalDurationSec);
  const playbackProgress = Math.min(1, currentTimeSec / safeTotalDurationSec);
  const sessionLabel = `Session #${sessionId.slice(-8).toUpperCase()}`;

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
    if (!isPlaying || isThinking || isMediaProcessing) {
      return;
    }
    const timer = window.setInterval(() => {
      setCurrentTimeSec((previous) => {
        const next = previous + 0.25;
        if (next >= safeTotalDurationSec) {
          setIsPlaying(false);
          return safeTotalDurationSec;
        }
        return next;
      });
    }, 250);

    return () => window.clearInterval(timer);
  }, [isPlaying, isThinking, isMediaProcessing, safeTotalDurationSec]);

  useEffect(() => {
    if (currentTimeSec > safeTotalDurationSec) {
      setCurrentTimeSec(safeTotalDurationSec);
    }
  }, [currentTimeSec, safeTotalDurationSec]);

  function handleExport() {
    if (isExporting) {
      return;
    }
    setIsExporting(true);
    setIsEditLocked(true);
    setReasoningOverlay("Export started. Editing is locked.");

    window.setTimeout(() => {
      setIsExporting(false);
      setIsEditLocked(false);
      setReasoningOverlay("Export finished. Editing unlocked.");
      window.setTimeout(() => setReasoningOverlay(null), 1200);
    }, 2600);
  }

  function handleSuggestionPick(suggestion: string) {
    if (isThinking || isEditLocked) {
      return;
    }
    setPromptText(suggestion);
  }

  async function handleSendChat() {
    const trimmed = promptText.trim();
    if (!trimmed || isThinking || isEditLocked) {
      return;
    }
    setPromptText("");
    setIsPlaying(false);
    await sendChat(trimmed);
  }

  function handleTogglePlay() {
    if (isThinking || isMediaProcessing) {
      return;
    }
    if (currentTimeSec >= safeTotalDurationSec) {
      setCurrentTimeSec(0);
    }
    setIsPlaying((previous) => !previous);
  }

  function handleSceneSeek(sceneId: string, index: number) {
    if (isEditLocked) {
      return;
    }
    setHighlightItem(sceneId);
    const startSec = storyboard
      .slice(0, index)
      .reduce((total, scene) => total + parseSceneDurationSeconds(scene.duration), 0);
    setCurrentTimeSec(startSec);
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
              className={`health-pill health-pill-${serviceHealth.server.state}`}
              title={buildHealthTitle("server", serviceHealth.server)}
            >
              <span className={`health-dot health-dot-${serviceHealth.server.state}`} />
              server {healthStateLabel(serviceHealth.server.state)}
            </span>
            {isMediaProcessing ? <span className="lock-pill">{mediaStatusText ?? "MEDIA PROCESSING"}</span> : null}
            {isEditLocked ? <span className="lock-pill">EDIT LOCKED</span> : null}
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
                    isEditLocked ? "is-disabled" : ""
                  }`}
                  onClick={() => {
                    if (!isEditLocked) {
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

                <div className="asset-grid">
                  {assets.map((asset) => (
                    <article key={asset.id} className="asset-card">
                      <div className="asset-thumb">
                        <Film size={14} />
                        <span>{asset.duration}</span>
                      </div>
                      <p title={asset.name}>{asset.name}</p>
                    </article>
                  ))}
                  {assets.length === 0 ? (
                    <article className="asset-card asset-card-empty">
                      <p>No assets yet. Upload videos to start processing.</p>
                    </article>
                  ) : null}
                </div>
              </>
            ) : (
              <div className="clip-list">
                {clips.map((clip) => (
                  <article key={clip.id} className="clip-card">
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
                            <div key={op} className="decision-op">
                              <span />
                              <code>{op}</code>
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
            <div ref={chatEndRef} />
          </div>

          <div className="suggestion-row">
            {SUGGESTION_CHIPS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => handleSuggestionPick(suggestion)}
                disabled={isThinking || isEditLocked}
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
              disabled={isThinking || isEditLocked}
              placeholder="Describe your edit..."
            />
            <button
              type="button"
              onClick={() => void handleSendChat()}
              disabled={!promptText.trim() || isThinking || isEditLocked}
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
              ) : (
                <div className="preview-center">
                  <Film size={40} />
                  <span>PREVIEW STAGE</span>
                </div>
              )}
              <div className="timecode">{formatTimecode(currentTimeSec)}</div>
              {reasoningOverlay ? <div className="reasoning-overlay">{reasoningOverlay}</div> : null}
            </div>

            <div className="scrubber">
              <button type="button" className="icon-btn" aria-label="play" onClick={handleTogglePlay}>
                <Play size={14} />
              </button>
              <div className="scrubber-track">
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
                {formatClock(currentTimeSec)} / {formatClock(safeTotalDurationSec)}
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
