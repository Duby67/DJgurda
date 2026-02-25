FROM python:3.11-slim

# Устанавливаем FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем только зависимости и код
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Бот будет читать переменные из окружения контейнера.
CMD ["python", "bot.py"]