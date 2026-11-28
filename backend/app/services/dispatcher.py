import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.comfyui import ComfyUIError, comfyui_client
from app.database.db import SessionLocal
from app.models import Job
from app.models.setting import utcnow
from app.services import generation
from app.services import reset as reset_service
from app.services.settings import get_effective_settings

# How often the dispatcher looks for work, and how many pending jobs it will
# hand to ComfyUI in a single pass. ComfyUI itself runs one inference at a time
# and keeps the rest in its own FIFO queue, so draining a bounded batch (rather
# than one at a time) matches "submit multiple prompts through ComfyUI" while
# avoiding a pathological burst of uploads.
DISPATCH_INTERVAL = 1.0
DISPATCH_BATCH = 8


class JobDispatcher:
    """Feeds SceneForge's persistent queue to ComfyUI.

    Jobs are persisted as ``pending`` the moment they are submitted. This task
    takes the oldest ``pending`` jobs (FIFO) and, only while ComfyUI is
    reachable, prepares and submits them to ComfyUI. If ComfyUI is down the
    jobs simply stay ``pending`` and are dispatched once it returns, so a
    temporary unavailability never loses a queued job.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None

    async def start(self) -> None:
        # Reconcile any job left "dispatching" by a crash before starting, so it
        # is failed (never re-submitted) and can't run twice.
        self.reconcile_interrupted()
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
                await self._dispatch_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep dispatching on any hiccup
                pass
            await asyncio.sleep(DISPATCH_INTERVAL)

    async def _dispatch_cycle(self) -> None:
        if reset_service.reset_in_progress():
            return
        with SessionLocal() as db:
            base_url = get_effective_settings(db)["comfyui_http_url"]
        # Gate on ComfyUI availability: if we can't even read its queue, don't
        # try to submit — the jobs stay pending for the next cycle.
        try:
            await comfyui_client.get_queue(base_url)
        except ComfyUIError:
            return
        with SessionLocal() as db:
            if reset_service.reset_in_progress():
                return
            pending = list(
                db.scalars(
                    select(Job)
                    .where(Job.status == "pending")
                    .order_by(Job.created_at.asc(), Job.id.asc())
                    .limit(DISPATCH_BATCH)
                )
            )
        for queued in pending:
            if reset_service.reset_in_progress():
                break
            # Re-read in a fresh session so we never dispatch a stale object that
            # may have been removed or advanced in the meantime.
            with SessionLocal() as db:
                job = db.get(Job, queued.id)
                if job is None or job.status != "pending":
                    continue
                await generation.dispatch_job(db, job)

    def reconcile_interrupted(self) -> None:
        """Fail jobs that a crash left mid-dispatch.

        A ``dispatching`` job with no ``comfyui_prompt_id`` may or may not have
        reached ComfyUI before the process died; we can't tell, so the only way
        to guarantee it never runs twice is to fail it rather than re-submit.
        (A ``pending`` job was never submitted, so it is left for the loop to
        dispatch normally.)
        """
        with SessionLocal() as db:
            stuck = list(db.scalars(select(Job).where(Job.status == "dispatching")))
            for job in stuck:
                if not job.comfyui_prompt_id:
                    job.status = "failed"
                    job.error = (
                        "Dispatch was interrupted by an application restart; the "
                        "job was not re-submitted to avoid running it twice."
                    )
                    job.finished_at = utcnow()
                else:
                    # Defensive: prompt_id was assigned, so it was submitted.
                    job.status = "queued"
            db.commit()


job_dispatcher = JobDispatcher()
