# Agent Chat UI Integration Plan

## 1. Architectural Analysis & State Mapping

The goal is to integrate the high-fidelity "Breathing Step Flow" UI components into the actual `WorkspacePage.tsx` and bind them to the real-time event stream managed by `useWorkspaceStore`.

### State Lifecycle Observations
Upon analyzing `useWorkspaceStore.ts`, a critical architectural detail emerged regarding how `agentSteps` and `chatTurns` are managed:

*   **`chatTurns`**: Persistent history of the conversation. Contains `UserTurn` and `AssistantDecisionTurn`.
*   **`agentSteps`**: Transient array of `CoreAgentStepItem` objects.
    *   It populates in real-time via the `AGENT_STEP_UPDATED` event.
    *   **Crucially**, it is cleared (`agentSteps: []`) whenever a new `CHAT_TURN_CREATED` event arrives with `role === "user"`.
*   **`isThinking`**: Derived from `chatState === "responding"`.

### Design Implications
This transient nature of `agentSteps` is actually a feature, not a bug, for our UI design!
It perfectly aligns with the concept of reducing "information overload". 
1.  **Current Turn**: While the AI is processing the latest user request, we display the rich, expanding/collapsing `AgentExecutionBlock` with all the intermediate tool artifacts (`RetrieveArtifact`, `InspectArtifact`, `PatchArtifact`).
2.  **Historical Turns**: Once the user sends a *new* message, the previous tool steps are wiped from the state, leaving behind only the clean `UserMessage` and `AgentFinalMessage` (the `AssistantDecisionTurn`). This keeps the chat history pristine and readable.

## 2. Component Restructuring (`WorkspacePage.tsx`)

We will replace the existing linear mapping inside the `.chat-thread` div. The new structure will look like this:

```tsx
<div className="chat-thread">
  {/* 1. Render History (Clean) */}
  {historicalTurns.map(turn => {
    if (turn.role === 'user') return <UserMessage text={turn.content} />;
    if (turn.role === 'assistant') return <AgentFinalMessage text={turn.reasoning_summary} />;
  })}

  {/* 2. Render Active Execution Block (Rich) */}
  {agentSteps.length > 0 && (
    <div className="agent-execution-block">
      {agentSteps.map((step, index) => {
        const isLastStep = index === agentSteps.length - 1;
        const status = (isThinking && isLastStep) ? 'loading' : 'success';
        
        return (
          <AgentStep 
            key={index}
            status={status}
            title={step.summary} // Expanded title
            summary={`✓ ${step.summary}`} // Collapsed summary
            icon={getIconForPhase(step.phase)}
          >
            <ArtifactRenderer phase={step.phase} details={step.details} isLoading={status === 'loading'} />
          </AgentStep>
        );
      })}
    </div>
  )}

  {/* 3. Render Latest Assistant Turn (if finished but no new user message yet) */}
  {latestAssistantTurn && !isThinking && (
    <AgentFinalMessage text={latestAssistantTurn.reasoning_summary} />
  )}
  
  {/* Thinking indicator if no steps yet but processing */}
  {isThinking && agentSteps.length === 0 && (
    <div className="thinking-box">...</div>
  )}
</div>
```

## 3. Artifact Data Binding

To make the artifacts dynamic, we need to map the `CoreAgentStepItem.phase` to our UI components and eventually pass the `details` payload.

| Phase | Component | Icon | Details Payload (Expected) |
| :--- | :--- | :--- | :--- |
| `retrieval` | `<RetrieveArtifact />` | `Search` | Array of matched clips with scores and thumbnail references. |
| `inspection` | `<InspectArtifact />` | `ScanSearch` | Target frame/clip reference, structured VLM analysis report. |
| `patching` / `edit` | `<PatchArtifact />` | `Scissors` | List of timeline operations (inserts, removals). |
| `other` | `null` (Text only) | `Settings` | N/A |

*Note: In the initial integration pass, if the backend `details` payload is not yet fully structured or mapped in the frontend, we will pass the real `step.summary` and `phase`, but render the Artifacts with fallback/mock data (or omitted) to ensure the layout functions correctly without crashing.*

## 4. Execution Plan (Next Steps)

1.  **Refactor Components**: Export the UI components (`UserMessage`, `AgentStep`, `AgentFinalMessage`, etc.) from `AgentChatPanels.tsx` (or move them to a dedicated file like `AgentChatComponents.tsx`) so they can be imported cleanly by `WorkspacePage.tsx`.
2.  **Integrate into Workspace**: Modify `client/src/pages/WorkspacePage.tsx` to implement the layout structure defined in Section 2.
3.  **State Mapping Logic**: Write the helper functions (e.g., `getIconForPhase`, `ArtifactRenderer`) to map the Zustand store state to the UI components.
4.  **Cleanup**: Remove the temporary `?ui-canvas` routing from `App.tsx` once the real integration is verified.
5.  **Quality Assurance**: Run the application, trigger a real backend agent planning cycle, and verify the "Breathing Step Flow" triggers accurately based on `AGENT_STEP_UPDATED` WebSocket events.