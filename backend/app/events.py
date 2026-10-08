"""In-process pub/sub for live updates (Server-Sent Events).

Single-process by design (one uvicorn worker). To scale out, swap publish()
for Postgres LISTEN/NOTIFY; the interface stays the same.
"""
from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from collections.abc import Iterable

_lock = threading.Lock()
_subscribers: dict[int, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(set)


def subscribe(user_id: int, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    with _lock:
        _subscribers[user_id].add((loop, queue))
    return queue


def unsubscribe(user_id: int, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    with _lock:
        _subscribers[user_id].discard((loop, queue))


def _put(queue: asyncio.Queue, event: dict) -> None:
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(event)


def publish(user_ids: Iterable[int], event: dict) -> None:
    """Thread-safe: may be called from sync endpoints running in the threadpool."""
    with _lock:
        targets = [t for uid in set(user_ids) for t in _subscribers.get(uid, ())]
    for loop, queue in targets:
        try:
            loop.call_soon_threadsafe(_put, queue, event)
        except RuntimeError:
            pass
