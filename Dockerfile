# Базовый образ с нужной версией PostgreSQL
FROM python:3.13-slim

# Устанавливаем системные зависимости и правильную версию PostgreSQL
RUN apt update && apt upgrade -y && apt-get install -y \
    gcc \
    python3-dev \
    wget \
    gnupg \
    && sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' &&  wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - && apt update -y && apt install postgresql-client-17
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