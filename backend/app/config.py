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
