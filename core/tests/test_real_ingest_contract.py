from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

CORE_DIR = Path(__file__).resolve().parents[1]
if str(CORE_DIR) not in sys.path:
    sys.path.append(str(CORE_DIR))

CORE_TEST_APPDATA_DIR = tempfile.TemporaryDirectory()
os.environ["ENTROCUT_APP_DATA_ROOT"] = CORE_TEST_APPDATA_DIR.name
import types
fake_scenedetect = types.ModuleType("scenedetect")
fake_scenedetect.ContentDetector = object
fake_scenedetect.detect = lambda *args, **kwargs: []
sys.modules.setdefault("scenedetect", fake_scenedetect)

CORE_SERVER_SPEC = importlib.util.spec_from_file_location("core_server_real_ingest_module", CORE_DIR / "server.py")
if CORE_SERVER_SPEC is None or CORE_SERVER_SPEC.loader is None:
    raise RuntimeError("Unable to load core/server.py for tests.")
core_server = importlib.util.module_from_spec(CORE_SERVER_SPEC)
sys.modules["core_server_real_ingest_module"] = core_server
CORE_SERVER_SPEC.loader.exec_module(core_server)


class RealIngestContractTest(unittest.TestCase):
    def setUp(self) -> None:
        core_server.store.reset_for_test()
        core_server.auth_session_store.reset_for_test()
        self.client = TestClient(core_server.app)
        self.client.__enter__()
        self.detect_scenes_patcher = patch("store.detect_scenes", return_value=[(0, 5000), (5000, 9000)])
        self.extract_frames_patcher = patch("store.extract_and_stitch_frames", return_value="dummy_b64")
        self.detect_scenes_patcher.start()
        self.extract_frames_patcher.start()

        class _MockResponse:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

        class _MockClientAsyncContextManager:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def post(self, *args, **kwargs):
                return _MockResponse()

        self.httpx_patcher = patch("store.AsyncClient", return_value=_MockClientAsyncContextManager())
        self.httpx_patcher.start()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.detect_scenes_patcher.stop()
        self.extract_frames_patcher.stop()
        self.httpx_patcher.stop()

    def _create_project(self) -> str:
        response = self.client.post(
            "/api/v1/projects",
            json={
                "title": "Real ingest contract",
                "media": {
                    "files": [{"name": "input.mp4", "path": "/tmp/input.mp4"}],
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workspace"]["edit_draft"]["assets"], [])
        self.assertEqual(body["workspace"]["edit_draft"]["clips"], [])
        return body["project"]["id"]

    def _set_auth(self) -> None:
        response = self.client.post(
            "/api/v1/auth/session",
            json={"access_token": "tok_test_access_token_value_12345"},
        )
        self.assertEqual(response.status_code, 200)

    def _poll_ingest_done(self, project_id: str) -> dict:
        deadline = time.time() + 5
        last_workspace: dict | None = None
        while time.time() < deadline:
            response = self.client.get(f"/api/v1/projects/{project_id}")
            self.assertEqual(response.status_code, 200)
            last_workspace = response.json()["workspace"]
            active_task = last_workspace.get("active_task")
            if not active_task or active_task.get("status") in {"succeeded", "failed"}:
                return last_workspace
            time.sleep(0.05)
        self.fail(f"timed out waiting ingest completion: {last_workspace}")

    def test_import_requires_auth_at_entry(self) -> None:
        project_id = self._create_project()
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "clip.mp4"
            video_path.write_bytes(b"fake")
            response = self.client.post(
                f"/api/v1/projects/{project_id}/assets:import",
                json={"media": {"files": [{"name": "clip.mp4", "path": str(video_path)}]}},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_SESSION_REQUIRED")

    def test_import_rejects_directory_path(self) -> None:
        project_id = self._create_project()
        self._set_auth()
        with tempfile.TemporaryDirectory() as temp_dir:
            response = self.client.post(
                f"/api/v1/projects/{project_id}/assets:import",
                json={"media": {"files": [{"name": "not-file.mp4", "path": temp_dir}]}},
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "MEDIA_FILE_PATH_IS_DIRECTORY")

    def test_import_state_flow_reaches_retrieval_ready(self) -> None:
        project_id = self._create_project()
        self._set_auth()
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "clip.mp4"
            video_path.write_bytes(b"fake")
            response = self.client.post(
                f"/api/v1/projects/{project_id}/assets:import",
                json={"media": {"files": [{"name": "clip.mp4", "path": str(video_path)}]}},
            )
            self.assertEqual(response.status_code, 200)
            workspace = self._poll_ingest_done(project_id)
        self.assertTrue(workspace["media_summary"]["retrieval_ready"])
        self.assertEqual(workspace["media_summary"]["ready_asset_count"], 1)
        self.assertGreaterEqual(workspace["media_summary"]["indexed_clip_count"], 1)
