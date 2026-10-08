from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import config
from .api import auth, expenses, groups, misc, settlements
from .db import SessionLocal
from .reminders import run_reminders

log = logging.getLogger("fairshare")


async def _reminder_loop() -> None:
    while True:
        await asyncio.sleep(config.REMINDER_INTERVAL_SECONDS)
        try:
            def work() -> int:
                with SessionLocal() as db:
                    return run_reminders(db)

            sent = await asyncio.to_thread(work)
            if sent:
                log.info("reminders sent: %s", sent)
        except Exception:  # keep the loop alive
            log.exception("reminder loop failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_reminder_loop())
    yield
    task.cancel()


app = FastAPI(title="Fairshare", version="0.1.0", lifespan=lifespan)
for module in (auth, groups, expenses, settlements, misc):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
