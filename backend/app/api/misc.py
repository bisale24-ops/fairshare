from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import events
from ..db import get_db
from ..deps import current_user, stream_user
from ..models import Notification, Outbox, User

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db), unread_only: bool = False):
    q = select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(100)
    if unread_only:
        q = q.where(Notification.read.is_(False))
    return [
        {"id": n.id, "group_id": n.group_id, "kind": n.kind, "text": n.text, "read": n.read, "created_at": n.created_at}
        for n in db.scalars(q)
    ]


@router.post("/notifications/read")
def mark_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))):
        n.read = True
    db.commit()
    return {"ok": True}


@router.get("/me/outbox")
def my_outbox(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """E-mail is stubbed: this shows the messages that were 'sent' to your address."""
    rows = db.scalars(select(Outbox).where(Outbox.to_email == user.email).order_by(Outbox.id.desc()).limit(50))
    return [{"id": r.id, "subject": r.subject, "body": r.body, "kind": r.kind, "created_at": r.created_at} for r in rows]


@router.get("/stream")
async def stream(request: Request, user: User = Depends(stream_user)):
    loop = asyncio.get_running_loop()
    queue = events.subscribe(user.id, loop)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            yield f"data: {json.dumps({'type': 'hello'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            events.unsubscribe(user.id, loop, queue)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
