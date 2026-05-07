from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import ValidationError

from ..core.config import Settings
from ..core.errors import (
    inspect_evidence_missing,
    inspect_provider_invalid_response,
    inspect_provider_unavailable,
    invalid_inspect_request,
)
from ..schemas.inspect import InspectRequest, InspectResponse


DEFAULT_DESCRIBE_QUESTION = (
    "Describe this clip for a text-only video editing agent. Focus on visible subjects, actions, scene, timing, "
    "camera motion, mood, editing value, and uncertainty. Do not invent details."
)


class InspectService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def peek_provider_name(self) -> str:
        return self._settings.inspect_provider_mode.strip().lower() or "unknown"

    def validate_request(self, payload: Any) -> InspectRequest:
        if not isinstance(payload, dict):
            raise invalid_inspect_request("Request body must be a JSON object.")
        try:
            request = InspectRequest.model_validate(payload)
        except ValidationError as exc:
            raise invalid_inspect_request(
                "Inspect request validation failed.",
                details={"validation_errors": exc.errors()},
            ) from exc
        self._validate_semantics(request)
        return request

    async def inspect(self, payload: InspectRequest) -> InspectResponse:
        provider = self._resolve_provider()
        genai, types = self._load_genai_modules()
        client = genai.Client(api_key=provider["api_key"])
        parts = self._build_content_parts(payload, types)
        config = types.GenerateContentConfig(
            temperature=0,
            system_instruction=self._build_system_prompt(payload),
            response_mime_type="application/json",
        )
        try:
            response = await client.aio.models.generate_content(
                model=provider["model"],
                contents=[types.Content(role="user", parts=parts)],
                config=config,
            )
        except TimeoutError as exc:
            raise inspect_provider_unavailable(
                "Inspect provider timed out.",
                status_code=504,
                details={"provider": provider["provider"]},
            ) from exc
        except Exception as exc:
            raise inspect_provider_unavailable(
                f"Inspect provider request failed: {exc}",
                status_code=502,
                details={"provider": provider["provider"]},
            ) from exc
        finally:
            await self._close_client(client)
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise inspect_provider_invalid_response("Inspect provider message content is empty.")
        return self._normalize_provider_text(text, payload)

    def _validate_semantics(self, payload: InspectRequest) -> None:
        candidate_count = len(payload.candidates)
        if candidate_count == 0:
            raise invalid_inspect_request("Inspect request must include at least one candidate.")
        if payload.mode == "verify" and candidate_count != 1:
            raise invalid_inspect_request("verify mode requires exactly one candidate.")
        if payload.mode == "compare" and candidate_count != 2:
            raise invalid_inspect_request("compare mode requires exactly two candidates.")
        if payload.mode == "choose" and not 3 <= candidate_count <= 5:
            raise invalid_inspect_request("choose mode requires three to five candidates.")
        if payload.mode == "rank" and not 2 <= candidate_count <= 5:
            raise invalid_inspect_request("rank mode requires two to five candidates.")
        if payload.mode == "describe" and candidate_count != 1:
            raise invalid_inspect_request("describe mode requires exactly one candidate.")
        if payload.mode != "describe" and not payload.question:
            raise invalid_inspect_request(f"{payload.mode} mode requires question.")

        for candidate in payload.candidates:
            if candidate.clip_duration_ms <= 0:
                raise inspect_evidence_missing(
                    "Each candidate must include a positive clip_duration_ms.",
                    details={"clip_id": candidate.clip_id},
                )
            if not candidate.frames:
                raise inspect_evidence_missing(
                    "Each candidate must include at least one frame.",
                    details={"clip_id": candidate.clip_id},
                )
            last_timestamp = -1
            for frame in candidate.frames:
                if frame.timestamp_ms > candidate.clip_duration_ms:
                    raise inspect_evidence_missing(
                        "Frame timestamp exceeds clip_duration_ms.",
                        details={
                            "clip_id": candidate.clip_id,
                            "frame_index": frame.frame_index,
                            "timestamp_ms": frame.timestamp_ms,
                            "clip_duration_ms": candidate.clip_duration_ms,
                        },
                    )
                if frame.timestamp_ms < last_timestamp:
                    raise inspect_evidence_missing(
                        "Frames must be ordered by timestamp_ms.",
                        details={
                            "clip_id": candidate.clip_id,
                            "frame_index": frame.frame_index,
                            "timestamp_ms": frame.timestamp_ms,
                        },
                    )
                last_timestamp = frame.timestamp_ms

    def _resolve_provider(self) -> dict[str, str]:
        mode = self.peek_provider_name()
        if mode != "google_gemini":
            raise inspect_provider_unavailable(
                "Inspect provider mode is not supported.",
                details={"provider_mode": mode},
            )
        api_key = (self._settings.google_api_key or "").strip() or (self._settings.gemini_api_key or "").strip()
        if not api_key:
            raise inspect_provider_unavailable(
                "GEMINI_API_KEY or GOOGLE_API_KEY is required when inspect_provider_mode=google_gemini.",
                details={"provider_mode": mode},
            )
        provider_model = (self._settings.inspect_default_model or "").strip() or self._settings.llm_gemini_default_model.strip()
        return {
            "provider": "google_gemini",
            "api_key": api_key,
            "model": provider_model or "gemini-3.1-flash-lite-preview",
        }

    def _load_genai_modules(self) -> tuple[Any, Any]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise inspect_provider_unavailable(
                "google-genai is required for Gemini inspect provider.",
                details={"provider_mode": self.peek_provider_name()},
            ) from exc
        return genai, types

    async def _close_client(self, client: Any) -> None:
        async_client = getattr(client, "aio", None)
        aclose = getattr(async_client, "aclose", None)
        if callable(aclose):
            await aclose()
            return
        close = getattr(client, "close", None)
        if callable(close):
            close()

    def _build_content_parts(self, payload: InspectRequest, types: Any) -> list[Any]:
        criteria_lines = "\n".join(
            f"- {criterion.name}: {criterion.description}" for criterion in payload.criteria
        ) or "- No explicit criteria provided."
        question = payload.question or DEFAULT_DESCRIBE_QUESTION
        parts: list[Any] = [
            types.Part.from_text(
                text=(
                    f"mode: {payload.mode}\n"
                    f"task_summary: {payload.task_summary}\n"
                    f"hypothesis_summary: {payload.hypothesis_summary or 'N/A'}\n"
                    f"question: {question}\n"
                    f"criteria:\n{criteria_lines}"
                )
            )
        ]
        for candidate in payload.candidates:
            parts.append(
                types.Part.from_text(
                    text=(
                        f"candidate clip_id={candidate.clip_id} asset_id={candidate.asset_id} "
                        f"clip_duration_ms={candidate.clip_duration_ms} summary={candidate.summary or 'N/A'}"
                    )
                )
            )
            for frame in candidate.frames:
                parts.append(
                    types.Part.from_text(
                        text=(
                            f"frame clip_id={candidate.clip_id} frame_index={frame.frame_index} "
                            f"timestamp_label={frame.timestamp_label} timestamp_ms={frame.timestamp_ms}"
                        )
                    )
                )
                try:
                    image_bytes = base64.b64decode(frame.image_base64, validate=True)
                except ValueError as exc:
                    raise inspect_evidence_missing(
                        "Frame image_base64 must be valid base64.",
                        details={"clip_id": candidate.clip_id, "frame_index": frame.frame_index},
                    ) from exc
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
        return parts

    def _build_system_prompt(self, payload: InspectRequest) -> str:
        if payload.mode == "describe":
            return (
                "You are the visual perception tool for a text-only video editing agent.\n"
                "Return exactly one JSON object.\n"
                "Do not return markdown, code fences, commentary, or extra prose.\n"
                "Describe only visible evidence from the provided clip frames.\n"
                "Separate observations from inferences.\n"
                "Mention uncertainty when the frames are insufficient.\n"
                "Do not invent identities, events, emotions, or off-screen facts.\n"
                "Use only these top-level fields: question_type, selected_clip_id, descriptions, uncertainty.\n"
                "question_type must be describe.\n"
                "descriptions must contain objects with clip_id, description, observations, actions, subjects, "
                "scene, camera, editing_value, uncertainty."
            )
        return (
            "You are a visual inspection tool for video editing.\n"
            "Return exactly one JSON object.\n"
            "Do not return markdown, code fences, commentary, or extra prose.\n"
            "Use only these top-level fields when relevant: "
            "question_type, selected_clip_id, ranking, candidate_judgments, uncertainty.\n"
            "candidate_judgments must be a non-empty array of objects with clip_id, verdict, confidence, short_reason.\n"
            "ranking must contain only clip_id values from the provided candidates.\n"
            "If you cannot make a stable choice, keep the JSON valid and explain uncertainty."
        )

    def _normalize_provider_text(self, text: str, request: InspectRequest) -> InspectResponse:
        parsed_payload = self._parse_json_object(text)
        if "question_type" not in parsed_payload:
            parsed_payload["question_type"] = request.mode
        if request.mode == "describe":
            return self._normalize_describe_response(parsed_payload, request)
        try:
            response = InspectResponse.model_validate(parsed_payload)
        except ValidationError as exc:
            raise inspect_provider_invalid_response(
                "Inspect provider returned a response that failed schema validation.",
                details={"validation_errors": exc.errors()},
            ) from exc

        candidate_ids = [candidate.clip_id for candidate in request.candidates]
        candidate_id_set = set(candidate_ids)
        normalized = response.model_dump()
        if normalized.get("question_type") != request.mode:
            raise inspect_provider_invalid_response(
                "question_type must match inspect request mode.",
                details={"question_type": normalized.get("question_type"), "mode": request.mode},
            )

        ranking = normalized.get("ranking")
        if ranking is not None:
            if not isinstance(ranking, list) or not ranking:
                raise inspect_provider_invalid_response("ranking must be a non-empty array when provided.")
            seen: set[str] = set()
            deduped_ranking: list[str] = []
            for clip_id in ranking:
                if clip_id not in candidate_id_set:
                    raise inspect_provider_invalid_response(
                        "ranking contains an unknown clip_id.",
                        details={"clip_id": clip_id},
                    )
                if clip_id in seen:
                    raise inspect_provider_invalid_response(
                        "ranking contains duplicate clip_id values.",
                        details={"clip_id": clip_id},
                    )
                seen.add(clip_id)
                deduped_ranking.append(clip_id)
            normalized["ranking"] = deduped_ranking

        selected_clip_id = normalized.get("selected_clip_id")
        if selected_clip_id is not None and selected_clip_id not in candidate_id_set:
            raise inspect_provider_invalid_response(
                "selected_clip_id is not part of the provided candidates.",
                details={"clip_id": selected_clip_id},
            )

        judgments = normalized.get("candidate_judgments") or []
        if not judgments:
            raise inspect_provider_invalid_response("Inspect provider response must include candidate_judgments.")
        seen_judgment_ids: set[str] = set()
        for judgment in judgments:
            clip_id = judgment["clip_id"]
            if clip_id not in candidate_id_set:
                raise inspect_provider_invalid_response(
                    "candidate_judgments contains an unknown clip_id.",
                    details={"clip_id": clip_id},
                )
            if clip_id in seen_judgment_ids:
                raise inspect_provider_invalid_response(
                    "candidate_judgments contains duplicate clip_id values.",
                    details={"clip_id": clip_id},
                )
            seen_judgment_ids.add(clip_id)

        if request.mode == "rank" and not normalized.get("ranking"):
            raise inspect_provider_invalid_response("rank mode requires ranking in provider response.")

        if request.mode in {"choose", "compare"} and not normalized.get("selected_clip_id"):
            ranking = normalized.get("ranking") or []
            if ranking:
                normalized["selected_clip_id"] = ranking[0]
            else:
                normalized["uncertainty"] = normalized.get("uncertainty") or "no_stable_selection_from_provider"

        try:
            return InspectResponse.model_validate(normalized)
        except ValidationError as exc:
            raise inspect_provider_invalid_response(
                "Inspect response normalization failed.",
                details={"validation_errors": exc.errors()},
            ) from exc

    def _normalize_describe_response(self, parsed_payload: dict[str, Any], request: InspectRequest) -> InspectResponse:
        parsed_payload["question_type"] = "describe"
        candidate_ids = [candidate.clip_id for candidate in request.candidates]
        candidate_id_set = set(candidate_ids)
        descriptions = parsed_payload.get("descriptions")
        if not isinstance(descriptions, list) or not descriptions:
            raise inspect_provider_invalid_response("describe mode requires descriptions in provider response.")

        seen_description_ids: set[str] = set()
        for description in descriptions:
            if not isinstance(description, dict):
                raise inspect_provider_invalid_response("description entries must be objects.")
            clip_id = description.get("clip_id")
            if clip_id not in candidate_id_set:
                raise inspect_provider_invalid_response(
                    "descriptions contains an unknown clip_id.",
                    details={"clip_id": clip_id},
                )
            if clip_id in seen_description_ids:
                raise inspect_provider_invalid_response(
                    "descriptions contains duplicate clip_id values.",
                    details={"clip_id": clip_id},
                )
            seen_description_ids.add(clip_id)

        selected_clip_id = parsed_payload.get("selected_clip_id")
        if selected_clip_id is not None and selected_clip_id not in candidate_id_set:
            raise inspect_provider_invalid_response(
                "selected_clip_id is not part of the provided candidates.",
                details={"clip_id": selected_clip_id},
            )
        if not selected_clip_id:
            parsed_payload["selected_clip_id"] = descriptions[0]["clip_id"]
        parsed_payload["candidate_judgments"] = parsed_payload.get("candidate_judgments") or []
        parsed_payload["ranking"] = parsed_payload.get("ranking") or None

        try:
            return InspectResponse.model_validate(parsed_payload)
        except ValidationError as exc:
            raise inspect_provider_invalid_response(
                "Inspect describe response normalization failed.",
                details={"validation_errors": exc.errors()},
            ) from exc

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        sanitized = text.strip()
        if sanitized.startswith("```"):
            lines = sanitized.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            sanitized = "\n".join(lines).strip()
        start = sanitized.find("{")
        if start == -1:
            raise inspect_provider_invalid_response("Inspect provider response does not contain a JSON object.")
        depth = 0
        end = None
        for index in range(start, len(sanitized)):
            char = sanitized[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise inspect_provider_invalid_response("Inspect provider returned an incomplete JSON object.")
        candidate = sanitized[start:end]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise inspect_provider_invalid_response(
                "Inspect provider returned invalid JSON.",
                details={"json_excerpt": candidate[:300]},
            ) from exc
        if not isinstance(parsed, dict):
            raise inspect_provider_invalid_response("Inspect provider JSON root must be an object.")
        return parsed
