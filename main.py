import os
import platform
import datetime
import subprocess
import argparse
import time
from typing import Dict, List, Optional
import schedule
import json
import gzip
import zipfile
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, timedelta
from google_drive import GoogleDriveManager


class BackupManager:
    def __init__(self, config_file: str = "BackupSettings.json"):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing BackupManager")

        self.config = self._load_config(config_file)
        self.db_config = self.config["db_config"]
        self.backup_settings = self.config["backup_settings"]
        self.gdrive_manager = None
        self.os_type = platform.system().lower()

        if self.backup_settings["google_drive"]["enabled"]:
            self.logger.info("Initializing Google Drive integration")
            self.gdrive_manager = GoogleDriveManager()
        else:
            self.logger.info("Google Drive integration disabled")

    def _load_config(self, config_file: str) -> Dict:
        """Загрузка конфигурации из JSON-файла"""
        default_config = {
            "db_config": {
                "user": "postgres",
                "host": "localhost",
                "port": "5432",
                "name": "my_database",
                "password": "password",
            },
            "backup_settings": {
                "local_backup_dir": "Backups",
                "retention": {"unit": "hours", "value": 48},
                "backup_interval": {"value": 30, "unit": "minutes"},
                "google_drive": {
                    "enabled": False,
                    "folder_name": "Backups",
                    "retention": {"unit": "days", "value": 3},
                },
                "compression": "gzip",
                "backup_name_template": "{db_name}_backup_{timestamp}.sql.gz",
            },
        }

        try:
            config_path = Path(config_file)
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    config = {**default_config, **json.load(f)}
                    self.logger.info("Configuration loaded successfully")
                    return config

            self.logger.warning("Config file not found, using default configuration")
            return default_config

        except Exception as e:
            self.logger.error("Error loading config file: %s", str(e), exc_info=True)
            return default_config

    def _save_config(self):
        """Сохранение конфигурации в JSON-файл"""
        try:
            with open("BackupSettings.json", "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.logger.debug("Configuration saved successfully")
        except Exception as e:
            self.logger.error("Error saving config: %s", str(e), exc_info=True)

    def _parse_interval(self):
        """Парсинг интервала из конфига для планировщика"""
        interval = self.backup_settings["backup_interval"]
        value = interval["value"]
        unit = interval["unit"].lower()

        if unit == "minutes":
            return schedule.every(value).minutes
        elif unit == "hours":
            return schedule.every(value).hours
        elif unit == "days":
            return schedule.every(value).days
        else:
            self.logger.error("Invalid time unit in config: %s", unit)
            raise ValueError(f"Unknown time unit: {unit}")

    def _run_command(
        self, command: List[str], env: Optional[Dict] = None
    ) -> (bool, str):  # type: ignore
        """Кроссплатформенное выполнение команды"""
        try:
            self.logger.debug("Executing command: %s", " ".join(command))
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                check=True,
                encoding="utf-8",
                env=env,
            )
            self.logger.debug("Command output: %s", result.stdout)
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            self.logger.error("Command failed: %s", e.stderr)
            return False, f"Command failed: {e.stderr}"

    def _compress_file(self, input_path: str, output_path: str) -> (bool, str):  # type: ignore
        """Сжатие файла с использованием библиотек Python"""
        compression = self.backup_settings.get("compression", "gzip")
        self.logger.info(
            "Compressing file with %s: %s -> %s", compression, input_path, output_path
        )

        try:
            if compression == "gzip":
                with open(input_path, "rb") as f_in:
                    with gzip.open(output_path, "wb") as f_out:
                        f_out.writelines(f_in)
            elif compression == "zip":
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(input_path, arcname=os.path.basename(input_path))
            else:
                raise ValueError(f"Unsupported compression: {compression}")

            self.logger.debug("File compressed successfully")
            return True, ""
        except Exception as e:
            self.logger.error("Compression failed: %s", str(e), exc_info=True)
            return False, str(e)

    def _calculate_cutoff_time(self, retention: Dict) -> datetime:
        """Вычисление временной метки для удаления"""
        unit = retention["unit"].lower()
        value = retention["value"]

        if unit == "minutes":
            return datetime.now() - timedelta(minutes=value)
        elif unit == "hours":
            return datetime.now() - timedelta(hours=value)
        elif unit == "days":
            return datetime.now() - timedelta(days=value)
        else:
            self.logger.error("Invalid retention unit: %s", unit)
            raise ValueError(f"Unsupported time unit: {unit}")

    def _delete_old_files(self, directory: Path, retention: Dict, file_pattern: str):
        """Удаление файлов по заданному временному интервалу"""
        cutoff = self._calculate_cutoff_time(retention)
        self.logger.info("Cleaning up files older than %s in %s", cutoff, directory)

        try:
            for file_path in directory.glob(file_pattern):
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff:
                    file_path.unlink()
                    self.logger.debug(
                        "Deleted old backup: %s (created %s)", file_path.name, file_time
                    )
        except Exception as e:
            self.logger.error("Error deleting old files: %s", str(e), exc_info=True)

    def _cleanup_gdrive_backups(self, retention: Dict):
        """Очистка старых бэкапов в Google Drive"""
        if not self.gdrive_manager:
            return

        try:
            cutoff = self._calculate_cutoff_time(retention)
            folder_name = self.backup_settings["google_drive"]["folder_name"]
            self.logger.info(
                "Cleaning up Google Drive backups older than %s in folder '%s'",
                cutoff,
                folder_name,
            )

            folder = self.gdrive_manager.get_folder(folder_name)
            if not folder:
                return

            query = f"'{folder['id']}' in parents and trashed=false"
            file_list = self.gdrive_manager.drive.ListFile({"q": query}).GetList()

            for file in file_list:
                if file["title"].endswith(".sql.gz"):
                    file_time = datetime.strptime(
                        file["modifiedDate"][:19], "%Y-%m-%dT%H:%M:%S"
                    )
                    if file_time < cutoff:
                        file.Delete()
                        self.logger.debug(
                            "Deleted Google Drive backup: %s (created %s)",
                            file["title"],
                            file_time,
                        )
        except Exception as e:
            self.logger.error(
                "Error cleaning Google Drive backups: %s", str(e), exc_info=True
            )

    def _cleanup_old_backups(self):
        """Удаление старых резервных копий"""
        try:
            # Очистка локальных бэкапов
            local_retention = self.backup_settings.get(
                "retention", {"unit": "hours", "value": 48}
            )
            self._delete_old_files(
                directory=Path(self.backup_settings["local_backup_dir"]),
                retention=local_retention,
                file_pattern="*.sql.gz",
            )

            # Очистка Google Drive (если включено)
            if self.gdrive_manager:
                gdrive_retention = self.backup_settings["google_drive"].get(
                    "retention", local_retention
                )
                self._cleanup_gdrive_backups(retention=gdrive_retention)

        except Exception as e:
            self.logger.error("Error cleaning old backups: %s", str(e), exc_info=True)

    def create_backup(self) -> Optional[str]:
        """Создание резервной копии базы данных"""
        backup_dir = Path(self.backup_settings["local_backup_dir"])
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = self.backup_settings["backup_name_template"].format(
            db_name=self.db_config["name"], timestamp=timestamp
        )
        sql_file = backup_dir / f"{self.db_config['name']}_backup_{timestamp}.sql"
        compressed_file = backup_dir / backup_name

        try:
            self.logger.info(
                "Starting backup process for database '%s'", self.db_config["name"]
            )

            # Команда pg_dump
            pg_dump_cmd = [
                "pg_dump",
                "-U",
                self.db_config["user"],
                "-h",
                self.db_config["host"],
                "-p",
                self.db_config["port"],
                "-d",
                self.db_config["name"],
                "-f",
                str(sql_file),
            ]

            # Устанавливаем пароль в переменную окружения
            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_config["password"]

            # Выполняем pg_dump
            success, message = self._run_command(pg_dump_cmd, env=env)
            if not success:
                self.logger.error("Backup failed: %s", message)
                return None

            # Сжимаем файл
            success, error = self._compress_file(sql_file, compressed_file)
            if not success:
                self.logger.error("Compression failed: %s", error)
                return None

            # Удаляем несжатый файл
            if compressed_file.exists():
                sql_file.unlink(missing_ok=True)
                self.logger.info("Backup created successfully: %s", compressed_file)

                # Загружаем в Google Drive
                if self.gdrive_manager:
                    folder = self.backup_settings["google_drive"]["folder_name"]
                    if self.gdrive_manager.upload_file(str(compressed_file), folder):
                        self.logger.info(
                            "Backup uploaded to Google Drive folder '%s'", folder
                        )

                self._cleanup_old_backups()
                return str(compressed_file)

            return None

        except Exception as e:
            self.logger.error("Error during backup: %s", str(e), exc_info=True)
            return None
        finally:
            if sql_file.exists():
                sql_file.unlink(missing_ok=True)

    def restore_backup(
        self, backup_file: Optional[str] = None, target_db: Optional[str] = None
    ) -> bool:
        """Восстановление базы данных"""
        try:
            if backup_file is None and self.gdrive_manager:
                folder = self.backup_settings["google_drive"]["folder_name"]
                self.logger.info(
                    "Looking for latest backup in Google Drive folder '%s'", folder
                )
                backup_file = self.gdrive_manager.get_latest_backup(folder)
                if backup_file:
                    backup_file = self.gdrive_manager.download_file(
                        backup_file, folder, self.backup_settings["local_backup_dir"]
                    )
                    self.logger.info("Downloaded latest backup: %s", backup_file)

            if not backup_file or not Path(backup_file).exists():
                self.logger.error("Backup file not found: %s", backup_file)
                return False

            target_db = target_db or self.db_config["name"]
            self.logger.info(
                "Starting restore of database '%s' from %s", target_db, backup_file
            )
            temp_sql_file = None

            # Распаковка файла
            backup_path = Path(backup_file)
            if backup_path.suffix == ".gz":
                temp_sql_file = backup_path.with_suffix("")
                with gzip.open(backup_path, "rb") as f_in:
                    with open(temp_sql_file, "wb") as f_out:
                        f_out.write(f_in.read())
                self.logger.debug("Extracted gzip backup to %s", temp_sql_file)
            elif backup_path.suffix == ".zip":
                with zipfile.ZipFile(backup_path, "r") as zipf:
                    for name in zipf.namelist():
                        if name.endswith(".sql"):
                            temp_sql_file = backup_path.parent / name
                            zipf.extract(name, backup_path.parent)
                            self.logger.debug(
                                "Extracted zip backup to %s", temp_sql_file
                            )
                            break
            else:
                temp_sql_file = backup_path

            if not temp_sql_file or not temp_sql_file.exists():
                self.logger.error("No .sql file found in backup")
                return False

            # Восстановление из SQL файла
            psql_cmd = [
                "psql",
                "-U",
                self.db_config["user"],
                "-h",
                self.db_config["host"],
                "-p",
                self.db_config["port"],
                "-d",
                target_db,
                "-f",
                str(temp_sql_file),
            ]

            env = os.environ.copy()
            env["PGPASSWORD"] = self.db_config["password"]

            success, message = self._run_command(psql_cmd, env=env)
            if not success:
                self.logger.error("Restore failed: %s", message)
                return False

            self.logger.info("Database '%s' restored successfully", target_db)
            return True

        except Exception as e:
            self.logger.error("Error during restore: %s", str(e), exc_info=True)
            return False
        finally:
            if temp_sql_file and temp_sql_file.exists():
                temp_sql_file.unlink()

    def list_backups(self):
        """Показать список доступных резервных копий"""
        backup_dir = Path(self.backup_settings["local_backup_dir"])

        if not backup_dir.exists():
            self.logger.warning("Backup directory not found: %s", backup_dir)
            return

        backups = sorted(
            [
                f
                for f in backup_dir.iterdir()
                if f.is_file() and (f.suffix == ".gz" or f.suffix == ".zip")
            ],
            key=os.path.getmtime,
            reverse=True,
        )

        if not backups:
            self.logger.info("No backups found in %s", backup_dir)
            return

        self.logger.info("Available backups in %s:", backup_dir)
        for i, backup in enumerate(backups, 1):
            size = backup.stat().st_size / (1024 * 1024)  # Size in MB
            mtime = datetime.fromtimestamp(backup.stat().st_mtime)
            print(f"{i}. {backup.name} | {mtime} | {size:.2f} MB")

    def start_scheduler(self):
        """Запуск периодического создания резервных копий"""
        interval = self.backup_settings["backup_interval"]
        retention = self.backup_settings["retention"]

        self.logger.info(
            "Starting backup scheduler. Interval: %d %s, Retention: %d %s",
            interval["value"],
            interval["unit"],
            retention["value"],
            retention["unit"],
        )

        if self.gdrive_manager:
            folder = self.backup_settings["google_drive"]["folder_name"]
            gdrive_retention = self.backup_settings["google_drive"]["retention"]
            self.logger.info(
                "Google Drive integration enabled. Folder: %s, Retention: %d %s",
                folder,
                gdrive_retention["value"],
                gdrive_retention["unit"],
            )

        # Сразу создаем первый бэкап
        self.create_backup()

        # Настраиваем периодическое выполнение
        job = self._parse_interval()
        job.do(self.create_backup)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Backup scheduler stopped by user")
        except Exception as e:
            self.logger.error("Backup scheduler failed: %s", str(e), exc_info=True)


