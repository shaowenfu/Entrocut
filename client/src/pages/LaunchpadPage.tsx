import { useMemo, useState, type DragEvent } from "react";
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
import { MOCK_LAUNCHPAD_HINTS, MOCK_LAUNCHPAD_PROJECTS } from "../mocks/launchpad";

type LaunchpadPageProps = {
  onOpenWorkspace: (workspaceName: string) => void;
};

function LaunchpadPage({ onOpenWorkspace }: LaunchpadPageProps) {
  const [prompt, setPrompt] = useState("");
  const [isDropHovering, setIsDropHovering] = useState(false);
  const [hintIndex, setHintIndex] = useState(0);

  const promptPlaceholder = useMemo(
    () => `Or type an idea: "${MOCK_LAUNCHPAD_HINTS[hintIndex]}"`,
    [hintIndex]
  );

  function handleCreateFromPrompt() {
    if (!prompt.trim()) {
      return;
    }
    // TODO(api): 改为真实 `POST /api/v1/projects` 后再跳转到 Workspace。
    onOpenWorkspace(prompt.trim().slice(0, 32));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDropHovering(false);
    // TODO(api): 改为真实 `POST /api/v1/projects/import`，并上传本地索引任务。
    onOpenWorkspace("Imported Workspace");
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

        <button className="launchpad-search" type="button">
          <Search size={14} />
          <span>Search projects...</span>
          <kbd>Ctrl+K</kbd>
        </button>

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
              className="intent-drop-surface"
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
                onFocus={() => setHintIndex((current) => (current + 1) % MOCK_LAUNCHPAD_HINTS.length)}
              />
              <button
                type="button"
                className={prompt.trim() ? "is-active" : ""}
                onClick={handleCreateFromPrompt}
                aria-label="create workspace"
              >
                <Plus size={16} />
              </button>
            </div>
          </div>

          <div className="intent-actions">
            <button type="button" onClick={() => onOpenWorkspace("Untitled Sequence")}>
              <FileVideo size={14} />
              <span>Empty Sequence</span>
            </button>
            <button type="button">
              <Cloud size={14} />
              <span>Connect Drive</span>
            </button>
          </div>
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
            {MOCK_LAUNCHPAD_PROJECTS.map((project) => (
              <article key={project.id} className="recent-card" onClick={() => onOpenWorkspace(project.title)}>
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
