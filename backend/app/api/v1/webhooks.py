from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from whop_sdk import APIWebhookValidationError, WhopError

from backend.app.core.config import get_settings
from backend.app.db.session import async_session_factory
from backend.app.services.billing_service import process_whop_webhook_event
from backend.app.services.whop_client import get_whop_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _handle_whop_event(event) -> None:
    async with async_session_factory() as db:
        try:
            await process_whop_webhook_event(db, event)
        except Exception:
            await db.rollback()
            logger.exception("Failed to process Whop webhook %s", getattr(event, "id", None))
            raise


@router.post("/whop", status_code=status.HTTP_200_OK)
async def whop_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    settings = get_settings()
    if not settings.whop_webhook_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Whop webhooks are not configured")

    client = get_whop_client()
    if client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Whop client is not configured")

    payload = (await request.body()).decode("utf-8")
    headers = {key: value for key, value in request.headers.items()}

    try:
        event = client.webhooks.unwrap(payload, headers=headers)
    except APIWebhookValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature") from exc
    except WhopError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    background_tasks.add_task(_handle_whop_event, event)
    return {"status": "accepted"}
