import { assembleActionContext, type ActionContextPacket } from "./contextAssembler";
import {
  isPlannerOutputExecutable,
  validatePlannerOutput,
  type PlannerOutput,
} from "./plannerOutput";
import {
  recordExecutionAction,
  updateSelectionState,
  type PlannerActionType,
  type SessionRuntimeState,
} from "./sessionRuntimeState";

export type ExecutionLoopErrorCode =
  | "CONTEXT_ASSEMBLY_FAILED"
  | "PLANNER_FAILED"
  | "PLANNER_OUTPUT_INVALID"
  | "ROUTING_FAILED"
  | "TOOL_EXECUTION_FAILED"
  | "WRITEBACK_FAILED";

export interface ExecutionLoopError {
  code: ExecutionLoopErrorCode;
  message: string;
  actionType?: PlannerActionType;
}

export interface ExecutionStepInput {
  runtimeState: SessionRuntimeState;
  actionType: PlannerActionType;
  stepStartedAt?: string;
}

export interface ExecutionStepResult {
  success: boolean;
  actionContextPacket?: ActionContextPacket;
  plannerOutput?: PlannerOutput;
  nextRuntimeState: SessionRuntimeState;
  shouldContinue: boolean;
  waitForUser: boolean;
  stopReason: string;
  error?: ExecutionLoopError;
}

export interface PlannerRunner {
  plan(input: { packet: ActionContextPacket }): Promise<PlannerOutput> | PlannerOutput;
}

export interface ToolExecutionResult {
  kind: "state" | "tool";
  summary: string;
  nextRuntimeState?: SessionRuntimeState;
  shouldContinue?: boolean;
  waitForUser?: boolean;
}

export interface ToolExecutor {
  execute(input: {
    plannerOutput: PlannerOutput;
    runtimeState: SessionRuntimeState;
  }): Promise<ToolExecutionResult> | ToolExecutionResult;
}

export interface ExecutionLoopDeps {
  plannerRunner: PlannerRunner;
  toolExecutor: ToolExecutor;
}

export interface RunExecutionLoopInput {
  runtimeState: SessionRuntimeState;
  actionType: PlannerActionType;
  maxAutoSteps?: number;
}

export interface RunExecutionLoopResult {
  steps: ExecutionStepResult[];
  finalRuntimeState: SessionRuntimeState;
}

export async function runExecutionStep(
  deps: ExecutionLoopDeps,
  input: ExecutionStepInput,
): Promise<ExecutionStepResult> {
  const stepStartedAt = input.stepStartedAt ?? new Date().toISOString();

  const contextResult = assembleActionContext({
    actionType: input.actionType,
    runtimeState: input.runtimeState,
  });
  if (!contextResult.ok) {
    return {
      success: false,
      nextRuntimeState: input.runtimeState,
      shouldContinue: false,
      waitForUser: false,
      stopReason: "context_assembly_failed",
      error: {
        code: "CONTEXT_ASSEMBLY_FAILED",
        message: contextResult.error.message,
        actionType: input.actionType,
      },
    };
  }

  const runtimeWithStartedAction = recordExecutionAction(
    input.runtimeState,
    {
      action: input.actionType,
      status: "running",
      summary: `execution_step_started:${input.actionType}`,
    },
    stepStartedAt,
  );

  let plannerOutput: PlannerOutput;
  try {
    plannerOutput = await deps.plannerRunner.plan({
      packet: contextResult.packet,
    });
  } catch (error) {
    return {
      success: false,
      actionContextPacket: contextResult.packet,
      nextRuntimeState: recordExecutionAction(
        runtimeWithStartedAction,
        {
          action: input.actionType,
          status: "failed",
          summary: "planner_failed",
        },
        new Date().toISOString(),
      ),
      shouldContinue: false,
      waitForUser: false,
      stopReason: "planner_failed",
      error: {
        code: "PLANNER_FAILED",
        message: error instanceof Error ? error.message : "planner_failed",
        actionType: input.actionType,
      },
    };
  }

  const validationErrors = validatePlannerOutput(plannerOutput);
  if (validationErrors.length > 0 || !isPlannerOutputExecutable(plannerOutput)) {
    return {
      success: false,
      actionContextPacket: contextResult.packet,
      plannerOutput,
      nextRuntimeState: recordExecutionAction(
        runtimeWithStartedAction,
        {
          action: input.actionType,
          status: "failed",
          summary: `planner_output_invalid:${validationErrors.map((item) => item.code).join(",")}`,
        },
        new Date().toISOString(),
      ),
      shouldContinue: false,
      waitForUser: false,
      stopReason: "planner_output_invalid",
      error: {
        code: "PLANNER_OUTPUT_INVALID",
        message: validationErrors.map((item) => item.message).join(";") || "planner_output_not_executable",
        actionType: input.actionType,
      },
    };
  }

  let executionResult: ToolExecutionResult;
  try {
    executionResult = routeStateAction(plannerOutput, runtimeWithStartedAction) ?? (await deps.toolExecutor.execute({
      plannerOutput,
      runtimeState: runtimeWithStartedAction,
    }));
  } catch (error) {
    return {
      success: false,
      actionContextPacket: contextResult.packet,
      plannerOutput,
      nextRuntimeState: recordExecutionAction(
        runtimeWithStartedAction,
        {
          action: input.actionType,
          status: "failed",
          summary: "tool_execution_failed",
        },
        new Date().toISOString(),
      ),
      shouldContinue: false,
      waitForUser: false,
      stopReason: "tool_execution_failed",
      error: {
        code: "TOOL_EXECUTION_FAILED",
        message: error instanceof Error ? error.message : "tool_execution_failed",
        actionType: input.actionType,
      },
    };
  }

  const nextRuntimeState = recordExecutionAction(
    executionResult.nextRuntimeState ?? runtimeWithStartedAction,
    {
      action: plannerOutput.header.action,
      status: "succeeded",
      summary: executionResult.summary,
    },
    new Date().toISOString(),
  );

  return {
    success: true,
    actionContextPacket: contextResult.packet,
    plannerOutput,
    nextRuntimeState,
    shouldContinue: executionResult.shouldContinue ?? false,
    waitForUser: executionResult.waitForUser ?? false,
    stopReason:
      executionResult.shouldContinue === true
        ? "continue"
        : executionResult.waitForUser === true
        ? "wait_for_user"
        : "step_completed",
  };
}

