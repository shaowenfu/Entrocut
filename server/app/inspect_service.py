from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from .config import Settings
from .errors import (
    inspect_evidence_missing,
    inspect_provider_invalid_response,
    inspect_provider_unavailable,
    invalid_inspect_request,
)
from .models import InspectRequest, InspectResponse


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
        upstream_payload = self._build_upstream_payload(payload, provider_model=provider["model"])
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
        if provider["provider"] == "google_gemini":
            headers["x-goog-api-client"] = "entrocut-server/0.1"
        try:
            async with httpx.AsyncClient(timeout=float(self._settings.inspect_timeout_seconds)) as client:
                response = await client.post(
                    f"{provider['base_url']}{provider['chat_path']}",
                    json=upstream_payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise inspect_provider_unavailable(
                "Inspect provider timed out.",
                status_code=504,
                details={"provider": provider["provider"]},
            ) from exc
        except httpx.HTTPError as exc:
            raise inspect_provider_unavailable(
                "Inspect provider transport failed.",
                status_code=502,
                details={"provider": provider["provider"]},
            ) from exc
        if response.status_code >= 400:
            raise inspect_provider_unavailable(
                "Inspect provider returned an error.",
                status_code=502,
                details={
                    "provider": provider["provider"],
                    "upstream_status": response.status_code,
                    "upstream_body": response.text[:500],
                },
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise inspect_provider_invalid_response("Inspect provider returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise inspect_provider_invalid_response("Inspect provider response body must be a JSON object.")
        return self._normalize_provider_response(body, payload)

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
        api_key = (self._settings.google_api_key or "").strip()
        if not api_key:
            raise inspect_provider_unavailable(
                "GOOGLE_API_KEY is required when inspect_provider_mode=google_gemini.",
                details={"provider_mode": mode},
            )
        provider_model = (self._settings.inspect_default_model or "").strip() or self._settings.llm_gemini_default_model.strip()
        return {
            "provider": "google_gemini",
            "base_url": self._settings.llm_gemini_base_url.rstrip("/"),
            "chat_path": self._settings.llm_gemini_chat_path,
            "api_key": api_key,
            "model": provider_model or "gemini-2.5-flash",
        }

    def _build_upstream_payload(self, payload: InspectRequest, *, provider_model: str) -> dict[str, Any]:
        criteria_lines = "\n".join(
            f"- {criterion.name}: {criterion.description}" for criterion in payload.criteria
        ) or "- No explicit criteria provided."
        system_text = (
            "You are a visual inspection tool for video editing.\n"
            "Return exactly one JSON object.\n"
            "Do not return markdown, code fences, commentary, or extra prose.\n"
            "Use only these top-level fields when relevant: "
            "question_type, selected_clip_id, ranking, candidate_judgments, uncertainty.\n"
            "candidate_judgments must be a non-empty array of objects with clip_id, verdict, confidence, short_reason.\n"
            "ranking must contain only clip_id values from the provided candidates.\n"
            "If you cannot make a stable choice, keep the JSON valid and explain uncertainty."
        )
        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"mode: {payload.mode}\n"
                    f"task_summary: {payload.task_summary}\n"
                    f"hypothesis_summary: {payload.hypothesis_summary or 'N/A'}\n"
                    f"question: {payload.question}\n"
                    f"criteria:\n{criteria_lines}"
                ),
            }
        ]
        for candidate in payload.candidates:
            user_content.append(
                {
                    "type": "text",
                    "text": (
                        f"candidate clip_id={candidate.clip_id} asset_id={candidate.asset_id} "
                        f"clip_duration_ms={candidate.clip_duration_ms} summary={candidate.summary or 'N/A'}"
                    ),
                }
            )
            for frame in candidate.frames:
                user_content.append(
                    {
                        "type": "text",
                        "text": (
                            f"frame clip_id={candidate.clip_id} frame_index={frame.frame_index} "
                            f"timestamp_label={frame.timestamp_label} timestamp_ms={frame.timestamp_ms}"
                        ),
                    }
                )
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{frame.image_base64}",
                        },
                    }
                )
        return {
            "model": provider_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_content},
            ],
        }

    def _normalize_provider_response(self, body: dict[str, Any], request: InspectRequest) -> InspectResponse:
        content_text = self._extract_response_text(body)
        parsed_payload = self._parse_json_object(content_text)
        if "question_type" not in parsed_payload:
            parsed_payload["question_type"] = request.mode
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

    def _extract_response_text(self, body: dict[str, Any]) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise inspect_provider_invalid_response("Inspect provider response must include choices.")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise inspect_provider_invalid_response("Inspect provider choice must be an object.")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise inspect_provider_invalid_response("Inspect provider response must include message.")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                part.get("text", "").strip()
                for part in content
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
            ]
            combined = "\n".join(part for part in text_parts if part).strip()
            if combined:
                return combined
        raise inspect_provider_invalid_response("Inspect provider message content is empty.")

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
