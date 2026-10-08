FROM python:3.12-slim
RUN pip install --no-cache-dir uv==0.12.7
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY . .
RUN useradd --system --uid 10001 app && mkdir -p /data/uploads && chown -R app /data /app
USER app
ENV PATH="/app/.venv/bin:$PATH" UPLOAD_DIR=/data/uploads
# --timeout-graceful-shutdown: live streams never end by themselves; give them 5 s on a stop, then close them.
# One worker on purpose: live updates use an in-process hub (see app/events.py).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --timeout-graceful-shutdown 5"]
