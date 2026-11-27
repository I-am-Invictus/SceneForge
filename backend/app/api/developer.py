import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.schemas import (
    DeveloperStatus,
    ResetConfirm,
    ResetReportOut,
)
from app.services import reset as reset_service

router = APIRouter(prefix="/api/developer", tags=["developer"])

# The typed confirmation the client must send to authorise the reset.
_CONFIRM_WORD = "RESET"


def _dev_mode_enabled() -> bool:
    return bool(get_settings().sceneforge_dev_mode)


@router.get("/status", response_model=DeveloperStatus)
async def status() -> DeveloperStatus:
    # Always available so the frontend can decide whether to show the
    # (hidden-by-default) Developer Options section. Reveals only a boolean.
    return DeveloperStatus(dev_mode=_dev_mode_enabled())


@router.post("/reset", response_model=ResetReportOut)
async def reset(payload: ResetConfirm) -> ResetReportOut:
    # Security: the destructive action is only reachable when developer mode is
    # enabled (SCENEFORGE_DEV_MODE). Hiding the nav entry is NOT the protection;
    # this gate is. When disabled we 404 so the endpoint does not advertise
    # itself.
    if not _dev_mode_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    if payload.confirm != _CONFIRM_WORD:
        raise HTTPException(
            status_code=400, detail="Confirmation word is incorrect."
        )

    base = get_settings().data_dirs["base"]
    report = await asyncio.to_thread(reset_service.reset_image_data, base)
    result = ResetReportOut(**report.to_dict())
    if not result.ok:
        # Return the structured report (with diagnostics) at 500 so the client
        # and server logs can investigate the failure.
        return JSONResponse(status_code=500, content=result.model_dump())
    return result
