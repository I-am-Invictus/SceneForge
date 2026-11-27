import asyncio
import json
import time
from datetime import datetime, timezone

import websockets
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.comfyui import ComfyUIError, comfyui_client
from app.database.db import SessionLocal
from app.models import Job
from app.models.setting import utcnow
from app.services import generation
from app.services import reset as reset_service
from app.services.settings import get_effective_settings

RECONNECT_DELAY = 2.0
RESYNC_INTERVAL = 8.0
# Don't conclude a prompt is lost until it's been submitted long enough that
# ComfyUI's queue/history must reflect it. Guards the brief window between a
# prompt leaving the queue and its history entry being written.
LOST_GRACE_SECONDS = 30.0
# A job is committed as "queued" before submit_prompt returns its ComfyUI
# prompt_id. Don't declare that window a lost prompt — give the submission
# time to land before concluding it was never submitted.
SUBMIT_GRACE_SECONDS = 15.0


class JobMonitor:
    """Watches ComfyUI's WebSocket and drives SceneForge job state.

    Connects with the process-wide ``monitor_client_id`` so ComfyUI routes
    execution_start/success/error to this socket (events are addressed to the
    submitting client_id, not broadcast). Messages are routed to jobs by
    prompt_id. A periodic resync reconciles active jobs against the
    queue/history as a safety net, so jobs never get stuck even if an event
    is missed or the client_id races with another ComfyUI client.
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
                url = f"{ws_url}?clientId={comfyui_client.monitor_client_id}"
                async with websockets.connect(
                    url, ping_interval=20, open_timeout=10
                ) as ws:
                    self._connected = True
                    await self._resync()
                    next_resync = time.monotonic() + RESYNC_INTERVAL
                    while True:
                        raw: str | None = None
                        try:
                            raw = await asyncio.wait_for(
                                ws.recv(), timeout=RESYNC_INTERVAL
                            )
                        except asyncio.TimeoutError:
                            raw = None
                        if raw is not None:
                            try:
                                message = json.loads(raw)
                            except json.JSONDecodeError:
                                message = None
                            if message is not None:
                                await self._handle_message(message)
                        if time.monotonic() >= next_resync:
                            await self._resync()
                            next_resync = time.monotonic() + RESYNC_INTERVAL
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
        # A reset is wiping all data; don't recreate job outputs mid-reset.
        # The job row is removed by the reset, so there is nothing to finish.
        if reset_service.reset_in_progress():
            return
        # Retrieve outputs before flipping to "completed" so a reader never
        # sees a completed job whose images haven't been stored yet.
        try:
            await generation.retrieve_outputs(db, job)
        except Exception as exc:  # noqa: BLE001
            job.error = f"Generation completed but output retrieval failed: {exc}"
        job.status = "completed"
        job.progress = 1.0
        job.finished_at = utcnow()
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
                # Can't verify what's in flight; don't conclude anything is
                # lost this cycle.
                return
            queued_ids: set[str] = set()
            for item in list(queue.get("running", [])) + list(
                queue.get("pending", [])
            ):
                # Queue items are [number, prompt_id, prompt, extra, outputs].
                if len(item) > 1 and isinstance(item[1], str):
                    queued_ids.add(item[1])
            for job in active:
                if job.status == "queued" and not job.comfyui_prompt_id:
                    if self._job_age_seconds(job) < SUBMIT_GRACE_SECONDS:
                        # submit_generation is still assigning the prompt_id;
                        # don't conclude the prompt was never submitted.
                        continue
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
                elif history is None:
                    if self._job_age_seconds(job) < LOST_GRACE_SECONDS:
                        # Too new to be lost; the queue/history may not have
                        # reflected this prompt yet.
                        continue
                    job.status = "failed"
                    job.error = (
                        "Lost: ComfyUI has no record of this prompt "
                        "(it likely restarted before the job finished)"
                    )
                    job.finished_at = utcnow()
                else:
                    status_str = (history.get("status") or {}).get("status_str", "")
                    if status_str == "interrupted":
                        job.status = "interrupted"
                        job.error = "Interrupted in ComfyUI"
                    else:
                        job.status = "failed"
                        job.error = self._history_error(history) or (
                            "Failed in ComfyUI"
                        )
                    job.finished_at = utcnow()
            db.commit()

    @staticmethod
    def _job_age_seconds(job: Job) -> float:
        created = job.created_at
        if created is None:
            return float("inf")
        if created.tzinfo is not None:
            created = created.astimezone(timezone.utc).replace(tzinfo=None)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return (now - created).total_seconds()

    @staticmethod
    def _history_error(history: dict) -> str | None:
        for msg in (history.get("status") or {}).get("messages", []):
            if (
                isinstance(msg, list)
                and len(msg) >= 2
                and msg[0] == "execution_error"
            ):
                data = msg[1] if isinstance(msg[1], dict) else {}
                return (
                    f"{data.get('exception_type', 'Error')}: "
                    f"{data.get('exception_message', '')}"
                ).strip()
        return None

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
