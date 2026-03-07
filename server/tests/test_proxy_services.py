import os
import unittest
from unittest.mock import patch

from app.adapters.contracts import ProxyResult
from app.adapters.mock_providers import MockEmbeddingAdapter, MockVectorSearchAdapter
from app.repositories.usage_repository import UsageRepositoryShell
from app.services.proxy_services import EmbeddingProxyService, LLMProxyService, VectorSearchService


class _StubLlmAdapter:
    def plan(self, prompt: str, *, context: dict[str, object]) -> ProxyResult:
        return ProxyResult(
            ok=True,
            payload={
                "reasoning_summary": "",
                "ops": [{"op": "keep"}, "drop-me"],
                "storyboard_scenes": [{"id": "", "title": "", "duration": "", "intent": ""}],
                "context": context,
                "prompt": prompt,
            },
        )


class ProxyServiceTests(unittest.TestCase):
    def test_llm_proxy_normalizes_payload_shape(self) -> None:
        service = LLMProxyService(adapter=_StubLlmAdapter())

        result = service.plan_edit("make it punchy", context={"source": "unit"})

        self.assertTrue(result.ok)
        self.assertEqual(result.payload["reasoning_summary"], "mock_llm:make it punchy")
        self.assertEqual(result.payload["ops"], [{"op": "keep"}])
        self.assertEqual(len(result.payload["storyboard_scenes"]), 1)
        self.assertEqual(result.payload["storyboard_scenes"][0]["id"], "scene_1")
        self.assertEqual(result.payload["storyboard_scenes"][0]["duration"], "4s")

    def test_vector_search_requires_user_scope_and_enforces_quota(self) -> None:
        with patch.dict(os.environ, {"SERVER_VECTOR_SEARCH_MAX_REQUESTS_PER_USER": "1"}, clear=False):
            repository = UsageRepositoryShell()
            service = VectorSearchService(
                adapter=MockVectorSearchAdapter(),
                usage_repository=repository,
            )

            invalid = service.semantic_search("snow", top_k=3, filters={"project_id": "proj"})
            first = service.semantic_search(
                "snow",
                top_k=3,
                filters={"user_id": "user_001", "project_id": "proj"},
            )
            second = service.semantic_search(
                "snow",
                top_k=3,
                filters={"user_id": "user_001", "project_id": "proj"},
            )

            self.assertFalse(invalid.ok)
            self.assertEqual(invalid.payload["error_code"], "SERVER_VECTOR_FILTER_INVALID")
            self.assertTrue(first.ok)
            self.assertFalse(second.ok)
            self.assertEqual(second.payload["error_code"], "SERVER_PROVIDER_QUOTA_EXCEEDED")

    def test_vector_upsert_adds_scope_and_search_isolated_by_project(self) -> None:
        adapter = MockVectorSearchAdapter()
        service = VectorSearchService(adapter=adapter, usage_repository=None)

        upsert = service.upsert_clips(
            [
                {
                    "clip_id": "clip_1",
                    "asset_id": "asset_1",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "score": 0.9,
                    "description": "snow jump",
                }
            ],
            user_id="user_002",
            project_id="proj_a",
        )
        other = service.upsert_clips(
            [
                {
                    "clip_id": "clip_2",
                    "asset_id": "asset_2",
                    "start_ms": 0,
                    "end_ms": 1200,
                    "score": 0.8,
                    "description": "city walk",
                }
            ],
            user_id="user_002",
            project_id="proj_b",
        )
        search = service.semantic_search(
            "snow",
            top_k=5,
            filters={"user_id": "user_002", "project_id": "proj_a"},
        )

        self.assertTrue(upsert.ok)
        self.assertTrue(other.ok)
        self.assertTrue(search.ok)
        self.assertEqual(search.payload["hits"][0]["clip_id"], "clip_1")
        self.assertTrue(all(hit["project_id"] == "proj_a" for hit in search.payload["hits"]))

    def test_embedding_proxy_enforces_quota(self) -> None:
        with patch.dict(os.environ, {"SERVER_EMBEDDING_MAX_REQUESTS_PER_USER": "1"}, clear=False):
            repository = UsageRepositoryShell()
            service = EmbeddingProxyService(
                adapter=MockEmbeddingAdapter(),
                usage_repository=repository,
            )

            first = service.embed_query("powder snow", user_id="user_003")
            second = service.embed_query("powder snow", user_id="user_003")

            self.assertTrue(first.ok)
            self.assertFalse(second.ok)
            self.assertEqual(second.payload["error_code"], "SERVER_PROVIDER_QUOTA_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
