import asyncio
import json

import websockets
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.comfyui import ComfyUIError, comfyui_client
from app.database.db import SessionLocal
from app.models import Job
from app.models.setting import utcnow
from app.services import generation
from app.services.settings import get_effective_settings

RECONNECT_DELAY = 2.0


class JobMonitor:
    """Watches ComfyUI's WebSocket and drives SceneForge job state.

    A single shared connection receives all client events; messages are
    routed to jobs by prompt_id. On (re)connect, jobs with no ComfyUI
    trace are reconciled against the queue/history so restarts and
    disconnects never leave jobs stuck.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        while True:
            try:
                with SessionLocal() as db:
                    ws_url = get_effective_settings(db)["comfyui_ws_url"]
                async with websockets.connect(
                    ws_url, ping_interval=20, open_timeout=10
                ) as ws:
                    self._connected = True
                    await self._resync()
                    async for raw in ws:
                        try:
                            message = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - reconnect on any failure
                pass
            self._connected = False
            await asyncio.sleep(RECONNECT_DELAY)

    async def _job_by_prompt_id(self, db: Session, prompt_id: str) -> Job | None:
        return db.scalar(select(Job).where(Job.comfyui_prompt_id == prompt_id))

    async def _handle_message(self, message: dict) -> None:
        event = message.get("type")
        payload = message.get("data", {})
        prompt_id = payload.get("prompt_id")
        if not prompt_id:
            return
        with SessionLocal() as db:
            job = await self._job_by_prompt_id(db, prompt_id)
            if job is None:
                return
            await self._apply_event(db, job, event, payload)

    async def _apply_event(
        self, db: Session, job: Job, event: str, payload: dict
    ) -> None:
        if event == "execution_start" and job.status == "queued":
            job.status = "running"
            job.started_at = utcnow()
        elif event == "progress":
            maximum = payload.get("max") or 1
            job.progress = min(1.0, (payload.get("value") or 0) / maximum)
        elif event == "execution_success":
            await self._complete(db, job)
        elif event == "execution_error":
            job.status = "failed"
            job.error = (
                f"{payload.get('exception_type', 'Error')}: "
                f"{payload.get('exception_message', '')}"
            ).strip()
            job.finished_at = utcnow()
        elif event == "execution_interrupted":
            job.status = "interrupted"
            job.finished_at = utcnow()
        db.commit()

    async def _complete(self, db: Session, job: Job) -> None:
        job.status = "completed"
        job.progress = 1.0
        job.finished_at = utcnow()
        db.commit()
        try:
            await generation.retrieve_outputs(db, job)
        except Exception as exc:  # noqa: BLE001
            job.error = f"Generation completed but output retrieval failed: {exc}"
            db.commit()

    async def _resync(self) -> None:
        with SessionLocal() as db:
            urls = get_effective_settings(db)
            base_url = urls["comfyui_http_url"]
            active = list(
                db.scalars(
                    select(Job).where(Job.status.in_(("queued", "running")))
                )
            )
            if not active:
                return
            try:
                queue = await comfyui_client.get_queue(base_url)
            except ComfyUIError:
                queue = {"running": [], "pending": []}
            queued_ids = {
                item[0] for item in queue.get("running", [])
            } | {item[0] for item in queue.get("pending", [])}
            for job in active:
                if job.status == "queued" and not job.comfyui_prompt_id:
                    job.status = "failed"
                    job.error = "Prompt was never submitted to ComfyUI"
                    job.finished_at = utcnow()
                    continue
                if not job.comfyui_prompt_id:
                    continue
                if job.comfyui_prompt_id in queued_ids:
                    continue
                try:
                    history = await comfyui_client.get_history(
                        base_url, job.comfyui_prompt_id
                    )
                except ComfyUIError:
                    continue
                if history is not None and history.get("outputs"):
                    await self._complete(db, job)
                else:
                    job.status = "failed"
                    job.error = (
                        "Lost: ComfyUI has no record of this prompt "
                        "(it likely restarted before the job finished)"
                    )
                    job.finished_at = utcnow()
            db.commit()

    async def cancel(self, client_id: str) -> bool:
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.client_id == client_id))
            if job is None:
                return False
            if job.status not in ("queued", "running"):
                return False
            if not job.comfyui_prompt_id:
                job.status = "interrupted"
                job.finished_at = utcnow()
                db.commit()
                return True
            base_url = get_effective_settings(db)["comfyui_http_url"]
        try:
            await comfyui_client.interrupt(base_url, job.comfyui_prompt_id)
        except ComfyUIError:
            return False
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.client_id == client_id))
            if job is not None and job.status == "running":
                job.status = "interrupted"
                job.finished_at = utcnow()
                db.commit()
        return True


job_monitor = JobMonitor()
