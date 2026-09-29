FROM ghcr.io/astral-sh/uv:0.12.0 AS uv
FROM python:3.14-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
USER 10001:10001
CMD ["djgurda"]
