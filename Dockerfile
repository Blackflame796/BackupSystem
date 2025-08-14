# Базовый образ с нужной версией PostgreSQL
FROM python:3.13-slim

# Устанавливаем системные зависимости и правильную версию PostgreSQL
RUN apt update && apt upgrade -y && apt-get install -y \
    gcc \
    python3-dev \
    wget \
    gnupg \
    postgresql-17 postgresql-contrib-17
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