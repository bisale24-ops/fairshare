import logging

from sqlalchemy.orm import Session

from .models import Outbox

log = logging.getLogger("fairshare.mail")


def send_email(db: Session, to_email: str, subject: str, body: str, kind: str, group_id: int | None = None) -> None:
    """Stub transport: the message is stored in the outbox table and logged."""
    db.add(Outbox(to_email=to_email, subject=subject, body=body, kind=kind, group_id=group_id))
    log.info("EMAIL to=%s kind=%s subject=%s", to_email, kind, subject)
