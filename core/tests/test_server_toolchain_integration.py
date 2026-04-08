from __future__ import annotations

import importlib.util
import os
import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
import sqlite3

from fastapi.testclient import TestClient

CORE_DIR = Path(__file__).resolve().parents[1]
if str(CORE_DIR) not in sys.path:
    sys.path.append(str(CORE_DIR))

CORE_TEST_APPDATA_DIR = tempfile.TemporaryDirectory()
os.environ["ENTROCUT_APP_DATA_ROOT"] = CORE_TEST_APPDATA_DIR.name

CORE_SERVER_SPEC = importlib.util.spec_from_file_location("core_server_module", CORE_DIR / "server.py")
if CORE_SERVER_SPEC is None or CORE_SERVER_SPEC.loader is None:
    raise RuntimeError("Unable to load core/server.py for tests.")
core_server = importlib.util.module_from_spec(CORE_SERVER_SPEC)
sys.modules["core_server_module"] = core_server
CORE_SERVER_SPEC.loader.exec_module(core_server)


class CoreChatPlannerSkeletonTest(unittest.TestCase):
    def setUp(self) -> None:
        core_server.store.reset_for_test()
        core_server.auth_session_store.reset_for_test()
        self.client = TestClient(core_server.app)
        self.client.__enter__()
        
        self.detect_scenes_patcher = patch("ingestion.detect_scenes", return_value=[(0, 6000), (6000, 12000)])
        self.detect_scenes_mock = self.detect_scenes_patcher.start()
        
        self.extract_frames_patcher = patch("ingestion.extract_and_stitch_frames", return_value="dummy_b64")
        self.extract_frames_mock = self.extract_frames_patcher.start()
        
        class _MockResponse:
            status_code = 200
            def raise_for_status(self): pass
            
        class _MockClientAsyncContextManager:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
            async def post(self, *args, **kwargs):
                return _MockResponse()
                
        self.httpx_patcher = patch("store.AsyncClient", return_value=_MockClientAsyncContextManager())
        self.httpx_mock = self.httpx_patcher.start()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.detect_scenes_patcher.stop()
        self.extract_frames_patcher.stop()
        self.httpx_patcher.stop()

    def _create_project(self) -> tuple[str, list[str]]:
        response = self.client.post(
            "/api/v1/projects",
            json={
                "title": "Planner Skeleton Test",
                "prompt": "做一个旅行视频的开头",
                "media": {
                    "files": [
                        {"name": "travel-day-1.mp4", "path": "/tmp/travel-day-1.mp4"},
                        {"name": "travel-day-2.mp4", "path": "/tmp/travel-day-2.mp4"},
                    ]
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        project_id = body["project"]["id"]
        clip_ids = [clip["id"] for clip in body["workspace"]["edit_draft"]["clips"]]
        return project_id, clip_ids

    def _set_auth_session(self) -> None:
        response = self.client.post(
            "/api/v1/auth/session",
            json={"access_token": "tok_test_access_token_value_12345", "user_id": "user_planner"},
        )
        self.assertEqual(response.status_code, 200)

    def _poll_workspace(self, project_id: str, *, assistant_turns: int = 1) -> dict[str, Any]:
        deadline = time.time() + 5
        last_body: dict[str, Any] | None = None
        while time.time() < deadline:
            response = self.client.get(f"/api/v1/projects/{project_id}")
            self.assertEqual(response.status_code, 200)
            last_body = response.json()
            workspace = last_body["workspace"]
            assistants = [turn for turn in workspace["chat_turns"] if turn.get("role") == "assistant"]
            if len(assistants) >= assistant_turns:
                return workspace
            time.sleep(0.1)
        self.fail(f"timed out waiting for assistant turn, last workspace={last_body}")

    def _poll_task_idle(self, project_id: str) -> dict[str, Any]:
        deadline = time.time() + 5
        last_body: dict[str, Any] | None = None
        while time.time() < deadline:
            response = self.client.get(f"/api/v1/projects/{project_id}")
            self.assertEqual(response.status_code, 200)
            last_body = response.json()
            if last_body["workspace"]["active_task"] is None:
                return last_body["workspace"]
            time.sleep(0.1)
        self.fail(f"timed out waiting for task idle, last workspace={last_body}")

    def test_chat_runs_planner_first_and_applies_placeholder_edit(self) -> None:
        project_id, clip_ids = self._create_project()
        self._set_auth_session()

        planner_json = (
            '{"status":"final","reasoning_summary":"plan first, tools later",'
            '"assistant_reply":"我先基于当前草案给出一个占位初剪，后续再接 planner 驱动工具链。",'
            '"tool_name":null,"tool_input_summary":null,"draft_strategy":"placeholder_first_cut"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            self.assertTrue(url.endswith("/v1/chat/completions"))

            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 80, "completion_tokens": 28, "total_tokens": 108},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            chat_response = self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "做一个旅行视频的开头，强调出发感"},
            )
            self.assertEqual(chat_response.status_code, 200)
            workspace = self._poll_workspace(project_id)

        self.assertGreaterEqual(len(workspace["edit_draft"]["shots"]), 1)
        self.assertEqual(workspace["edit_draft"]["shots"][0]["clip_id"], clip_ids[0])
        assistant_turn = [turn for turn in workspace["chat_turns"] if turn.get("role") == "assistant"][-1]
        self.assertIn("占位初剪", assistant_turn["reasoning_summary"])
        op_actions = [op["action"] for op in assistant_turn["ops"]]
        self.assertIn("planner_context_assembled", op_actions)
        self.assertIn("planner_decision_finalized", op_actions)
        self.assertIn("agent_tool_execution_loop", op_actions)
        self.assertIn("placeholder_edit_draft_applied", op_actions)
        self.assertEqual(core_server.store.pending_background_task_count(project_id), 0)

    def test_chat_runs_tool_step_then_replans_to_final(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        planner_sequence = [
            (
                '{"status":"requires_tool","reasoning_summary":"need retrieve before finalize",'
                '"assistant_reply":"我先检索候选片段。","tool_name":"retrieve",'
                '"tool_input_summary":"departure","draft_strategy":"no_change"}'
            ),
            (
                '{"status":"final","reasoning_summary":"retrieval done, finalize",'
                '"assistant_reply":"已检索完成并生成建议。","tool_name":null,'
                '"tool_input_summary":null,"draft_strategy":"placeholder_first_cut"}'
            ),
        ]

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_sequence.pop(0)}}],
                        "usage": {"prompt_tokens": 70, "completion_tokens": 24, "total_tokens": 94},
                    }

                text = "ok"

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            chat_response = self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "做一个旅行视频的开头，强调出发感"},
            )
            self.assertEqual(chat_response.status_code, 200)
            workspace = self._poll_workspace(project_id)

        self.assertGreaterEqual(len(workspace["edit_draft"]["shots"]), 1)
        assistant_turn = [turn for turn in workspace["chat_turns"] if turn.get("role") == "assistant"][-1]
        self.assertIn("检索完成", assistant_turn["reasoning_summary"])
        self.assertEqual(core_server.store.pending_background_task_count(project_id), 0)

    def test_chat_fails_when_tool_execution_invalid(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        planner_json = (
            '{"status":"requires_tool","reasoning_summary":"invalid tool requested",'
            '"assistant_reply":"调用不存在工具。","tool_name":"transcode",'
            '"tool_input_summary":"{}", "draft_strategy":"no_change"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 55, "completion_tokens": 18, "total_tokens": 73},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "做一个旅行视频的开头"},
            )
            workspace = self._poll_task_idle(project_id)
        self.assertEqual(len([turn for turn in workspace["chat_turns"] if turn.get("role") == "assistant"]), 0)
        self.assertEqual(workspace["summary_state"], "attention_required")
        self.assertEqual(core_server.store.pending_background_task_count(project_id), 0)

    def test_chat_tool_patch_writeback_updates_draft(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()
        planner_sequence = [
            (
                '{"status":"requires_tool","reasoning_summary":"patch once",'
                '"assistant_reply":"先执行一次 patch。","tool_name":"patch",'
                '"tool_input_summary":"{}", "draft_strategy":"no_change"}'
            ),
            (
                '{"status":"final","reasoning_summary":"patched done",'
                '"assistant_reply":"补丁已完成。","tool_name":null,'
                '"tool_input_summary":null,"draft_strategy":"no_change"}'
            ),
        ]

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_sequence.pop(0)}}],
                        "usage": {"prompt_tokens": 66, "completion_tokens": 21, "total_tokens": 87},
                    }

                text = "ok"

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "补一刀节奏"},
            )
            workspace = self._poll_workspace(project_id)
        self.assertGreaterEqual(len(workspace["edit_draft"]["shots"]), 1)
        self.assertEqual(core_server.store.pending_background_task_count(project_id), 0)

    def test_chat_fails_when_loop_exhausts_iterations(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()
        planner_json = (
            '{"status":"requires_tool","reasoning_summary":"keep reading",'
            '"assistant_reply":"继续读取。","tool_name":"read",'
            '"tool_input_summary":"{}", "draft_strategy":"no_change"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52},
                    }

                text = planner_json

            return _DummyResponse()

        with patch.object(core_server, "AGENT_LOOP_MAX_ITERATIONS", 1):
            with patch("httpx.AsyncClient.post", fake_post):
                self.client.post(
                    f"/api/v1/projects/{project_id}/chat",
                    json={"prompt": "一直循环"},
                )
                workspace = self._poll_task_idle(project_id)
        self.assertEqual(len([turn for turn in workspace["chat_turns"] if turn.get("role") == "assistant"]), 0)
        self.assertEqual(workspace["summary_state"], "attention_required")
        self.assertEqual(core_server.store.pending_background_task_count(project_id), 0)

    def test_chat_planner_context_contains_structured_tools_and_scope(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        captured_context: dict[str, Any] = {}
        planner_json = (
            '{"status":"final","reasoning_summary":"context checked",'
            '"assistant_reply":"上下文已完成结构化。","tool_name":null,'
            '"tool_input_summary":null,"draft_strategy":"no_change"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            messages = json.get("messages", [])
            user_message = next((item for item in messages if item.get("role") == "user"), {})
            captured_context.update(core_server.json.loads(user_message.get("content", "{}")))

            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 70, "completion_tokens": 24, "total_tokens": 94},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            chat_response = self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "做一个旅行视频开头", "target": {"scene_id": "scene_focus_1"}},
            )
            self.assertEqual(chat_response.status_code, 200)
            workspace = self._poll_workspace(project_id)

        self.assertEqual(captured_context["scope"]["scope_type"], "scene")
        self.assertEqual(captured_context["project"]["summary_state"], "editing")
        self.assertEqual(captured_context["capabilities"]["chat_mode"], "editing")
        self.assertTrue(captured_context["media"]["retrieval_ready"])
        self.assertEqual(captured_context["runtime_state"]["focus_state"]["scene_id"], "scene_focus_1")
        tool_names = [item["name"] for item in captured_context["tools"]["available_tools"]]
        self.assertIn("read", tool_names)
        self.assertEqual(workspace["runtime_state"]["focus_state"]["scene_id"], "scene_focus_1")

    def test_planning_only_chat_blocks_retrieve_tool_request(self) -> None:
        response = self.client.post("/api/v1/projects", json={})
        self.assertEqual(response.status_code, 200)
        project_id = response.json()["project"]["id"]
        self._set_auth_session()

        planner_json = (
            '{"status":"requires_tool","reasoning_summary":"try retrieve before media ready",'
            '"assistant_reply":"先检索素材。","tool_name":"retrieve",'
            '"tool_input_summary":"travel", "draft_strategy":"no_change"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "先帮我规划一个旅行片头"},
            )
            workspace = self._poll_task_idle(project_id)

        self.assertEqual(len([turn for turn in workspace["chat_turns"] if turn.get("role") == "assistant"]), 0)
        self.assertEqual(
            workspace["runtime_state"]["execution_state"]["last_error"]["code"],
            "PLANNER_REQUESTED_BLOCKED_TOOL",
        )
        self.assertEqual(workspace["runtime_state"]["goal_state"]["brief"], "先帮我规划一个旅行片头")
        self.assertEqual(workspace["runtime_state"]["focus_state"]["scope_type"], "project")

    def test_retrieve_tool_updates_runtime_retrieval_state(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        planner_sequence = [
            (
                '{"status":"requires_tool","reasoning_summary":"retrieve candidates first",'
                '"assistant_reply":"我先召回候选。","tool_name":"retrieve",'
                '"tool_input_summary":"departure", "draft_strategy":"no_change"}'
            ),
            (
                '{"status":"final","reasoning_summary":"retrieval completed",'
                '"assistant_reply":"已完成候选召回。","tool_name":null,'
                '"tool_input_summary":null, "draft_strategy":"no_change"}'
            ),
        ]

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_sequence.pop(0)}}],
                        "usage": {"prompt_tokens": 55, "completion_tokens": 18, "total_tokens": 73},
                    }

                text = "ok"

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "帮我找出发镜头"},
            )
            workspace = self._poll_workspace(project_id)

        retrieval_state = workspace["runtime_state"]["retrieval_state"]
        self.assertEqual(retrieval_state["last_query"], "departure")
        self.assertGreaterEqual(len(retrieval_state["candidate_clip_ids"]), 1)
        self.assertEqual(workspace["runtime_state"]["execution_state"]["last_tool_name"], "retrieve")

    def test_create_project_initializes_local_persistence_and_workspace_dir(self) -> None:
        response = self.client.post(
            "/api/v1/projects",
            json={
                "title": "Local Persistence Bootstrap",
                "media": {
                    "files": [
                        {"name": "bootstrap.mp4", "path": "/tmp/bootstrap.mp4"},
                    ]
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        project_id = body["project"]["id"]
        workspace = body["workspace"]

        self.assertEqual(body["project"]["lifecycle_state"], "active")
        self.assertEqual(body["project"]["summary_state"], "editing")
        self.assertEqual(workspace["summary_state"], "editing")
        self.assertIn("runtime_state", workspace)
        self.assertIn("capabilities", workspace)
        self.assertIn("media_summary", workspace)
        self.assertIn("active_tasks", workspace)
        self.assertEqual(workspace["active_tasks"], [])

        self.assertTrue(core_server.store.db_path.exists())
        workspace_dir = core_server.store.app_data_root / "projects" / project_id
        self.assertTrue(workspace_dir.exists())
        self.assertTrue((workspace_dir / "thumbs").exists())
        self.assertTrue((workspace_dir / "preview").exists())
        self.assertTrue((workspace_dir / "exports").exists())
        self.assertTrue((workspace_dir / "temp").exists())
        self.assertTrue((workspace_dir / "proxies").exists())

        reloaded_store = core_server.InMemoryProjectStore(app_data_root=core_server.store.app_data_root)
        persisted = reloaded_store.get_project_or_raise(project_id)
        self.assertEqual(persisted["project"]["title"], "Local Persistence Bootstrap")
        self.assertEqual(persisted["workspace_dir"], str(workspace_dir))

    def test_create_project_allows_empty_input_and_returns_state_skeleton(self) -> None:
        response = self.client.post("/api/v1/projects", json={})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        workspace = body["workspace"]

        self.assertEqual(body["project"]["title"], "Untitled Project")
        self.assertEqual(body["project"]["lifecycle_state"], "active")
        self.assertEqual(body["project"]["summary_state"], "blank")
        self.assertEqual(workspace["summary_state"], "blank")
        self.assertEqual(workspace["media_summary"]["asset_count"], 0)
        self.assertEqual(workspace["media_summary"]["retrieval_ready"], False)
        self.assertEqual(workspace["capabilities"]["can_send_chat"], True)
        self.assertEqual(workspace["capabilities"]["chat_mode"], "planning_only")
        self.assertEqual(workspace["capabilities"]["can_retrieve"], False)
        self.assertEqual(workspace["runtime_state"]["goal_state"]["brief"], None)
        self.assertEqual(workspace["active_tasks"], [])

    def test_empty_project_allows_planning_only_chat(self) -> None:
        response = self.client.post("/api/v1/projects", json={})
        self.assertEqual(response.status_code, 200)
        project_id = response.json()["project"]["id"]
        self._set_auth_session()

        planner_json = (
            '{"status":"final","reasoning_summary":"need more constraints",'
            '"assistant_reply":"请先告诉我目标时长和风格。","tool_name":null,'
            '"tool_input_summary":null,"draft_strategy":"no_change"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 50, "completion_tokens": 18, "total_tokens": 68},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            chat_response = self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "我想先规划一个旅行视频"},
            )
            self.assertEqual(chat_response.status_code, 200)
            workspace = self._poll_workspace(project_id)

        assistant_turn = [turn for turn in workspace["chat_turns"] if turn.get("role") == "assistant"][-1]
        self.assertIn("目标时长", assistant_turn["reasoning_summary"])
        self.assertEqual(len(workspace["edit_draft"]["shots"]), 0)

    def test_persistence_tables_restore_workspace_state_after_reload(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        planner_json = (
            '{"status":"final","reasoning_summary":"persist reload",'
            '"assistant_reply":"持久化重载测试。","tool_name":null,'
            '"tool_input_summary":null,"draft_strategy":"placeholder_first_cut"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 80, "completion_tokens": 28, "total_tokens": 108},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            chat_response = self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "做一个旅行视频的开头，强调出发感"},
            )
            self.assertEqual(chat_response.status_code, 200)
            workspace = self._poll_workspace(project_id)

        self.assertGreaterEqual(workspace["last_event_sequence"] if "last_event_sequence" in workspace else 0, 0)
        reloaded_store = core_server.InMemoryProjectStore(app_data_root=core_server.store.app_data_root)
        persisted = reloaded_store.get_project_or_raise(project_id)
        self.assertEqual(len(persisted["chat_turns"]), 2)
        self.assertGreaterEqual(len(persisted["edit_draft"]["shots"]), 1)
        self.assertGreaterEqual(int(persisted["sequence"]), 1)

        connection = sqlite3.connect(core_server.store.db_path)
        try:
            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            self.assertTrue(
                {"projects", "edit_drafts", "chat_turns", "tasks", "project_runtime", "assets", "core_auth_session"}.issubset(table_names)
            )
            self.assertNotIn("project_records", table_names)

            project_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            self.assertIn("lifecycle_state", project_columns)

            runtime_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(project_runtime)").fetchall()
            }
            self.assertIn("runtime_state_json", runtime_columns)
            self.assertIn("summary_state", runtime_columns)

            task_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            self.assertIn("slot", task_columns)
            self.assertIn("owner_type", task_columns)
            self.assertIn("owner_id", task_columns)
            self.assertIn("result_json", task_columns)
            self.assertIn("error_json", task_columns)

            asset_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(assets)").fetchall()
            }
            self.assertIn("processing_stage", asset_columns)
            self.assertIn("processing_progress", asset_columns)
            self.assertIn("clip_count", asset_columns)
            self.assertIn("indexed_clip_count", asset_columns)
            self.assertIn("last_error_json", asset_columns)
            self.assertIn("updated_at", asset_columns)

            task_count = connection.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            self.assertGreaterEqual(task_count, 1)
        finally:
            connection.close()

    def test_import_keeps_source_path_reference_without_copying_media(self) -> None:
        source_dir = Path(CORE_TEST_APPDATA_DIR.name) / "external_media"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_file = source_dir / "reference-only.mp4"
        source_file.write_text("source media placeholder\n", encoding="utf-8")

        response = self.client.post(
            "/api/v1/projects",
            json={
                "title": "Reference Only Media",
                "media": {
                    "files": [
                        {"name": source_file.name, "path": str(source_file)},
                    ]
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        project_id = body["project"]["id"]
        assets = body["workspace"]["edit_draft"]["assets"]
        self.assertEqual(assets[0]["source_path"], str(source_file))

        workspace_dir = core_server.store.app_data_root / "projects" / project_id
        self.assertFalse((workspace_dir / source_file.name).exists())
        self.assertFalse((workspace_dir / "temp" / source_file.name).exists())
        self.assertTrue(source_file.exists())

    def test_media_task_does_not_block_chat_task_slot(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        import_response = self.client.post(
            f"/api/v1/projects/{project_id}/assets:import",
            json={"media": {"files": [{"name": "extra.mp4", "path": "/tmp/extra.mp4"}]}},
        )
        self.assertEqual(import_response.status_code, 200)
        self.assertEqual(import_response.json()["task"]["slot"], "media")

        planner_json = (
            '{"status":"final","reasoning_summary":"slot-compatible chat",'
            '"assistant_reply":"媒体任务运行时仍允许 chat。","tool_name":null,'
            '"tool_input_summary":null,"draft_strategy":"placeholder_first_cut"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 80, "completion_tokens": 28, "total_tokens": 108},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            chat_response = self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "在素材继续导入时先做一个开头"},
            )
            self.assertEqual(chat_response.status_code, 200)
            self.assertEqual(chat_response.json()["task"]["slot"], "agent")
            workspace = self._poll_workspace(project_id)

        self.assertGreaterEqual(len(workspace["edit_draft"]["shots"]), 1)

    def test_assets_import_emits_asset_capability_and_summary_events(self) -> None:
        response = self.client.post("/api/v1/projects", json={})
        self.assertEqual(response.status_code, 200)
        project_id = response.json()["project"]["id"]
        self._set_auth_session()

        with self.client.websocket_connect(f"/api/v1/projects/{project_id}/events") as websocket:
            snapshot_event = websocket.receive_json()
            self.assertEqual(snapshot_event["event"], "workspace.snapshot")

            import_response = self.client.post(
                f"/api/v1/projects/{project_id}/assets:import",
                json={"media": {"files": [{"name": "pending.mp4", "path": "/tmp/pending.mp4"}]}},
            )
            self.assertEqual(import_response.status_code, 200)

            observed_events: list[dict[str, Any]] = []
            for _ in range(5):
                observed_events.append(websocket.receive_json())

        event_names = [event["event"] for event in observed_events]
        self.assertIn("asset.updated", event_names)
        self.assertIn("capabilities.updated", event_names)
        self.assertIn("project.summary.updated", event_names)

        asset_event = next(event for event in observed_events if event["event"] == "asset.updated")
        self.assertEqual(asset_event["data"]["assets"][0]["processing_stage"], "pending")

        capability_event = next(event for event in observed_events if event["event"] == "capabilities.updated")
        self.assertEqual(capability_event["data"]["capabilities"]["chat_mode"], "planning_only")
        self.assertIn(
            "media_index_not_ready",
            capability_event["data"]["capabilities"]["blocking_reasons"],
        )

        summary_event = next(event for event in observed_events if event["event"] == "project.summary.updated")
        self.assertEqual(summary_event["data"]["summary_state"], "media_processing")
        task_event = next(event for event in observed_events if event["event"] == "task.updated")
        self.assertNotIn("workflow_state", task_event["data"])

    def test_partial_media_processing_keeps_editing_capability_when_existing_clips_exist(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        async def slow_to_thread(func, *args, **kwargs) -> Any:
            await asyncio.sleep(0.5)
            if "detect_scenes" in str(func):
                return [(0, 6000), (6000, 12000)]
            return "dummy_b64"

        with patch("store.asyncio.to_thread", slow_to_thread):
            import_response = self.client.post(
                f"/api/v1/projects/{project_id}/assets:import",
                json={"media": {"files": [{"name": "extra.mp4", "path": "/tmp/extra.mp4"}]}},
            )
            self.assertEqual(import_response.status_code, 200)

            workspace_response = self.client.get(f"/api/v1/projects/{project_id}")
            self.assertEqual(workspace_response.status_code, 200)
            workspace = workspace_response.json()["workspace"]

            self.assertEqual(workspace["media_summary"]["asset_count"], 3)
            self.assertGreaterEqual(
                workspace["media_summary"]["pending_asset_count"] + workspace["media_summary"]["processing_asset_count"],
                1,
            )
            self.assertEqual(workspace["media_summary"]["ready_asset_count"], 2)
            self.assertEqual(workspace["media_summary"]["retrieval_ready"], True)
            self.assertEqual(workspace["capabilities"]["chat_mode"], "editing")
            self.assertEqual(workspace["capabilities"]["can_retrieve"], True)

            final_workspace = self._poll_task_idle(project_id)

        self.assertEqual(final_workspace["media_summary"]["asset_count"], 3)
        self.assertEqual(final_workspace["media_summary"]["ready_asset_count"], 3)
        self.assertEqual(final_workspace["media_summary"]["indexed_clip_count"], 6)

    def test_reloaded_store_preserves_asset_processing_state(self) -> None:
        response = self.client.post(
            "/api/v1/projects",
            json={
                "title": "Asset State Reload",
                "media": {
                    "files": [
                        {"name": "reload-a.mp4", "path": "/tmp/reload-a.mp4"},
                        {"name": "reload-b.mp4", "path": "/tmp/reload-b.mp4"},
                    ]
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        project_id = response.json()["project"]["id"]

        reloaded_store = core_server.InMemoryProjectStore(app_data_root=core_server.store.app_data_root)
        persisted = reloaded_store.get_project_or_raise(project_id)
        assets = persisted["edit_draft"]["assets"]

        self.assertEqual(len(assets), 2)
        self.assertTrue(all(asset["processing_stage"] == "ready" for asset in assets))
        self.assertTrue(all(asset["clip_count"] == 2 for asset in assets))
        self.assertTrue(all(asset["indexed_clip_count"] == 2 for asset in assets))

    def test_export_writes_artifact_into_project_workspace_exports_dir(self) -> None:
        project_id, _ = self._create_project()
        self._set_auth_session()

        planner_json = (
            '{"status":"final","reasoning_summary":"export setup",'
            '"assistant_reply":"先生成一个占位初剪。","tool_name":null,'
            '"tool_input_summary":null,"draft_strategy":"placeholder_first_cut"}'
        )

        async def fake_post(_self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
            class _DummyResponse:
                status_code = 200

                @staticmethod
                def json() -> dict[str, Any]:
                    return {
                        "choices": [{"message": {"content": planner_json}}],
                        "usage": {"prompt_tokens": 80, "completion_tokens": 28, "total_tokens": 108},
                    }

                text = planner_json

            return _DummyResponse()

        with patch("httpx.AsyncClient.post", fake_post):
            chat_response = self.client.post(
                f"/api/v1/projects/{project_id}/chat",
                json={"prompt": "做一个旅行视频的开头，强调出发感"},
            )
            self.assertEqual(chat_response.status_code, 200)
            self._poll_workspace(project_id)

        export_response = self.client.post(
            f"/api/v1/projects/{project_id}/export",
            json={"format": "mp4", "quality": "preview"},
        )
        self.assertEqual(export_response.status_code, 200)
        workspace = self._poll_task_idle(project_id)

        reloaded_store = core_server.InMemoryProjectStore(app_data_root=core_server.store.app_data_root)
        persisted = reloaded_store.get_project_or_raise(project_id)
        export_result = persisted["export_result"]
        self.assertIsNotNone(export_result)
        output_url = str(export_result["output_url"])
        self.assertIn("/projects/", output_url)
        self.assertIn("/exports/", output_url)
        export_path = Path(output_url.removeprefix("file://"))
        self.assertTrue(export_path.exists())
        self.assertEqual(export_path.parent.name, "exports")
        self.assertEqual(workspace["summary_state"], "editing")

    def test_core_auth_session_persists_across_reload(self) -> None:
        response = self.client.post(
            "/api/v1/auth/session",
            json={"access_token": "tok_test_access_token_value_12345", "user_id": "user_persisted"},
        )
        self.assertEqual(response.status_code, 200)

        reloaded_auth_store = core_server.CoreAuthSessionStore(app_data_root=core_server.store.app_data_root)
        persisted = asyncio.run(reloaded_auth_store.snapshot())
        self.assertEqual(persisted["access_token"], "tok_test_access_token_value_12345")
        self.assertEqual(persisted["user_id"], "user_persisted")


if __name__ == "__main__":
    unittest.main()
