import { useEffect, useRef, useState } from "react";
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

type WorkspacePageProps = {
  workspaceName: string;
  onBackLaunchpad?: () => void;
};

type MediaTab = "assets" | "clips";
type DraggingTarget = "left" | "mid" | null;

interface AssetItem {
  id: string;
  name: string;
  duration: string;
  type: "video" | "audio";
}

interface ClipItem {
  id: string;
  parent: string;
  start: string;
  end: string;
  score: string;
  desc: string;
  thumbClass: string;
}

interface StoryboardScene {
  id: string;
  title: string;
  duration: string;
  intent: string;
  colorClass: string;
  bgClass: string;
}

interface UserTurn {
  id: string;
  role: "user";
  content: string;
}

interface AssistantDecisionTurn {
  id: string;
  role: "assistant";
  type: "decision";
  decision_type: "UPDATE_PROJECT_CONTRACT" | "APPLY_PATCH_ONLY";
  reasoning_summary: string;
  ops: string[];
}

type ChatTurn = UserTurn | AssistantDecisionTurn;

// TODO(api): 使用真实素材契约替换本地 mock（来自 `/api/v1/project/{id}`）。
const ASSETS: AssetItem[] = [
  { id: "a1", name: "A001_C005_10242E.mp4", duration: "00:15", type: "video" },
  { id: "a2", name: "DJI_0042_ProRes.mov", duration: "01:20", type: "video" },
  { id: "a3", name: "Ambient_Wind_01.wav", duration: "03:00", type: "audio" },
  { id: "a4", name: "A002_C011_1025.mp4", duration: "00:08", type: "video" },
];

// TODO(api): 使用真实语义检索结果替换本地 mock（来自 `POST /api/v1/chat`）。
const CLIPS: ClipItem[] = [
  {
    id: "c1",
    parent: "a1",
    start: "00:00",
    end: "00:05",
    score: "98%",
    thumbClass: "thumb-blue",
    desc: "Clear sky, stable pan",
  },
  {
    id: "c2",
    parent: "a2",
    start: "00:12",
    end: "00:18",
    score: "85%",
    thumbClass: "thumb-indigo",
    desc: "Drone fast approach",
  },
  {
    id: "c3",
    parent: "a2",
    start: "00:45",
    end: "00:52",
    score: "92%",
    thumbClass: "thumb-purple",
    desc: "Subject looking at horizon",
  },
  {
    id: "c4",
    parent: "a4",
    start: "00:01",
    end: "00:06",
    score: "88%",
    thumbClass: "thumb-teal",
    desc: "Snow detail close-up",
  },
];

// TODO(api): 使用真实 `EntroVideoProject.timeline` 映射替换本地 mock。
const INITIAL_STORYBOARD: StoryboardScene[] = [
  {
    id: "sb1",
    title: "Establishing",
    duration: "5s",
    intent: "Show environmental scale",
    colorClass: "scene-blue",
    bgClass: "scene-bg-blue",
  },
  {
    id: "sb2",
    title: "Hero Reveal",
    duration: "12s",
    intent: "Focus on subject emotion",
    colorClass: "scene-indigo",
    bgClass: "scene-bg-indigo",
  },
  {
    id: "sb3",
    title: "Action Pan",
    duration: "3s",
    intent: "Increase pacing to beat",
    colorClass: "scene-purple",
    bgClass: "scene-bg-purple",
  },
];

// TODO(api): 使用真实会话历史替换本地 mock（来自 `POST /api/v1/chat`）。
const INITIAL_CHAT: ChatTurn[] = [
  {
    id: "msg1",
    role: "user",
    content: "帮我根据现有素材，粗剪一个关于雪山徒步的 20 秒开场。",
  },
  {
    id: "msg2",
    role: "assistant",
    type: "decision",
    decision_type: "UPDATE_PROJECT_CONTRACT",
    reasoning_summary:
      "我已扫描素材库，提取了 3 段高分风景与人物特写片段，并按逻辑组装了分镜序列。",
    ops: ["Added 3 retrieved clips", "Matched duration to 20s"],
  },
];

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

