import re
from pathlib import Path

def patch_file():
    with open('store.py', 'r', encoding='utf8') as f:
        content = f.read()

    # We want to replace the `async def _run_assets_import` method body.
    # The easiest way is using a regex that captures from `async def _run_assets_import` to the start of `async def queue_chat`
    
    new_method = """    async def _run_assets_import(self, project_id: str, task: TaskModel, asset_ids: set[str]) -> None:
        import httpx
        from ingestion import detect_scenes, extract_and_stitch_frames
        from config import SERVER_BASE_URL
        from schemas import ClipModel
        from helpers import _entity_id, _asset_clip_counts

        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        current_task = task
        try:
            previous_capabilities = self._derive_project_capabilities(record)
            previous_summary_state = record.get("summary_state")
            segmenting_at = _now_iso()
            running = current_task.model_copy(
                update={
                    "status": "running",
                    "progress": 10,
                    "message": "Segmenting media into clips",
                    "updated_at": segmenting_at,
                }
            )
            running_task = self._upsert_active_task(record, running)
            draft = EditDraftModel.model_validate(record["edit_draft"])
            segmenting_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="segmenting",
                progress=10,
                updated_at=segmenting_at,
                bump_version=False,
            )
            record["edit_draft"] = segmenting_draft.model_dump()
            record["project"]["updated_at"] = segmenting_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=segmenting_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": segmenting_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(segmenting_draft, asset_ids)},
            )
            await self.emit(project_id, "task.updated", {"task": running_task})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )
            current_task = running

            imported_assets = [asset for asset in segmenting_draft.assets if asset.id in asset_ids]
            
            # 1. Segmenting
            new_clips = []
            for asset in imported_assets:
                video_path = asset.source_path
                if not video_path:
                    continue
                # run CPU intensive detection in thread
                scene_list = await asyncio.to_thread(detect_scenes, video_path)
                for i, (start_ms, end_ms) in enumerate(scene_list, start=1):
                    new_clips.append(
                        ClipModel(
                            id=_entity_id("clip"),
                            asset_id=asset.id,
                            source_start_ms=start_ms,
                            source_end_ms=end_ms,
                            visual_desc=f"{asset.name} candidate clip {i}",
                            semantic_tags=[],
                        )
                    )

            clip_counts = _asset_clip_counts(new_clips)

            # Update state to vectorizing
            vectorizing_at = _now_iso()
            vectorizing_task = current_task.model_copy(
                update={
                    "progress": 50,
                    "message": "Vectorizing clips for retrieval",
                    "updated_at": vectorizing_at,
                }
            )
            vectorizing_running_task = self._upsert_active_task(record, vectorizing_task)
            vectorizing_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="vectorizing",
                progress=50,
                clip_counts=clip_counts,
                indexed_clip_counts={asset_id: 0 for asset_id in asset_ids},
                append_clips=new_clips,
                updated_at=vectorizing_at,
                bump_version=True,
            )
            record["edit_draft"] = vectorizing_draft.model_dump()
            record["project"]["updated_at"] = vectorizing_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=vectorizing_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": vectorizing_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(vectorizing_draft, asset_ids)},
            )
            await self.emit(project_id, "task.updated", {"task": vectorizing_running_task})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )
            current_task = vectorizing_task

            # 2. Extract frames and send to vectorizer
            auth_session = await auth_session_store.snapshot()
            access_token = auth_session.get("access_token")
            if not access_token:
                raise RuntimeError("Access token missing, please login.")

            # Batch vectorize
            batch_size = 10
            for i in range(0, len(new_clips), batch_size):
                batch = new_clips[i:i+batch_size]
                docs = []
                for clip in batch:
                    asset = next(a for a in imported_assets if a.id == clip.asset_id)
                    video_path = asset.source_path
                    if not video_path:
                        continue
                    b64 = await asyncio.to_thread(extract_and_stitch_frames, video_path, clip.source_start_ms, clip.source_end_ms)
                    docs.append({
                        "id": clip.id,
                        "content": {"image_base64": b64},
                        "fields": {
                            "clip_id": clip.id,
                            "asset_id": clip.asset_id,
                            "project_id": project_id,
                            "source_start_ms": clip.source_start_ms,
                            "source_end_ms": clip.source_end_ms,
                            "frame_count": 4,
                        }
                    })

                # send request to server
                if docs:
                    endpoint_url = f"{SERVER_BASE_URL}/v1/assets/vectorize"
                    request_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    }
                    async with httpx.AsyncClient(timeout=300) as client:
                        response = await client.post(endpoint_url, json={"docs": docs}, headers=request_headers)
                        response.raise_for_status()

                # Update progress
                progress = 50 + int(50 * (i + len(batch)) / max(1, len(new_clips)))
                current_task = current_task.model_copy(update={"progress": progress})
                self._upsert_active_task(record, current_task)
                await self.emit(project_id, "task.updated", {"task": current_task})

            # Update stage to ready
            ready_at = _now_iso()
            ready_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="ready",
                progress=100,
                clip_counts=clip_counts,
                indexed_clip_counts=clip_counts,
                updated_at=ready_at,
                bump_version=False,
            )
            record["edit_draft"] = ready_draft.model_dump()
            record["project"]["updated_at"] = ready_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=ready_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": ready_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(ready_draft, asset_ids)},
            )
            await self.emit(project_id, "project.updated", {"project": record["project"]})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )

            succeeded = current_task.model_copy(
                update={
                    "status": "succeeded",
                    "progress": 100,
                    "message": "Media ingest completed",
                    "result": {
                        "asset_ids": sorted(asset_ids),
                        "clip_count": sum(clip_counts.values()),
                    },
                    "updated_at": _now_iso(),
                }
            )
            succeeded_task = self._upsert_active_task(record, succeeded)
            await self.emit(
                project_id,
                "task.updated",
                {"task": succeeded_task},
            )
        except Exception as exc:
            import traceback
            import logging
            logging.getLogger(__name__).error(f"Asset import failed: {exc}", exc_info=True)
            record = self.get_project_or_raise(project_id)
            self._ensure_record_defaults(record)
            previous_capabilities = self._derive_project_capabilities(record)
            previous_summary_state = record.get("summary_state")
            failed_at = _now_iso()
            error_body = {"code": "MEDIA_IMPORT_FAILED", "message": str(exc)}
            draft = EditDraftModel.model_validate(record["edit_draft"])
            failed_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="failed",
                progress=None,
                last_error=error_body,
                updated_at=failed_at,
                bump_version=False,
            )
            record["edit_draft"] = failed_draft.model_dump()
            record["project"]["updated_at"] = failed_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=failed_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": failed_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(failed_draft, asset_ids)},
            )
            await self.emit(project_id, "project.updated", {"project": record["project"]})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )
            failed_task = current_task.model_copy(
                update={
                    "status": "failed",
                    "message": "Media ingest failed",
                    "error": error_body,
                    "updated_at": failed_at,
                }
            )
            await self.emit(
                project_id,
                "task.updated",
                {"task": failed_task.model_dump()},
            )
"""
    
    # regex replace
    pattern = re.compile(r'    async def _run_assets_import\(self, project_id: str, task: TaskModel, asset_ids: set\[str\]\) -> None:.*?    async def queue_chat\(', re.DOTALL)
    new_content = pattern.sub(new_method + "\n    async def queue_chat(", content)
    
    if new_content == content:
        print("Replacement failed. Pattern not matched.")
    else:
        with open('store.py', 'w', encoding='utf8') as f:
            f.write(new_content)
        print("Replacement succeeded.")

if __name__ == '__main__':
    patch_file()
