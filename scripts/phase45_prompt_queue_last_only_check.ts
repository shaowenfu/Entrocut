import { useWorkspaceStore } from "../client/src/store/useWorkspaceStore";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

async function main(): Promise<void> {
  useWorkspaceStore.setState({
    workspaceId: "prompt_queue_project",
    isMediaProcessing: true,
    processingPhase: "media_processing",
    chatTurns: [],
    pendingPrompt: null,
    lastError: null,
  });

  await useWorkspaceStore.getState().sendChat("first queued prompt");
  await useWorkspaceStore.getState().sendChat("last queued prompt");

  const state = useWorkspaceStore.getState();
  assert(state.pendingPrompt === "last queued prompt", "pendingPrompt should keep only the latest prompt");
  assert(state.chatTurns.length === 4, "queued prompts should append two user turns and two assistant turns");

  const userTurns = state.chatTurns.filter((turn) => turn.role === "user");
  const assistantTurns = state.chatTurns.filter((turn) => turn.role === "assistant");

  assert(userTurns.length === 2, "expected two user turns");
  assert(assistantTurns.length === 2, "expected two assistant turns");
  assert(
    assistantTurns.every(
      (turn) =>
        turn.type === "decision" &&
        turn.decision_type === "ASK_USER_CLARIFICATION" &&
        turn.ops.some((op) => op.op === "prompt_queued")
    ),
    "queued prompts should only produce prompt_queued assistant turns"
  );

  console.log("phase45_prompt_queue_last_only_ok");
}

void main();
