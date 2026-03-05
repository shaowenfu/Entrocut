import { useState } from "react";
import LaunchpadPage from "./pages/LaunchpadPage";
import WorkspacePage from "./pages/WorkspacePage";

type AppView = "launchpad" | "workspace";

function App() {
  const [view, setView] = useState<AppView>("launchpad");
  const [activeWorkspaceName, setActiveWorkspaceName] = useState("Beach Trip Vlog");

  function handleOpenWorkspace(workspaceName: string) {
    setActiveWorkspaceName(workspaceName);
    setView("workspace");
  }

  if (view === "launchpad") {
    return <LaunchpadPage onOpenWorkspace={handleOpenWorkspace} />;
  }

  return (
    <WorkspacePage
      workspaceName={activeWorkspaceName}
      onBackLaunchpad={() => setView("launchpad")}
    />
  );
}

export default App;
