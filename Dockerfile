FROM python:3.11-slim

WORKDIR /app

# Копируем только зависимости и код
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Бот будет читать переменные из окружения контейнера.
CMD ["python", "bot.py"]