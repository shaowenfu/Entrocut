import { useEffect, useMemo, useState, type DragEvent } from "react";
import {
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Cloud,
  FileVideo,
  FolderUp,
  HardDrive,
  ImagePlus,
  Pencil,
  Plus,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import AccountMenu from "../components/account/AccountMenu";
import { BrandIcon } from "../components/icons/BrandIcon";
import { useLaunchpadStore } from "../store/useLaunchpadStore";
import {
  isElectronEnvironment,
  toDesktopMediaFileReferences,
  type MediaPickMode,
} from "../services/electronBridge";
import "../styles/launchpad.css";

const PROMPT_HINTS = [
  "A fast-paced recap of my Tokyo trip",
  "一个 30 秒的产品开场，节奏紧凑",
  "生成旅行 vlog 的第一版粗剪",
];

const COVER_STORAGE_KEY = "entrocut.launchpad.workspaceCovers";

function readStoredCovers(): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(COVER_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as Record<string, string>) : {};
  } catch {
    return {};
  }
}

function persistStoredCovers(covers: Record<string, string>) {
  try {
    window.localStorage.setItem(COVER_STORAGE_KEY, JSON.stringify(covers));
  } catch {
    // 封面是纯 UI 增强，localStorage 写入失败时不阻塞打开 Workspace。
  }
}

