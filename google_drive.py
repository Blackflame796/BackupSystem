import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from oauth2client.service_account import ServiceAccountCredentials


class GoogleDriveManager:
    def __init__(self, service_account_file: str = "service_account.json"):
        self.logger = logging.getLogger(__name__)
        self.service_account_file = service_account_file
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self.service = self._build_service()

    def _build_service(self):
        try:
            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                self.service_account_file, scopes=self.scopes
            )
            service = build("drive", "v3", credentials=credentials)
            self.logger.info("Google Drive API client initialized.")
            return service
        except Exception as e:
            self.logger.error(
                f"Failed to initialize Drive API client: {e}", exc_info=True
            )
            return None

    def is_initialized(self) -> bool:
        return self.service is not None

    def upload_file(self, file_path: str, folder_id: str) -> bool:
        if not self.is_initialized():
            self.logger.error("Google Drive API client not initialized")
            return False

        try:
            file_name = os.path.basename(file_path)
            file_metadata = {"name": file_name, "parents": [folder_id]}
            media = MediaFileUpload(file_path, resumable=True)

            uploaded_file = (
                self.service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )

            self.logger.info(
                f"Uploaded '{file_name}' to folder ID '{folder_id}' (File ID: {uploaded_file.get('id')})"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to upload '{file_path}': {e}", exc_info=True)
            return False

    def cleanup_old_backups(self, folder_id: str, retention_days: int = 3) -> bool:
        if not self.is_initialized():
            self.logger.error("Google Drive API client not initialized")
            return False

        try:
            cutoff_time = datetime.utcnow() - timedelta(days=retention_days)
            query = (
                f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' "
                f"and trashed = false"
            )

            results = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name, modifiedTime)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            files = results.get("files", [])
            deleted_count = 0

            for file in files:
                modified_time = datetime.strptime(
                    file["modifiedTime"], "%Y-%m-%dT%H:%M:%S.%fZ"
                )
                if modified_time < cutoff_time:
                    self.service.files().delete(fileId=file["id"]).execute()
                    self.logger.info(f"Deleted old file: {file['name']}")
                    deleted_count += 1

            self.logger.info(
                f"Deleted {deleted_count} old backups from folder ID '{folder_id}'"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to clean up backups: {e}", exc_info=True)
            return False
