from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

import server as core_server
from process.job_orchestrator import PipelineError


class CoreServerApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.transport = httpx.ASGITransport(app=core_server.app, raise_app_exceptions=False)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    def setUp(self) -> None:
        self.original_work_root = core_server.orchestrator.work_root
        self.temp_work_root = Path(tempfile.mkdtemp(prefix="core_api_work_root_", dir=Path.cwd())).resolve()
        core_server.orchestrator.work_root = self.temp_work_root

    def tearDown(self) -> None:
        core_server.orchestrator.work_root = self.original_work_root
        shutil.rmtree(self.temp_work_root, ignore_errors=True)

    async def test_health_response_contains_request_id_header(self) -> None:
        response = await self.client.get("/health", headers={"X-Request-ID": "req-core-health-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Request-ID"), "req-core-health-1")

    async def test_get_job_not_found_returns_structured_error(self) -> None:
        with mock.patch.object(
            core_server.orchestrator,
            "get_job",
            new=mock.AsyncMock(side_effect=KeyError("Job not found: missing-job")),
        ):
            response = await self.client.get("/jobs/missing-job", headers={"X-Request-ID": "req-core-job-404"})

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["type"], "validation_error")
        self.assertEqual(data["error"]["code"], "VAL_JOB_NOT_FOUND")
        self.assertEqual(data["error"]["step"], "GET_JOB")
        self.assertEqual(data["error"]["request_id"], "req-core-job-404")

    async def test_start_job_conflict_returns_structured_error(self) -> None:
        with mock.patch.object(
            core_server.orchestrator,
            "start_job",
            new=mock.AsyncMock(
                side_effect=PipelineError(
                    error_type="runtime_error",
                    code="RUN_JOB_ALREADY_ACTIVE",
                    message="Active job exists",
                    step="START_JOB",
                )
            ),
        ):
            response = await self.client.post(
                "/jobs/start",
                json={"video_path": "/tmp/example.mp4"},
                headers={"X-Request-ID": "req-core-start-409"},
            )

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["error"]["type"], "runtime_error")
        self.assertEqual(data["error"]["code"], "RUN_JOB_ALREADY_ACTIVE")
        self.assertEqual(data["error"]["step"], "START_JOB")
        self.assertEqual(data["error"]["request_id"], "req-core-start-409")

    async def test_unhandled_exception_returns_standard_runtime_error(self) -> None:
        with mock.patch.object(
            core_server.orchestrator,
            "list_jobs",
            new=mock.AsyncMock(side_effect=RuntimeError("boom")),
        ):
            response = await self.client.get("/jobs", headers={"X-Request-ID": "req-core-unhandled"})

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["error"]["type"], "runtime_error")
        self.assertEqual(data["error"]["code"], "RUN_UNHANDLED_EXCEPTION")
        self.assertEqual(data["error"]["step"], "UNKNOWN")
        self.assertEqual(data["error"]["request_id"], "req-core-unhandled")

    async def test_get_video_rejects_path_outside_work_root(self) -> None:
        outside_dir = Path(tempfile.mkdtemp(prefix="core_api_outside_", dir=Path.cwd())).resolve()
        try:
            outside_file = outside_dir / "outside.mp4"
            outside_file.write_bytes(b"outside")
            relative_path = os.path.relpath(outside_file, Path.cwd())
            response = await self.client.get(f"/videos/{relative_path}")
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data["error"]["type"], "validation_error")
        self.assertEqual(data["error"]["code"], "VAL_VIDEO_ACCESS_DENIED")
        self.assertEqual(data["error"]["step"], "GET_VIDEO")

    async def test_get_video_missing_file_inside_work_root(self) -> None:
        missing_file = self.temp_work_root / "missing.mp4"
        relative_path = os.path.relpath(missing_file, Path.cwd())
        response = await self.client.get(f"/videos/{relative_path}")

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"]["type"], "validation_error")
        self.assertEqual(data["error"]["code"], "VAL_VIDEO_NOT_FOUND")
        self.assertEqual(data["error"]["step"], "GET_VIDEO")


if __name__ == "__main__":
    unittest.main()