def main():
    # Настройка основного логгера (выполняется один раз)
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        handlers=[
            logging.handlers.RotatingFileHandler(
                filename=os.path.join(logs_dir, "backup_system.log"),
                maxBytes=10 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
            logging.StreamHandler(),
        ],
    )

    # Теперь все модули используют этот логгер
    logger = logging.getLogger(__name__)
    logger.info("Starting backup system")

    parser = argparse.ArgumentParser(
        description="PostgreSQL Backup Manager with flexible retention policies"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Парсер для запуска службы
    start_parser = subparsers.add_parser("start", help="Start backup service")
    start_parser.add_argument(
        "--interval-value", type=int, help="Backup interval value"
    )
    start_parser.add_argument(
        "--interval-unit",
        choices=["minutes", "hours", "days"],
        help="Backup interval unit",
    )
    start_parser.add_argument(
        "--retention-value", type=int, help="Retention period value"
    )
    start_parser.add_argument(
        "--retention-unit",
        choices=["minutes", "hours", "days"],
        help="Retention period unit",
    )
    start_parser.add_argument(
        "--enable-gdrive", action="store_true", help="Enable Google Drive upload"
    )
    start_parser.add_argument("--gdrive-folder", help="Google Drive folder name")
    start_parser.add_argument(
        "--gdrive-retention-value", type=int, help="Google Drive retention value"
    )
    start_parser.add_argument(
        "--gdrive-retention-unit",
        choices=["minutes", "hours", "days"],
        help="Google Drive retention unit",
    )

    # Парсер для разового бэкапа
    run_once_parser = subparsers.add_parser("run-once", help="Create single backup")
    run_once_parser.add_argument(
        "--enable-gdrive", action="store_true", help="Enable Google Drive upload"
    )

    # Парсер для восстановления
    restore_parser = subparsers.add_parser(
        "restore", help="Restore database from backup"
    )
    restore_parser.add_argument("--file", help="Backup file path")
    restore_parser.add_argument("--target-db", help="Target database name")
    restore_parser.add_argument(
        "--use-gdrive", action="store_true", help="Use latest backup from Google Drive"
    )

    # Парсер для списка бэкапов
    list_parser = subparsers.add_parser("list", help="List available backups")

    args = parser.parse_args()

    # Инициализируем менеджер бэкапов
    manager = BackupManager()

    # Обновляем конфиг из аргументов командной строки
    if args.command in ["start", "run-once"]:
        if args.interval_value:
            manager.backup_settings["backup_interval"]["value"] = args.interval_value
        if args.interval_unit:
            manager.backup_settings["backup_interval"]["unit"] = args.interval_unit
        if args.retention_value:
            manager.backup_settings["retention"]["value"] = args.retention_value
        if args.retention_unit:
            manager.backup_settings["retention"]["unit"] = args.retention_unit
        if args.enable_gdrive:
            manager.backup_settings["google_drive"]["enabled"] = True
            manager.gdrive_manager = GoogleDriveManager()
        if args.gdrive_folder:
            manager.backup_settings["google_drive"]["folder_name"] = args.gdrive_folder
        if args.gdrive_retention_value:
            manager.backup_settings["google_drive"]["retention"][
                "value"
            ] = args.gdrive_retention_value
        if args.gdrive_retention_unit:
            manager.backup_settings["google_drive"]["retention"][
                "unit"
            ] = args.gdrive_retention_unit

    # Выполняем команду
    if args.command == "start":
        manager.start_scheduler()
    elif args.command == "run-once":
        manager.create_backup()
    elif args.command == "restore":
        if args.use_gdrive and manager.gdrive_manager:
            manager.restore_backup()
        elif args.file:
            manager.restore_backup(args.file, args.target_db)
        else:
            logging.error("Please specify backup file or use --use-gdrive")
    elif args.command == "list":
        manager.list_backups()

    # Сохраняем обновлённый конфиг
    manager._save_config()


if __name__ == "__main__":
    main()
