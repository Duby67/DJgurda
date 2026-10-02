FROM ghcr.io/astral-sh/uv:0.12.0 AS uv
FROM denoland/deno:bin-2.9.7 AS deno
FROM mwader/static-ffmpeg:9.0.2 AS ffmpeg
FROM python:3.14-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
# Precompiled bytecode: the read-only runtime would otherwise compile every module on each start,
# which at the development CPU limit outlasts the healthcheck start period.
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
# ffmpeg merges YouTube streams; deno solves YouTube's JavaScript challenges for yt-dlp.
COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg
COPY --from=deno /deno /usr/local/bin/deno
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
# A new named volume copies this owner, so the non-root user can write the database.
RUN mkdir /data && chown 10001:10001 /data
USER 10001:10001
CMD ["djgurda"]
