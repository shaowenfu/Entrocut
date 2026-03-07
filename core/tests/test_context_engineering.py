import unittest

from app.services.context_engineering import CoreContextEngineeringShell, NO_MEDIA_PROMPT_HINT


class CoreContextEngineeringShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shell = CoreContextEngineeringShell()

    def test_prompt_only_request_appends_no_media_hint(self) -> None:
        request = self.shell.build_chat_request(
            prompt="  帮我做一版开场  ",
            project_id="proj_001",
            user_id="user_001",
            client_context={"source": "launchpad"},
            runtime_state={"workflow_state": "prompt_input_required", "pending_prompt": "cached"},
            asset_count=0,
            clip_count=0,
            current_project=None,
        )

        self.assertTrue(request.requires_media)
        self.assertEqual(request.interaction_mode, "prompt_only")
        self.assertIn(NO_MEDIA_PROMPT_HINT, request.prompt)
        self.assertEqual(request.context["search_scope"], "none")
        self.assertTrue(request.context["pending_prompt_exists"])
        self.assertTrue(request.context["requires_media"])

    def test_media_ready_request_keeps_prompt_clean(self) -> None:
        request = self.shell.build_chat_request(
            prompt="剪成高燃混剪",
            project_id="proj_002",
            user_id="user_002",
            client_context={"clip_count_hint": 3},
            runtime_state={"workflow_state": "media_ready", "active_task_type": None},
            asset_count=2,
            clip_count=5,
            current_project={"project_id": "proj_002"},
        )

        self.assertFalse(request.requires_media)
        self.assertEqual(request.interaction_mode, "workspace_chat")
        self.assertEqual(request.prompt, "剪成高燃混剪")
        self.assertEqual(request.context["search_scope"], "clip_pool")
        self.assertTrue(request.context["current_project_present"])
        self.assertEqual(request.context["asset_count"], 2)
        self.assertEqual(request.context["clip_count"], 5)


if __name__ == "__main__":
    unittest.main()
