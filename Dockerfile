# Базовый образ Python
FROM python:3.13-slim

# Устанавливаем системные зависимости для psycopg2 и других пакетов
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install --upgrade pip

# Рабочая директория
WORKDIR /app

# Копируем только файлы, необходимые для установки зависимостей
COPY requirements.txt ./

# Устанавливаем зависимости
RUN pip install -r requirements.txt
# Копируем основной файл и остальное содержимое
COPY main.py .
COPY . .  

# Создаем директорию для логов
RUN mkdir -p /app/logs

# Команда для запуска
CMD ["python", "main.py", "start"]