function WorkspacePage({ workspaceName, onBackLaunchpad }: WorkspacePageProps) {
  const [sessionId] = useState(() =>
    getOrCreateSessionId(`proj_${workspaceName.replace(/[^a-zA-Z0-9]+/g, "_").toLowerCase()}`)
  );
  const [isThinking, setIsThinking] = useState(false);
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>(INITIAL_CHAT);
  const [storyboard, setStoryboard] = useState<StoryboardScene[]>(INITIAL_STORYBOARD);
  const [promptText, setPromptText] = useState("");
  const [mediaTab, setMediaTab] = useState<MediaTab>("clips");
  const [highlightItem, setHighlightItem] = useState("sb2");
  const [leftWidth, setLeftWidth] = useState(280);
  const [midWidth, setMidWidth] = useState(400);
  const [dragging, setDragging] = useState<DraggingTarget>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [isEditLocked, setIsEditLocked] = useState(false);
  const [reasoningOverlay, setReasoningOverlay] = useState<string | null>(null);
  const [patchPulseId, setPatchPulseId] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeSec, setCurrentTimeSec] = useState(12);
  const [serviceHealth, setServiceHealth] = useState<Record<ServiceTarget, ServiceHealthSnapshot>>({
    core: createInitialHealthSnapshot(),
    server: createInitialHealthSnapshot(),
  });

  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const totalDurationSec = storyboard.reduce(
    (total, scene) => total + parseSceneDurationSeconds(scene.duration),
    0
  );
  const safeTotalDurationSec = Math.max(1, totalDurationSec);
  const playbackProgress = Math.min(1, currentTimeSec / safeTotalDurationSec);
  const sessionLabel = `Session #${sessionId.slice(-8).toUpperCase()}`;

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatTurns, isThinking]);

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
    if (!isPlaying || isThinking) {
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
  }, [isPlaying, isThinking, safeTotalDurationSec]);

  useEffect(() => {
    if (currentTimeSec > safeTotalDurationSec) {
      setCurrentTimeSec(safeTotalDurationSec);
    }
  }, [currentTimeSec, safeTotalDurationSec]);

  function showReasoningOverlay(message: string, durationMs = 2200) {
    setReasoningOverlay(message);
    window.setTimeout(() => setReasoningOverlay(null), durationMs);
  }

  function handleExport() {
    if (isExporting) {
      return;
    }
    setIsExporting(true);
    setIsEditLocked(true);
    showReasoningOverlay("Export started. Editing is locked.", 1200);

    window.setTimeout(() => {
      setIsExporting(false);
      setIsEditLocked(false);
      showReasoningOverlay("Export finished. Editing unlocked.", 1200);
    }, 2600);
  }

  function handleSuggestionPick(suggestion: string) {
    if (isThinking || isEditLocked) {
      return;
    }
    setPromptText(suggestion);
  }

  function handleSendChat() {
    const trimmed = promptText.trim();
    if (!trimmed || isThinking || isEditLocked) {
      return;
    }

    const userMessage: UserTurn = {
      id: `${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    setChatTurns((previous) => [...previous, userMessage]);
    setPromptText("");
    setIsThinking(true);
    setIsPlaying(false);

    window.setTimeout(() => {
      setIsThinking(false);
      const newStoryboardId = `sb${Date.now()}`;
      const aiMessage: AssistantDecisionTurn = {
        id: `${Date.now() + 1}`,
        role: "assistant",
        type: "decision",
        decision_type: "APPLY_PATCH_ONLY",
        reasoning_summary:
          "根据你的要求，我替换了第二个镜头的氛围，引入了雪地细节特写，节奏更紧凑。",
        ops: ["Replaced Hero Reveal with Close-up"],
      };
      setChatTurns((previous) => [...previous, aiMessage]);

      setStoryboard((previous) => {
        const next = [...previous];
        if (next[1]) {
          next[1] = {
            id: newStoryboardId,
            title: "Detail Close-up",
            duration: "8s",
            intent: "Enhance tactile feeling of snow",
            colorClass: "scene-cyan",
            bgClass: "scene-bg-cyan",
          };
        }
        return next;
      });

      setHighlightItem(newStoryboardId);
      setPatchPulseId(newStoryboardId);
      window.setTimeout(() => setPatchPulseId(null), 1200);
      showReasoningOverlay(aiMessage.reasoning_summary, 2600);
    }, 1800);
  }

  function handleTogglePlay() {
    if (isThinking) {
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
            {isEditLocked ? <span className="lock-pill">EDIT LOCKED</span> : null}
          </div>
          <button className="icon-btn topbar-icon-btn" type="button" aria-label="settings">
            <Settings size={18} />
          </button>
          <button
            className="export-btn"
            type="button"
            onClick={handleExport}
            disabled={isExporting}
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
              <div className="asset-grid">
                {ASSETS.map((asset) => (
                  <article key={asset.id} className="asset-card">
                    <div className="asset-thumb">
                      <Film size={14} />
                      <span>{asset.duration}</span>
                    </div>
                    <p title={asset.name}>{asset.name}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="clip-list">
                {CLIPS.map((clip) => (
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
              </div>
            )}
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
              <div
                key={turn.id}
                className={turn.role === "user" ? "chat-row chat-row-user" : "chat-row"}
              >
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

            {isThinking ? (
              <div className="thinking-box">
                <Loader2 size={16} />
                <span>Analyzing footage and generating edit...</span>
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
                  handleSendChat();
                }
              }}
              disabled={isThinking || isEditLocked}
              placeholder="Describe your edit..."
            />
            <button
              type="button"
              onClick={handleSendChat}
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
              {isThinking ? (
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
                  className={`story-card ${scene.bgClass} ${
                    highlightItem === scene.id ? "active" : ""
                  } ${patchPulseId === scene.id ? "patch-pulse" : ""}`}
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

              <div className="story-end">
                <ListVideo size={20} />
                <span>END</span>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default WorkspacePage;
