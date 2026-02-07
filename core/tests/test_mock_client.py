from __future__ import annotations

import json
import unittest
from unittest import mock
from urllib import error as urllib_error

from process.mock_client import MockClientError, MockServerClient


class _DummyResponse:
    def __init__(self, status: int, body: dict):
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class MockClientTestCase(unittest.TestCase):
    def test_local_fallback_analyze_is_deterministic(self) -> None:
        client = MockServerClient(base_url=None, contract_version="0.1.0-mock")
        frames = [
            {"scene_index": 0, "timestamp": 0.2, "file_path": "/tmp/a.jpg"},
            {"scene_index": 0, "timestamp": 0.8, "file_path": "/tmp/b.jpg"},
            {"scene_index": 1, "timestamp": 1.2, "file_path": "/tmp/c.jpg"},
        ]
        result = client.local_fallback_analyze(job_id="job-1", video_path="/tmp/video.mp4", frames=frames)
        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(result["contract_version"], "0.1.0-mock")
        self.assertEqual(len(result["analysis"]["segments"]), 2)

    def test_local_fallback_edl_returns_clips(self) -> None:
        client = MockServerClient(base_url=None, contract_version="0.1.0-mock")
        segments = [
            {"start_time": 0.0, "end_time": 1.0},
            {"start_time": 1.0, "end_time": 2.0},
        ]
        result = client.local_fallback_edl(
            job_id="job-2",
            video_path="/tmp/video.mp4",
            segments=segments,
            rule="highlight_first",
        )
        self.assertEqual(result["job_id"], "job-2")
        self.assertEqual(len(result["edl"]["clips"]), 2)
        self.assertEqual(result["edl"]["output_name"], "final.mp4")

    @mock.patch("process.mock_client.urllib_request.urlopen")
    def test_remote_analyze_success(self, mocked_urlopen) -> None:
        mocked_urlopen.return_value = _DummyResponse(
            200,
            {
                "contract_version": "0.1.0-mock",
                "job_id": "job-3",
                "analysis": {"segments": []},
            },
        )
        client = MockServerClient(base_url="http://127.0.0.1:8001", contract_version="0.1.0-mock")
        result = client.analyze(job_id="job-3", video_path="/tmp/video.mp4", frames=[])
        self.assertEqual(result["job_id"], "job-3")

    @mock.patch("process.mock_client.urllib_request.urlopen")
    def test_remote_analyze_unavailable_raises_external_error(self, mocked_urlopen) -> None:
        mocked_urlopen.side_effect = urllib_error.URLError("Connection refused")
        client = MockServerClient(base_url="http://127.0.0.1:8001", contract_version="0.1.0-mock")
        with self.assertRaises(MockClientError) as ctx:
            client.analyze(job_id="job-4", video_path="/tmp/video.mp4", frames=[])
        self.assertEqual(ctx.exception.error_type, "external_error")
        self.assertIn(ctx.exception.code, {"EXT_MOCK_UNAVAILABLE", "EXT_MOCK_TIMEOUT"})


if __name__ == "__main__":
    unittest.main()