export async function runExecutionLoop(
  deps: ExecutionLoopDeps,
  input: RunExecutionLoopInput,
): Promise<RunExecutionLoopResult> {
  const maxAutoSteps = Math.max(1, input.maxAutoSteps ?? 3);
  const steps: ExecutionStepResult[] = [];
  let currentRuntimeState = input.runtimeState;
  let currentActionType = input.actionType;

  for (let stepIndex = 0; stepIndex < maxAutoSteps; stepIndex += 1) {
    const stepResult = await runExecutionStep(deps, {
      runtimeState: currentRuntimeState,
      actionType: currentActionType,
    });
    steps.push(stepResult);
    currentRuntimeState = stepResult.nextRuntimeState;

    if (!stepResult.success || !stepResult.shouldContinue || stepResult.waitForUser) {
      break;
    }

    currentActionType = deriveNextActionType(stepResult.plannerOutput?.header.action ?? currentActionType);
  }

  return {
    steps,
    finalRuntimeState: currentRuntimeState,
  };
}

function routeStateAction(
  plannerOutput: PlannerOutput,
  runtimeState: SessionRuntimeState,
): ToolExecutionResult | null {
  switch (plannerOutput.header.action) {
    case "reply_only":
      return {
        kind: "state",
        summary: "reply_only_completed",
        nextRuntimeState: runtimeState,
        shouldContinue: false,
        waitForUser: true,
      };
    case "ask_clarification":
      return {
        kind: "state",
        summary: "clarification_requested",
        nextRuntimeState: {
          ...runtimeState,
          updatedAt: new Date().toISOString(),
          conversation: {
            ...runtimeState.conversation,
            clarificationRequired: true,
            openQuestions:
              plannerOutput.payload.kind === "clarification"
                ? plannerOutput.payload.questions.map((question) => ({
                    question,
                    raisedBy: "agent" as const,
                  }))
                : runtimeState.conversation.openQuestions,
          },
        },
        shouldContinue: false,
        waitForUser: true,
      };
    case "update_goal":
      return {
        kind: "state",
        summary: "goal_updated",
        nextRuntimeState: {
          ...runtimeState,
          updatedAt: new Date().toISOString(),
          goal: {
            ...runtimeState.goal,
            constraints:
              plannerOutput.payload.kind === "goal_update"
                ? [
                    ...runtimeState.goal.constraints,
                    ...Object.entries(plannerOutput.payload.changes).map(([key, value]) => ({
                      key,
                      value: String(value),
                      status: "confirmed" as const,
                    })),
                  ]
                : runtimeState.goal.constraints,
          },
        },
        shouldContinue: false,
        waitForUser: false,
      };
    case "set_selection_context":
      if (plannerOutput.payload.kind !== "selection_update") {
        return null;
      }
      return {
        kind: "state",
        summary: "selection_updated",
        nextRuntimeState: updateSelectionState(
          runtimeState,
          {
            scope: plannerOutput.payload.scope,
            selectedSceneId: plannerOutput.payload.scene_id,
            selectedShotId: plannerOutput.payload.shot_id,
          },
          new Date().toISOString(),
        ),
        shouldContinue: false,
        waitForUser: false,
      };
    default:
      return null;
  }
}

function deriveNextActionType(action: PlannerActionType): PlannerActionType {
  switch (action) {
    case "create_retrieval_request":
      return "inspect_candidates";
    case "inspect_candidates":
      return "apply_patch";
    case "apply_patch":
      return "render_preview";
    default:
      return action;
  }
}
