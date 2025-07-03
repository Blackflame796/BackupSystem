# Базовый образ с нужной версией PostgreSQL
FROM python:3.13-slim

# Устанавливаем системные зависимости и правильную версию PostgreSQL
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    wget \
    gnupg \
    && echo "deb http://apt.postgresql.org/pub/repos/apt/ bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
    && apt-get update \
    && apt-get install -y postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry и зависимости Python
RUN pip install --upgrade pip

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt ./

# Устанавливаем Python-зависимости
RUN pip install -r requirements.txt

# Копируем остальные файлы
COPY . .

# Создаем директорию для логов
RUN mkdir -p /app/logs

# Команда для запуска
CMD ["python", "main.py", "start"]