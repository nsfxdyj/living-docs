"""In-app notifications (M6): persistence + in-process SSE fan-out.

Notifications are persisted rows (listable, markable as read, surviving
restarts) and are additionally pushed to live SSE subscribers through
in-memory asyncio queues. This is deliberately single-process (PLAN.md:
SSE, no WebSocket); a multi-worker deployment would need a real broker.
"""

import asyncio
import json
from collections import defaultdict

from sqlalchemy.orm import Session

from .models import Notification


class _Subscriber:
    """One open SSE connection, bound to the event loop that owns it."""

    __slots__ = ("queue", "loop")

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self.queue = queue
        self.loop = loop


_subscribers: dict[int, list[_Subscriber]] = defaultdict(list)


def subscribe(user_id: int) -> asyncio.Queue:
    """Register a new SSE subscriber; must be called from its event loop."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers[user_id].append(_Subscriber(queue, asyncio.get_running_loop()))
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue) -> None:
    subs = _subscribers.get(user_id)
    if not subs:
        return
    subs[:] = [sub for sub in subs if sub.queue is not queue]
    if not subs:
        _subscribers.pop(user_id, None)


def publish(user_id: int, event: dict) -> None:
    """Push an event to all of the user's live SSE connections.

    Producers run in worker threads (sync route handlers), so hop onto the
    subscriber's own event loop instead of touching its queue directly.
    """
    for sub in list(_subscribers.get(user_id, [])):
        sub.loop.call_soon_threadsafe(sub.queue.put_nowait, event)


def notification_payload(notification: Notification) -> dict:
    """The wire shape shared by the REST API and SSE events."""
    return {
        "id": notification.id,
        "workspace_id": notification.workspace_id,
        "kind": notification.kind,
        "payload": json.loads(notification.payload),
        "read": notification.read,
        "created_at": notification.created_at.isoformat(),
    }


def create_notification(
    db: Session,
    *,
    user_id: int,
    workspace_id: int,
    kind: str,
    payload: dict,
) -> Notification:
    """Persist a notification and push it to the user's SSE subscribers.

    Callers skip self-notification (actor == recipient) before calling
    this. ``flush`` assigns the id/created_at so the SSE event is complete;
    the surrounding route still owns the final commit.
    """
    notification = Notification(
        user_id=user_id,
        workspace_id=workspace_id,
        kind=kind,
        payload=json.dumps(payload),
    )
    db.add(notification)
    db.flush()
    publish(user_id, notification_payload(notification))
    return notification
