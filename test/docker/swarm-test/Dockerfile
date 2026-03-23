FROM python:3.11-slim

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
COPY requirements-dev.txt ./requirements-dev.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-dev.txt

COPY src ./src
COPY scripts ./scripts
COPY test ./test
COPY docs ./docs
COPY AGENTS.md ./AGENTS.md
COPY ARCHITECTURE.md ./ARCHITECTURE.md
COPY README.md ./README.md

CMD ["python", "-m", "pytest", "test/scripts/test_swarm_cli_smoke.py"]
