FROM python:3.11-slim

WORKDIR /app

# Dockerfile лежит в deploy/, но build context остается корнем репозитория.

# Системные пакеты, необходимые runtime-обработчикам.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Копируем манифест зависимостей отдельно, чтобы сохранить кэш слоя для pip install.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем только runtime-код приложения.
COPY src ./src

# Подготавливаем runtime-директории, которые не приезжают из репозитория.
RUN mkdir -p /app/src/data \
    && chmod -R 0777 /app/src/data

CMD ["python", "-m", "src.main"]
