import { requestJson } from "../services/httpClient";
import type { ActionContextPacket } from "./contextAssembler";
import type { PlannerRunner } from "./executionLoop";
import {
  normalizePlannerOutput,
  validatePlannerOutput,
  type PlannerOutput,
} from "./plannerOutput";

interface ChatCompletionMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface ChatCompletionChoice {
  message?: {
    role?: string;
    content?: string | null;
  };
}

interface ChatCompletionResponse {
  choices?: ChatCompletionChoice[];
}

const DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8001";
const DEFAULT_PLANNER_MODEL = "entro-reasoning-v1";
const DEFAULT_MAX_RETRIES = 2;

export function createLlmPlannerRunner(fallback?: PlannerRunner): PlannerRunner {
  return {
    async plan({ packet }) {
      try {
        return await requestPlannerOutput(packet);
      } catch (error) {
        if (fallback) {
          return fallback.plan({ packet });
        }
        throw error;
      }
    },
  };
}

function buildPlannerUrl(path: string): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const baseUrl = (env.VITE_SERVER_BASE_URL?.trim() || DEFAULT_SERVER_BASE_URL).replace(/\/$/, "");
  return `${baseUrl}${path}`;
}

function getPlannerModel(): string {
  const env = import.meta.env as Record<string, string | undefined>;
  return env.VITE_PLANNER_MODEL?.trim() || DEFAULT_PLANNER_MODEL;
}

function buildPlannerMessages(packet: ActionContextPacket): ChatCompletionMessage[] {
  return [
    {
      role: "system",
      content: [
        "You are the planning core of an AI video editing agent.",
        "Return JSON only. No markdown. No prose outside JSON. No code fences.",
        "Return exactly one JSON object. Do not wrap it in an array.",
        "You must output a PlannerOutput object with exactly three top-level keys: header, payload, meta. No extra top-level keys.",
        'header.action must be one of: "reply_only","ask_clarification","update_goal","set_selection_context","create_retrieval_request","inspect_candidates","apply_patch","render_preview".',
        'payload.kind must match action exactly: reply_only->none, ask_clarification->clarification, update_goal->goal_update, set_selection_context->selection_update, create_retrieval_request->retrieval_request, inspect_candidates->candidate_inspection, apply_patch->edit_draft_patch, render_preview->preview_request.',
        "meta.target_scope must be one of global, scene, shot.",
        "Prefer minimal valid payloads. Use existing ids from the packet. Do not invent unavailable target ids.",
        "If required facts are missing, choose ask_clarification.",
        "If selected_scene_id or selected_shot_id is null in the packet, keep them null unless the payload type strictly requires an existing id already present in the packet.",
        "If you output create_retrieval_request, payload.request.query must be a non-empty string and payload.request.policy must be present.",
        "If you output inspect_candidates, payload.request.candidates must be non-empty.",
        "If you output apply_patch, payload.patch.operations must be non-empty.",
        "If you output render_preview, payload.request.draft_version must be a number.",
        "The response must be parseable by JSON.parse without repairs.",
      ].join("\n"),
    },
    {
      role: "user",
      content: [
        "Current ActionContextPacket JSON:",
        JSON.stringify(packet, null, 2),
        "",
        "Return a single valid PlannerOutput JSON object.",
        'Example shape: {"header":{"action":"ask_clarification","ready":true,"reason":"missing_goal"},"payload":{"kind":"clarification","questions":["What kind of opening do you want?"]},"meta":{"target_scope":"scene","target_scene_id":"scene_1","target_shot_id":null}}',
      ].join("\n"),
    },
  ];
}

function buildRepairMessages(
  packet: ActionContextPacket,
  invalidContent: string,
  validationErrors: string[],
): ChatCompletionMessage[] {
  return [
    ...buildPlannerMessages(packet),
    {
      role: "assistant",
      content: invalidContent,
    },
    {
      role: "user",
      content: [
        "Your previous output was invalid.",
        `Validation errors: ${validationErrors.join("; ")}`,
        "Repair the response and return a single valid PlannerOutput JSON object only.",
      ].join("\n"),
    },
  ];
}

async function requestPlannerOutput(packet: ActionContextPacket): Promise<PlannerOutput> {
  let lastError: Error | null = null;
  let previousInvalidContent = "";
  let previousValidationErrors: string[] = [];

  for (let attempt = 0; attempt <= DEFAULT_MAX_RETRIES; attempt += 1) {
    const messages =
      attempt === 0
        ? buildPlannerMessages(packet)
        : buildRepairMessages(packet, previousInvalidContent, previousValidationErrors);

    try {
      const response = await requestJson<ChatCompletionResponse>(buildPlannerUrl("/v1/chat/completions"), {
        method: "POST",
        body: {
          model: getPlannerModel(),
          stream: false,
          temperature: 0.1,
          max_tokens: 1400,
          messages,
        },
      });

      const parsed = parsePlannerOutputResponse(response);
      const validationErrors = validatePlannerOutput(parsed);
      if (validationErrors.length === 0) {
        return parsed;
      }

      previousInvalidContent = response.choices?.[0]?.message?.content?.trim() || "";
      previousValidationErrors = validationErrors.map((item) => item.message);
      lastError = new Error(`planner_output_invalid:${previousValidationErrors.join(",")}`);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      previousInvalidContent = lastError.message;
      previousValidationErrors = [lastError.message];
    }
  }

  throw lastError ?? new Error("planner_output_invalid");
}

function parsePlannerOutputResponse(response: ChatCompletionResponse): PlannerOutput {
  const content = response.choices?.[0]?.message?.content?.trim();
  if (!content) {
    throw new Error("planner_response_empty");
  }

  const extracted = extractJsonObject(stripCodeFence(content));
  return normalizePlannerOutput(JSON.parse(extracted));
}

function stripCodeFence(content: string): string {
  const trimmed = content.trim();
  if (!trimmed.startsWith("```")) {
    return trimmed;
  }
  return trimmed.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
}

function extractJsonObject(content: string): string {
  const trimmed = content.trim();
  if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
    return trimmed;
  }

  const firstBrace = trimmed.indexOf("{");
  if (firstBrace < 0) {
    throw new Error("planner_response_no_json_object");
  }

  let depth = 0;
  let inString = false;
  let escaped = false;
  let start = -1;

  for (let index = firstBrace; index < trimmed.length; index += 1) {
    const char = trimmed[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }
    if (char === "{") {
      if (depth === 0) {
        start = index;
      }
      depth += 1;
      continue;
    }
    if (char === "}") {
      depth -= 1;
      if (depth === 0 && start >= 0) {
        return trimmed.slice(start, index + 1);
      }
    }
  }

  throw new Error("planner_response_unbalanced_json");
}
