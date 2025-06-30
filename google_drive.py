import os
import logging
import logging.handlers
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from typing import Optional, Dict, List
from pathlib import Path


class GoogleDriveManager:
    def __init__(self, credentials_file: str = "credentials.txt"):
        self.credentials_file = credentials_file
        self.logger = logging.getLogger(__name__)
        self.drive = self._initialize_drive()

    def _initialize_drive(self) -> Optional[GoogleDrive]:
        """Инициализация подключения к Google Drive"""
        try:
            self.logger.info("Initializing Google Drive connection")
            gauth = GoogleAuth()

            if os.path.exists(self.credentials_file):
                self.logger.debug("Loading credentials from %s", self.credentials_file)
                gauth.LoadCredentialsFile(self.credentials_file)
            else:
                self.logger.warning("Credentials file not found")

            if gauth.credentials is None:
                self.logger.info("Starting OAuth authentication via local webserver")
                gauth.LocalWebserverAuth()
            elif gauth.access_token_expired:
                self.logger.info("Refreshing expired access token")
                gauth.Refresh()
            else:
                self.logger.info("Using existing valid credentials")
                gauth.Authorize()

            gauth.SaveCredentialsFile(self.credentials_file)
            self.logger.info("Successfully initialized Google Drive connection")
            return GoogleDrive(gauth)

        except Exception as e:
            self.logger.error(
                "Failed to initialize Google Drive: %s", str(e), exc_info=True
            )
            return None

    def get_folder(self, folder_name: str) -> Optional[Dict]:
        """Получение или создание папки на Google Drive"""
        try:
            self.logger.debug("Searching for folder: '%s'", folder_name)
            query = (
                f"title='{folder_name}' and "
                "mimeType='application/vnd.google-apps.folder' and "
                "trashed=false"
            )
            folder_list = self.drive.ListFile({"q": query}).GetList()

            if folder_list:
                self.logger.debug("Found existing folder: '%s'", folder_name)
                return folder_list[0]

            self.logger.info("Creating new folder: '%s'", folder_name)
            folder = self.drive.CreateFile(
                {"title": folder_name, "mimeType": "application/vnd.google-apps.folder"}
            )
            folder.Upload()
            self.logger.info("Successfully created folder: '%s'", folder_name)
            return folder

        except Exception as e:
            self.logger.error(
                "Error accessing folder '%s': %s", folder_name, str(e), exc_info=True
            )
            return None

    def upload_file(self, file_path: str, folder_name: str = "Backups") -> bool:
        """Загрузка файла в указанную папку на Google Drive"""
        if not self.drive:
            self.logger.error("Google Drive not initialized")
            return False

        try:
            file_name = os.path.basename(file_path)
            self.logger.info(
                "Starting upload of '%s' to folder '%s'", file_name, folder_name
            )

            folder = self.get_folder(folder_name)
            if not folder:
                return False

            file = self.drive.CreateFile(
                {"title": file_name, "parents": [{"id": folder["id"]}]}
            )
            file.SetContentFile(file_path)
            file.Upload()

            self.logger.info(
                "Successfully uploaded '%s' to folder '%s'", file_name, folder_name
            )
            return True

        except Exception as e:
            self.logger.error(
                "Failed to upload '%s': %s", file_path, str(e), exc_info=True
            )
            return False

    def download_file(
        self, file_name: str, folder_name: str = "Backups", local_dir: str = "."
    ) -> Optional[str]:
        """Скачивание файла с Google Drive"""
        if not self.drive:
            self.logger.error("Google Drive not initialized")
            return None

        try:
            self.logger.info(
                "Attempting to download '%s' from folder '%s'", file_name, folder_name
            )

            folder = self.get_folder(folder_name)
            if not folder:
                return None

            query = (
                f"title='{file_name}' and "
                f"'{folder['id']}' in parents and "
                "trashed=false"
            )
            file_list = self.drive.ListFile({"q": query}).GetList()

            if not file_list:
                self.logger.warning(
                    "File '%s' not found in folder '%s'", file_name, folder_name
                )
                return None

            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, file_name)

            file = file_list[0]
            file.GetContentFile(local_path)

            self.logger.info(
                "Successfully downloaded '%s' to '%s'", file_name, local_path
            )
            return local_path

        except Exception as e:
            self.logger.error(
                "Failed to download '%s': %s", file_name, str(e), exc_info=True
            )
            return None

    def get_latest_backup(self, folder_name: str = "Backups") -> Optional[str]:
        """Получение последнего файла бэкапа из папки"""
        if not self.drive:
            self.logger.error("Google Drive not initialized")
            return None

        try:
            self.logger.debug("Searching for latest backup in folder '%s'", folder_name)

            folder = self.get_folder(folder_name)
            if not folder:
                return None

            query = f"'{folder['id']}' in parents and trashed=false"
            file_list = self.drive.ListFile({"q": query}).GetList()

            if not file_list:
                self.logger.warning("No backups found in folder '%s'", folder_name)
                return None

            # Фильтруем только .sql.gz файлы и сортируем по дате изменения
            backup_files = [f for f in file_list if f["title"].endswith(".sql.gz")]
            backup_files.sort(key=lambda x: x["modifiedDate"], reverse=True)

            if backup_files:
                latest = backup_files[0]["title"]
                self.logger.info("Found latest backup: '%s'", latest)
                return latest

            self.logger.warning(
                "No valid backup files found in folder '%s'", folder_name
            )
            return None

        except Exception as e:
            self.logger.error("Error searching for backups: %s", str(e), exc_info=True)
            return None
