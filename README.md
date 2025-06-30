# 🗄️ PostgreSQL Backup System

  

![Docker](https://img.shields.io/badge/Docker-✓-blue?logo=docker)

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-✓-blue?logo=postgresql)

![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python)

  

## 🌟 Основные возможности

  

- **Автоматические бэкапы** по расписанию

- **Гибкие настройки** хранения (минуты/часы/дни)

- **Двойное хранилище**: локальное + Google Drive

- **Кроссплатформенность** (Linux/Windows/macOS)

- **Восстановление** из любой точки истории

- **Ротация логов** (10 МБ max)

  

## 🚀 Быстрый старт

  

### Требования

  

- Python 3.13+

- PostgreSQL 15+

- Docker (опционально)

  

```bash

# 1. Клонировать репозиторий

git clone https://github.com/yourrepo/backup-system.git

cd backup-system

  

# 2. Установить зависимости

pip install -r requirements.txt

  

# 3. Настроить конфиг (см. раздел ниже)

cp BackupSettings.example.json BackupSettings.json

  

# 4. Запустить

python main.py start

```

  

## ⚙️ Конфигурация

  

#### Файл BackupSettings.json:

  

```json

{

"db_config": {

"user": "postgres",

"host": "localhost",

"port": "5432",

"name": "my_db",

"password": "secret"

},

"backup_settings": {

"local_backup_dir": "Backups",

"retention": {

"unit": "hours",

"value": 48

},

"backup_interval": {

"value": 30,

"unit": "minutes"

},

"google_drive": {

"enabled": false,

"folder_name": "PG_Backups"

},

"compression": "gzip"

}

}

```

  
### 🛠️ Команды

  

| Команда    | Описание                  | Пример                                        |
| ---------- | ------------------------- | --------------------------------------------- |
| `start`    | Запуск службы бэкапов     | `python main.py start`                        |
| `run-once` | Создать разовый бэкап     | `python main.py run-once`                     |
| `restore`  | Восстановить БД           | `python main.py restore --file backup.sql.gz` |
| `list`     | Показать доступные бэкапы | `python main.py list`                         |

## 🖥️ Использование

### Основные команды:


```bash
# Запуск службы бэкапов
python main.py start
# Создать разовый бэкап
python main.py run-once
# Восстановить базу
python main.py restore --file backups/mydatabase_backup_2024-01-01_12-00-00.sql.gz
# Список доступных бэкапов
python main.py list
```

  

## Параметры командной строки

  

| Параметр            | Описание                               |
| ------------------- | -------------------------------------- |
| `--interval-value`  | Числовое значение интервала            |
| `--interval-unit`   | Единицы измерения (minutes/hours/days) |
| `--retention-value` | Время хранения бэкапов                 |
| `--enable-gdrive`   | Включить Google Drive                  |
| `--gdrive-folder`   | Название папки в Google Drive          |

## ☁️ Google Drive интеграция

### Включите в конфиге:

```json

"google_drive": {

"enabled": true,

"folder_name": "My_Backups"

}

```

## 🐳 Docker

### Запуск с Docker Compose:

1. Создайте `.env` файл:

```env

DB_USER=postgres

DB_PASSWORD=yourpassword

DB_NAME=mydatabase

Запустите систему:

```

  2. Запустите систему:

```bash

docker-compose up -d --build

```
### Структура Docker:

- ##### backup-system - сервис резервного копирования
- ##### postgres - контейнер PostgreSQL (опционально)
## 📝 Логирование

##### Логи сохраняются в директории logs/:
- ##### backup_system.log - основные события
- ##### google_drive.log - операции с Google Drive (если включено)
### Настройки логов:
- ##### Максимальный размер: 10 МБ
- ##### Хранение: 3 резервные копии
- ##### Формат: YYYY-MM-DD HH:MM:SS | LEVEL | MESSAGE
## 🧪 Примеры

#### Пример 1: Запуск с интервалом 1 час

```bash
python main.py start --interval-value 1 --interval-unit hours
```
#### Пример 2: Восстановление из Google Drive

```bash
python main.py restore --use-gdrive --target-db restored_db
```
#### Пример 3: С Docker и кастомными настройками

```bash
docker-compose run backup-system python main.py start \
--interval-value 2 \
--interval-unit hours \
--enable-gdrive
```

##  📜 [Лицензия](./LICENSE)