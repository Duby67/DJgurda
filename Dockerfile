FROM python:3.11-slim

# Устанавливаем FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую дерикторию
WORKDIR /app

# Копируем только зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаём папку для временных файлов
RUN mkdir -p /app/src/data/temp_files

# Запускаем бота как модуль
CMD ["python", "-m", "src.main"]