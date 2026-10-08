import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://fairshare:fairshare@localhost:5432/fairshare")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_RECEIPT_BYTES = int(os.getenv("MAX_RECEIPT_BYTES", str(5 * 1024 * 1024)))
REMINDER_INTERVAL_SECONDS = int(os.getenv("REMINDER_INTERVAL_SECONDS", "60"))
REMINDER_MIN_GAP_DAYS = int(os.getenv("REMINDER_MIN_GAP_DAYS", "7"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
TOKEN_TTL_DAYS = int(os.getenv("TOKEN_TTL_DAYS", "30"))
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "8"))
LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))
# Behind the bundled nginx, every request comes from the proxy's address; the real client address is in X-Forwarded-For,
# which nginx sets itself (overwriting anything the client sent). Trust it only when the API is reachable through that proxy.
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
# The e-mail transport is a stub and the "mailbox" endpoint shows those messages to whoever registered the address.
# Turn it off (DEV_MAILBOX=0) as soon as a real transport replaces the stub.
DEV_MAILBOX = os.getenv("DEV_MAILBOX", "1") == "1"