function LaunchpadPage() {
  const [prompt, setPrompt] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [isDropHovering, setIsDropHovering] = useState(false);
  const [isMediaPickerOpen, setIsMediaPickerOpen] = useState(false);
  const [hintIndex, setHintIndex] = useState(0);
  const [workspaceCovers, setWorkspaceCovers] = useState<Record<string, string>>(() => readStoredCovers());
  const recentProjects = useLaunchpadStore((state) => state.recentProjects);
  const projectsLoadState = useLaunchpadStore((state) => state.projectsLoadState);
  const createState = useLaunchpadStore((state) => state.createState);
  const importState = useLaunchpadStore((state) => state.importState);
  const navigationState = useLaunchpadStore((state) => state.navigationState);
  const lastError = useLaunchpadStore((state) => state.lastError);
  const fetchRecentProjects = useLaunchpadStore((state) => state.fetchRecentProjects);
  const startWorkspaceFromLaunchpad = useLaunchpadStore((state) => state.startWorkspaceFromLaunchpad);
  const pickMediaAndStartWorkspace = useLaunchpadStore((state) => state.pickMediaAndStartWorkspace);
  const createEmptyProject = useLaunchpadStore((state) => state.createEmptyProject);
  const openWorkspace = useLaunchpadStore((state) => state.openWorkspace);
  const renameProject = useLaunchpadStore((state) => state.renameProject);
  const clearLastError = useLaunchpadStore((state) => state.clearLastError);

  const isLoadingProjects = projectsLoadState === "loading";
  const isCreating = createState === "creating";
  const isImporting = importState === "picking_media" || importState === "importing";
  const isBusy = isCreating || isImporting || navigationState === "entering_workspace";

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

  const isElectron = useMemo(() => isElectronEnvironment(), []);

  const dropZoneText = useMemo(() => {
    if (isElectron) {
      return {
        title: "Drop folder or videos here",
        subtitle: "or click to browse videos",
      };
    }
    return {
      title: "Drop videos here",
      subtitle: "or click to upload videos",
    };
  }, [isElectron]);

  async function handleCreateFromPrompt() {
    if (!prompt.trim()) {
      return;
    }
    try {
      await startWorkspaceFromLaunchpad({
        prompt: prompt.trim(),
      });
      setPrompt("");
    } catch {
      // 错误已由 store 收敛到 lastError。
    }
  }

  function extractDroppedFiles(event: DragEvent<HTMLDivElement>): File[] {
    return Array.from(event.dataTransfer.files ?? []).filter((file) => file.size > 0);
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDropHovering(false);
    const droppedFiles = extractDroppedFiles(event);
    const desktopFiles = toDesktopMediaFileReferences(droppedFiles);
    if (desktopFiles.length === 0) {
      return;
    }
    await startWorkspaceFromLaunchpad({
      files: desktopFiles,
      prompt: prompt.trim() || undefined,
    });
    setIsMediaPickerOpen(false);
    if (prompt.trim()) {
      setPrompt("");
    }
  }

  async function handleBrowseMedia(mode?: MediaPickMode) {
    const pickMode = mode ?? (isElectron ? "electron-files" : "browser-files");
    const projectId = await pickMediaAndStartWorkspace(prompt.trim() || undefined, pickMode);
    setIsMediaPickerOpen(false);
    if (projectId && prompt.trim()) {
      setPrompt("");
    }
  }

  function handleBrowseSurfaceClick() {
    if (isBusy) {
      return;
    }
    if (isElectron) {
      setIsMediaPickerOpen((current) => !current);
      return;
    }
    void handleBrowseMedia("browser-files");
  }

  async function handleRenameCommit(projectId: string, currentTitle: string) {
    const trimmed = renameDraft.trim();
    if (!trimmed || trimmed === currentTitle) {
      setRenamingProjectId(null);
      setRenameDraft("");
      return;
    }
    await renameProject(projectId, trimmed);
    setRenamingProjectId(null);
    setRenameDraft("");
  }

  function handleCoverUpload(workspaceId: string, file?: File) {
    if (!file || !file.type.startsWith("image/")) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        return;
      }
      setWorkspaceCovers((current) => {
        const next = {
          ...current,
          [workspaceId]: reader.result as string,
        };
        persistStoredCovers(next);
        return next;
      });
    };
    reader.readAsDataURL(file);
  }

  return (
    <div className="launchpad-root">
      <header className="launchpad-topbar">
        <div className="launchpad-brand">
          <BrandIcon size={22} />
          <span>EntroCut</span>
        </div>

        <label className="launchpad-search">
          <Search size={14} />
          <input
            type="text"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search workspaces..."
          />
          <kbd>Ctrl+K</kbd>
        </label>

        <AccountMenu variant="launchpad" />
      </header>

      <main className="launchpad-main">
        <section className="intent-zone">
          <div className="intent-heading">
            <h1>创建你的视频工作台</h1>
            <p>描述你的想法，或直接拖入素材文件夹/视频文件来唤醒 Cutroom 进行智能剪辑。</p>
          </div>

          <div className={`intent-drop-shell ${isDropHovering ? "is-hovering" : ""}`}>
            <div
              className={`intent-drop-surface ${isBusy ? "is-disabled" : ""}`}
              onClick={handleBrowseSurfaceClick}
              onDragOver={(event) => {
                event.preventDefault();
                setIsDropHovering(true);
              }}
              onDragLeave={() => setIsDropHovering(false)}
              onDrop={handleDrop}
            >
              <div className="intent-drop-icon">
                <FolderUp size={64} />
              </div>
              <h3>{dropZoneText.title}</h3>
              <p>{dropZoneText.subtitle}</p>
            </div>

            {isElectron && isMediaPickerOpen ? (
              <div className="intent-media-menu" role="menu" aria-label="media source">
                <button
                  type="button"
                  onClick={() => void handleBrowseMedia("electron-files")}
                  disabled={isBusy}
                  role="menuitem"
                >
                  <FileVideo size={15} />
                  <span>Select Videos</span>
                </button>
                <button
                  type="button"
                  onClick={() => void handleBrowseMedia("electron-folder")}
                  disabled={isBusy}
                  role="menuitem"
                >
                  <FolderUp size={15} />
                  <span>Select Folder</span>
                </button>
              </div>
            ) : null}

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
                <Plus size={18} />
              </button>
            </div>
          </div>

          <div className="intent-actions">
            <button type="button" onClick={() => void createEmptyProject()} disabled={isCreating || isImporting}>
              <FileVideo size={14} />
              <span>Empty Sequence</span>
            </button>
            <button
              type="button"
              onClick={() => {
                if (isElectron) {
                  setIsMediaPickerOpen((current) => !current);
                  return;
                }
                void handleBrowseMedia("browser-files");
              }}
              disabled={isCreating || isImporting}
              aria-expanded={isMediaPickerOpen}
            >
              <Cloud size={14} />
              <span>{isElectron ? "Browse Media" : "Upload Videos"}</span>
            </button>
          </div>
          {lastError ? (
            <p className="launchpad-error-banner" role="alert" onClick={clearLastError}>
              {lastError.code}: {lastError.message}
              {lastError.cause ? ` (${lastError.cause})` : ""}
              {lastError.requestId ? ` (request_id=${lastError.requestId})` : ""}
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
              <article
                key={project.id}
                className="recent-card"
                onClick={() => {
                  if (renamingProjectId !== project.id) {
                    openWorkspace(project);
                  }
                }}
              >
                <div className={`recent-thumb ${project.thumbnailClassName}`}>
                  {workspaceCovers[project.id] ? (
                    <img src={workspaceCovers[project.id]} alt="" className="recent-cover-image" />
                  ) : null}
                  <div className="recent-thumb-top">
                    <span className="storage-pill">
                      {project.storageType === "cloud" ? <Cloud size={10} /> : <HardDrive size={10} />}
                      {project.storageType === "cloud" ? "Cloud Synced" : "Local Draft"}
                    </span>
                    <div className="recent-thumb-actions">
                      <label
                        title="Upload cover"
                        aria-label="upload workspace cover"
                        role="button"
                        tabIndex={0}
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => {
                          if (event.key !== "Enter" && event.key !== " ") {
                            return;
                          }
                          event.preventDefault();
                          event.currentTarget.querySelector("input")?.click();
                        }}
                      >
                        <ImagePlus size={13} />
                        <input
                          type="file"
                          accept="image/*"
                          onChange={(event) => {
                            handleCoverUpload(project.id, event.target.files?.[0]);
                            event.target.value = "";
                          }}
                        />
                      </label>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setRenamingProjectId(project.id);
                          setRenameDraft(project.title);
                        }}
                        aria-label="rename workspace"
                        title="Rename workspace"
                      >
                        <Pencil size={13} />
                      </button>
                    </div>
                  </div>
                  {renamingProjectId === project.id ? (
                    <form
                      className="recent-title-editor"
                      onClick={(event) => event.stopPropagation()}
                      onSubmit={(event) => {
                        event.preventDefault();
                        void handleRenameCommit(project.id, project.title);
                      }}
                    >
                      <input
                        value={renameDraft}
                        onChange={(event) => setRenameDraft(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Escape") {
                            setRenamingProjectId(null);
                            setRenameDraft("");
                          }
                        }}
                        autoFocus
                      />
                      <button type="submit" aria-label="save workspace title">
                        <Check size={12} />
                      </button>
                      <button
                        type="button"
                        aria-label="cancel workspace title edit"
                        onClick={() => {
                          setRenamingProjectId(null);
                          setRenameDraft("");
                        }}
                      >
                        <X size={12} />
                      </button>
                    </form>
                  ) : (
                    <h3>{project.title}</h3>
                  )}
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
              <article className="archive-card" aria-label="loading workspaces">
                <span>Loading workspaces...</span>
              </article>
            ) : null}

            {!isLoadingProjects && displayProjects.length === 0 ? (
              <article className="archive-card" aria-label="empty workspaces">
                <span>No workspaces</span>
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
