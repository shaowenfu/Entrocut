"""
Mock 云端客户端

用于调用远端 Mock Server，若不可用则可回退本地 Mock 结果。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request


class MockClientError(Exception):
    """Mock 客户端异常，携带错误语义。"""

    def __init__(self, error_type: str, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_type = error_type
        self.code = code
        self.details = details or {}


@dataclass
class MockServerClient:
    """
    Mock Server 客户端

    Attributes:
        base_url: 远端 Mock Server 地址，未配置则仅使用本地回退逻辑。
        contract_version: 契约版本。
        timeout_seconds: HTTP 超时时间。
    """

    base_url: Optional[str]
    contract_version: str = "0.1.0-mock"
    timeout_seconds: float = 8.0

    def analyze(self, job_id: str, video_path: str, frames: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        调用远端 /mock/analyze；若未配置 base_url 则使用本地 fallback。
        """
        if not self.base_url:
            return self.local_fallback_analyze(job_id=job_id, video_path=video_path, frames=frames)

        payload = {
            "job_id": job_id,
            "contract_version": self.contract_version,
            "video_path": video_path,
            "frames": frames,
        }
        return self._post_json("/api/v1/mock/analyze", payload)

    def generate_edl(
        self,
        job_id: str,
        video_path: str,
        segments: List[Dict[str, Any]],
        rule: str = "highlight_first",
    ) -> Dict[str, Any]:
        """
        调用远端 /mock/edl；若未配置 base_url 则使用本地 fallback。
        """
        if not self.base_url:
            return self.local_fallback_edl(
                job_id=job_id,
                video_path=video_path,
                segments=segments,
                rule=rule,
            )

        payload = {
            "job_id": job_id,
            "contract_version": self.contract_version,
            "segments": segments,
            "rule": rule,
        }
        return self._post_json("/api/v1/mock/edl", payload)

    def local_fallback_analyze(
        self, job_id: str, video_path: str, frames: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        本地 fallback 分析结果（确定性）。
        """
        grouped: Dict[int, List[float]] = {}
        for frame in frames:
            scene_index = int(frame.get("scene_index", 0))
            grouped.setdefault(scene_index, []).append(float(frame["timestamp"]))

        segments = []
        for scene_index in sorted(grouped.keys()):
            scene_times = grouped[scene_index]
            start_time = min(scene_times)
            end_time = max(scene_times) + 0.5
            segments.append(
                {
                    "segment_id": f"seg_{scene_index:04d}",
                    "start_time": round(start_time, 6),
                    "end_time": round(end_time, 6),
                    "tags": [f"mock_scene_{scene_index}"],
                    "score": 0.9,
                    "description": "local fallback analysis",
                }
            )

        return {
            "contract_version": self.contract_version,
            "job_id": job_id,
            "request_id": str(uuid.uuid4()),
            "analysis": {"segments": segments},
        }

    def local_fallback_edl(
        self,
        job_id: str,
        video_path: str,
        segments: List[Dict[str, Any]],
        rule: str = "highlight_first",
    ) -> Dict[str, Any]:
        """
        本地 fallback EDL（确定性）。
        """
        clips = []
        for idx, segment in enumerate(segments[:5]):
            start_time = float(segment.get("start_time", 0.0))
            end_time = float(segment.get("end_time", start_time + 1.0))
            if end_time <= start_time:
                end_time = start_time + 1.0

            clips.append(
                {
                    "clip_id": f"clip_{idx:04d}",
                    "src": video_path,
                    "start": round(start_time, 6),
                    "end": round(end_time, 6),
                }
            )

        return {
            "contract_version": self.contract_version,
            "job_id": job_id,
            "request_id": str(uuid.uuid4()),
            "edl": {
                "clips": clips,
                "output_name": "final.mp4",
                "rule": rule,
            },
        }

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        assert self.base_url is not None
        url = f"{self.base_url.rstrip('/')}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Contract-Version": self.contract_version,
            "X-Request-ID": str(uuid.uuid4()),
        }
        req = urllib_request.Request(url=url, data=body, headers=headers, method="POST")

        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                if response.status != 200:
                    raise MockClientError(
                        error_type="external_error",
                        code="EXT_MOCK_BAD_RESPONSE",
                        message=f"Mock server returned status {response.status}",
                        details={"status": response.status, "url": url},
                    )
                return json.loads(raw)
        except urllib_error.HTTPError as exc:
            raise MockClientError(
                error_type="external_error",
                code="EXT_MOCK_BAD_RESPONSE",
                message=f"Mock server HTTP error: {exc.code}",
                details={"status": exc.code, "url": url},
            ) from exc
        except urllib_error.URLError as exc:
            code = "EXT_MOCK_TIMEOUT" if "timed out" in str(exc.reason).lower() else "EXT_MOCK_UNAVAILABLE"
            raise MockClientError(
                error_type="external_error",
                code=code,
                message=f"Mock server unavailable: {exc.reason}",
                details={"reason": str(exc.reason), "url": url},
            ) from exc
        except TimeoutError as exc:
            raise MockClientError(
                error_type="external_error",
                code="EXT_MOCK_TIMEOUT",
                message="Mock server timeout",
                details={"url": url},
            ) from exc
