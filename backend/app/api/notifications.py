"""Notification routes (M6): REST listing/read markers + SSE live stream.

The SSE stream authenticates via ``?token=`` (EventSource cannot set
headers — see deps.get_current_user_sse) and pushes one
``event: notification`` per new notification, with heartbeat comment lines
every 25s so proxies do not time out the connection.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notification, User
from ..notify import notification_payload, subscribe, unsubscribe
from ..schemas import NotificationOut
from .deps import get_current_user, get_current_user_sse

router = APIRouter(tags=["notifications"])

HEARTBEAT_SECONDS = 25
LIST_LIMIT = 50


def _notification_out(notification: Notification) -> NotificationOut:
    return NotificationOut(**notification_payload(notification))


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(LIST_LIMIT)
    )
    return [_notification_out(n) for n in db.scalars(stmt).all()]


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def read_all_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read.is_(False))
        .values(read=True)
    )
    db.commit()


@router.post(
    "/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT
)
def read_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    notification.read = True
    db.commit()


@router.get("/notifications/stream")
async def stream_notifications(
    request: Request,
    user: User = Depends(get_current_user_sse),
) -> StreamingResponse:
    queue = subscribe(user.id)

    async def events() -> AsyncIterator[str]:
        try:
            # An opening comment line so clients/proxies see the stream start.
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield f"event: notification\ndata: {json.dumps(event)}\n\n"
        finally:
            unsubscribe(user.id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
