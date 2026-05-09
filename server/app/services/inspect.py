from __future__ import annotations

import base64
import binascii
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
            system_instruction=self._build_system_prompt(),
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
        return self._normalize_provider_text(text, payload, model=provider["model"])

    def _validate_semantics(self, payload: InspectRequest) -> None:
        try:
            base64.b64decode(payload.image_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise inspect_evidence_missing(
                "image_base64 must be valid base64.",
                details={"clip_id": payload.clip_id},
            ) from exc

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
        try:
            image_bytes = base64.b64decode(payload.image_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise inspect_evidence_missing(
                "image_base64 must be valid base64.",
                details={"clip_id": payload.clip_id},
            ) from exc
        return [
            types.Part.from_text(text=f"clip_id: {payload.clip_id}\nprompt: {payload.prompt}"),
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        ]

    def _build_system_prompt(self) -> str:
        return (
            "You are the visual perception tool for a text-only video editing agent.\n"
            "Return exactly one JSON object. Do not return markdown, code fences, or extra prose.\n"
            "Describe only visible evidence from the provided image.\n"
            "Do not compare, rank, choose, or make editing decisions for the agent.\n"
            "Do not invent identities, off-screen events, emotions, or facts not visible in the image.\n"
            "Use only these top-level fields: description, uncertainty.\n"
            "description must be a concise but useful visual description for video editing."
        )

    def _normalize_provider_text(self, text: str, request: InspectRequest, *, model: str) -> InspectResponse:
        parsed = self._parse_json_object(text)
        description = str(parsed.get("description") or "").strip()
        if not description:
            raise inspect_provider_invalid_response("Inspect provider response must include description.")
        uncertainty = parsed.get("uncertainty")
        return InspectResponse(
            clip_id=request.clip_id,
            description=description,
            uncertainty=str(uncertainty).strip() if uncertainty else None,
            model=model,
        )

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
