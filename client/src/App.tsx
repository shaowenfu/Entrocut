import LaunchpadPage from "./pages/LaunchpadPage";
import WorkspacePage from "./pages/WorkspacePage";
import { useLaunchpadStore } from "./store/useLaunchpadStore";

function App() {
  const activeWorkspaceId = useLaunchpadStore((state) => state.activeWorkspaceId);
  const activeWorkspaceName = useLaunchpadStore((state) => state.activeWorkspaceName);
  const clearActiveWorkspace = useLaunchpadStore((state) => state.clearActiveWorkspace);

  if (!activeWorkspaceId) {
    return <LaunchpadPage />;
  }

  return (
    <WorkspacePage
      workspaceId={activeWorkspaceId}
      workspaceName={activeWorkspaceName ?? activeWorkspaceId}
      onBackLaunchpad={clearActiveWorkspace}
    />
  );
}

export default App;
