FROM python:3.11-slim

WORKDIR /app

# Dockerfile lives in deploy/, but the build context remains the repository root.

# System packages required by runtime handlers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest separately to preserve layer caching for pip installs.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy only runtime application code.
COPY src ./src

# Prepare runtime directories.
RUN mkdir -p /app/src/data \
    && chmod -R 0777 /app/src/data

CMD ["python", "-m", "src.main"]
