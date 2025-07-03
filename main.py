import os
import platform
import subprocess
import argparse
import time
import schedule
import json
import gzip
import zipfile
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from google_drive import GoogleDriveManager


class BackupManager:
    def __init__(self, config_file: str = "BackupSettings.json"):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing BackupManager")

        self.config = self._load_config(config_file)
        self.db_config = self.config["db_config"]
        self.backup_settings = self.config["backup_settings"]
        self.os_type = platform.system().lower()
        self.folder_id = self.config["folder_id"]
        self.gdrive_manager = (
            GoogleDriveManager()
            if self.backup_settings["google_drive"].get("enabled")
            else None
        )

    def _load_config(self, config_file: str) -> Dict:
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
                    "folder_id": "",
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
                    return {**default_config, **json.load(f)}
            return default_config
        except Exception as e:
            self.logger.error("Error loading config: %s", str(e), exc_info=True)
            return default_config

    def _run_command(
        self, command: List[str], env: Optional[Dict] = None
    ) -> (bool, str):
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                check=True,
                encoding="utf-8",
                env=env,
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr

    def _compress_file(self, input_path: str, output_path: str) -> (bool, str):
        try:
            if self.backup_settings["compression"] == "gzip":
                with (
                    open(input_path, "rb") as f_in,
                    gzip.open(output_path, "wb") as f_out,
                ):
                    f_out.writelines(f_in)
            elif self.backup_settings["compression"] == "zip":
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(input_path, arcname=os.path.basename(input_path))
            else:
                return False, "Unsupported compression format"
            return True, ""
        except Exception as e:
            return False, str(e)

    def _calculate_cutoff(self, retention: Dict) -> datetime:
        value = retention["value"]
        unit = retention["unit"].lower()
        delta = {
            "minutes": timedelta(minutes=value),
            "hours": timedelta(hours=value),
            "days": timedelta(days=value),
        }.get(unit)
        return datetime.now() - delta if delta else datetime.now()

    def _delete_old_files(self, directory: Path, retention: Dict):
        cutoff = self._calculate_cutoff(retention)
        for file_path in directory.glob("*.sql.*"):
            if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff:
                file_path.unlink(missing_ok=True)

    def _cleanup_old_backups(self):
        local_dir = Path(self.backup_settings["local_backup_dir"])
        self._delete_old_files(local_dir, self.backup_settings["retention"])
        if self.gdrive_manager:
            retention = self.backup_settings["google_drive"]["retention"]
            self.gdrive_manager.cleanup_old_backups(
                folder_id=self.folder_id, retention_days=retention.get("value", 3)
            )

    def create_backup(self) -> Optional[str]:
        backup_dir = Path(self.backup_settings["local_backup_dir"])
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        sql_file = backup_dir / f"{self.db_config['name']}_backup_{timestamp}.sql"
        compressed_file = backup_dir / self.backup_settings[
            "backup_name_template"
        ].format(db_name=self.db_config["name"], timestamp=timestamp)

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
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_config["password"]

        success, msg = self._run_command(pg_dump_cmd, env)
        if not success:
            self.logger.error("Backup failed: %s", msg)
            return None

        success, msg = self._compress_file(str(sql_file), str(compressed_file))
        if success:
            sql_file.unlink(missing_ok=True)
            if self.gdrive_manager:
                self.gdrive_manager.upload_file(str(compressed_file), self.folder_id)
            self._cleanup_old_backups()
            return str(compressed_file)

        self.logger.error("Compression failed: %s", msg)
        return None

    def start_scheduler(self):
        interval = self.backup_settings["backup_interval"]
        unit = interval["unit"].lower()
        value = interval["value"]

        schedule_map = {
            "minutes": schedule.every(value).minutes,
            "hours": schedule.every(value).hours,
            "days": schedule.every(value).days,
        }

        job = schedule_map.get(unit)
        if job:
            job.do(self.create_backup)
        else:
            self.logger.error("Invalid scheduling unit: %s", unit)
            return

        self.create_backup()

        while True:
            schedule.run_pending()
            time.sleep(1)


def main():
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

    parser = argparse.ArgumentParser(description="PostgreSQL Backup Manager")
    parser.add_argument("start", help="Start scheduler", nargs="?")
    args = parser.parse_args()

    manager = BackupManager()
    manager.start_scheduler()


if __name__ == "__main__":
    main()
