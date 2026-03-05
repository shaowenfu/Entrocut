import { useEffect, useMemo, useState, type DragEvent } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Clock3,
  Cloud,
  FileVideo,
  FolderUp,
  HardDrive,
  MoreVertical,
  Plus,
  Search,
  Sparkles,
} from "lucide-react";
import { useLaunchpadStore } from "../store/useLaunchpadStore";

const PROMPT_HINTS = [
  "A fast-paced recap of my Tokyo trip",
  "一个 30 秒的产品开场，节奏紧凑",
  "生成旅行 vlog 的第一版粗剪",
];

function LaunchpadPage() {
  const [prompt, setPrompt] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [isDropHovering, setIsDropHovering] = useState(false);
  const [hintIndex, setHintIndex] = useState(0);
  const recentProjects = useLaunchpadStore((state) => state.recentProjects);
  const isLoadingProjects = useLaunchpadStore((state) => state.isLoadingProjects);
  const isImporting = useLaunchpadStore((state) => state.isImporting);
  const isCreating = useLaunchpadStore((state) => state.isCreating);
  const lastError = useLaunchpadStore((state) => state.lastError);
  const fetchRecentProjects = useLaunchpadStore((state) => state.fetchRecentProjects);
  const importLocalFolder = useLaunchpadStore((state) => state.importLocalFolder);
  const createEmptyProject = useLaunchpadStore((state) => state.createEmptyProject);
  const createProjectFromPrompt = useLaunchpadStore((state) => state.createProjectFromPrompt);
  const openWorkspace = useLaunchpadStore((state) => state.openWorkspace);
  const clearLastError = useLaunchpadStore((state) => state.clearLastError);

  useEffect(() => {
    void fetchRecentProjects();
  }, [fetchRecentProjects]);

  const displayProjects = useMemo(() => {
    const keyword = searchQuery.trim().toLowerCase();
    if (!keyword) {
      return recentProjects;
    }
    return recentProjects.filter((project) => project.title.toLowerCase().includes(keyword));
  }, [recentProjects, searchQuery]);

  const promptPlaceholder = useMemo(
    () => `Or type an idea: "${PROMPT_HINTS[hintIndex]}"`,
    [hintIndex]
  );

  async function handleCreateFromPrompt() {
    if (!prompt.trim()) {
      return;
    }
    try {
      await createProjectFromPrompt(prompt.trim());
      setPrompt("");
    } catch {
      // 错误已由 store 收敛到 lastError。
    }
  }

  function extractDroppedPath(event: DragEvent<HTMLDivElement>): string | null {
    const firstFile = event.dataTransfer.files?.item(0);
    const electronPath = (firstFile as File & { path?: string } | null)?.path;
    return typeof electronPath === "string" && electronPath.trim().length > 0 ? electronPath : null;
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDropHovering(false);
    const droppedPath = extractDroppedPath(event);
    await importLocalFolder(droppedPath ?? undefined);
  }

  return (
    <div className="launchpad-root">
      <header className="launchpad-topbar">
        <div className="launchpad-brand">
          <span className="launchpad-brand-icon">
            <Sparkles size={15} />
          </span>
          <span>EntroCut</span>
        </div>

        <label className="launchpad-search">
          <Search size={14} />
          <input
            type="text"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search projects..."
          />
          <kbd>Ctrl+K</kbd>
        </label>

        <div className="launchpad-user">ME</div>
      </header>

      <main className="launchpad-main">
        <section className="intent-zone">
          <div className="intent-heading">
            <h1>早上好。</h1>
            <p>描述你的想法，或直接拖入素材文件夹来唤醒 AI Copilot。</p>
          </div>

          <div className={`intent-drop-shell ${isDropHovering ? "is-hovering" : ""}`}>
            <div
              className={`intent-drop-surface ${isCreating || isImporting ? "is-disabled" : ""}`}
              onClick={() => {
                if (isCreating || isImporting) {
                  return;
                }
                void importLocalFolder();
              }}
              onDragOver={(event) => {
                event.preventDefault();
                setIsDropHovering(true);
              }}
              onDragLeave={() => setIsDropHovering(false)}
              onDrop={handleDrop}
            >
              <div className="intent-drop-icon">
                <FolderUp size={22} />
              </div>
              <h3>Drop media folder here</h3>
              <p>or click to browse local files</p>
            </div>

            <div className="intent-input-row">
              <Sparkles size={14} />
              <input
                type="text"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={promptPlaceholder}
                onFocus={() => setHintIndex((current) => (current + 1) % PROMPT_HINTS.length)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void handleCreateFromPrompt();
                  }
                }}
                disabled={isCreating || isImporting}
              />
              <button
                type="button"
                className={prompt.trim() ? "is-active" : ""}
                onClick={() => void handleCreateFromPrompt()}
                aria-label="create workspace"
                disabled={isCreating || isImporting}
              >
                <Plus size={16} />
              </button>
            </div>
          </div>

          <div className="intent-actions">
            <button type="button" onClick={() => void createEmptyProject()} disabled={isCreating || isImporting}>
              <FileVideo size={14} />
              <span>Empty Sequence</span>
            </button>
            <button type="button" onClick={() => void importLocalFolder()} disabled={isCreating || isImporting}>
              <Cloud size={14} />
              <span>Browse Folder</span>
            </button>
          </div>
          {lastError ? (
            <p className="launchpad-error-banner" role="alert" onClick={clearLastError}>
              {lastError.code}: {lastError.message}
            </p>
          ) : null}
        </section>

        <section className="recent-zone">
          <div className="recent-head">
            <h2>
              <Clock3 size={15} />
              <span>Recent Workspaces</span>
            </h2>
            <button type="button">View All</button>
          </div>

          <div className="recent-grid">
            {displayProjects.map((project) => (
              <article key={project.id} className="recent-card" onClick={() => openWorkspace(project)}>
                <div className={`recent-thumb ${project.thumbnailClassName}`}>
                  <div className="recent-thumb-top">
                    <span className="storage-pill">
                      {project.storageType === "cloud" ? <Cloud size={10} /> : <HardDrive size={10} />}
                      {project.storageType === "cloud" ? "Cloud Synced" : "Local Draft"}
                    </span>
                    <button type="button" onClick={(event) => event.stopPropagation()} aria-label="more">
                      <MoreVertical size={13} />
                    </button>
                  </div>
                  <h3>{project.title}</h3>
                </div>

                <div className="recent-meta">
                  <div className="recent-meta-top">
                    <span>{project.lastActiveText}</span>
                    <span className="ai-status">
                      <CheckCircle2 size={10} />
                      {project.aiStatus}
                    </span>
                  </div>
                  <p>
                    <Sparkles size={12} />
                    <span>
                      <em>Last AI Edit:</em>
                      {project.lastAiEdit}
                    </span>
                  </p>
                </div>
              </article>
            ))}

            {isLoadingProjects ? (
              <article className="archive-card" aria-label="loading projects">
                <span>Loading projects...</span>
              </article>
            ) : null}

            {!isLoadingProjects && displayProjects.length === 0 ? (
              <article className="archive-card" aria-label="empty projects">
                <span>No projects</span>
              </article>
            ) : null}

            <button className="archive-card" type="button">
              <ChevronRight size={20} />
              <span>View Archive</span>
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}

export default LaunchpadPage;
