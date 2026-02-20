from __future__ import annotations

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


class GoogleDocsService:
    def __init__(self, service_account_json: str) -> None:
        creds = Credentials.from_service_account_file(
            service_account_json, scopes=SCOPES
        )
        self.drive = build("drive", "v3", credentials=creds)
        self.docs = build("docs", "v1", credentials=creds)

    def create_doc_in_folder(self, title: str, folder_id: str) -> str:
        """Create an empty Google Doc inside *folder_id* and return its ID."""
        metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        }
        doc = self.drive.files().create(body=metadata, fields="id").execute()
        return doc["id"]

    def insert_text(self, doc_id: str, text: str) -> None:
        """Insert *text* at the beginning of the document body."""
        self.docs.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": text,
                        }
                    }
                ]
            },
        ).execute()

    def create_and_fill(self, title: str, folder_id: str, text: str) -> str:
        """Create a doc in *folder_id*, fill it with *text*, return the doc ID."""
        doc_id = self.create_doc_in_folder(title, folder_id)
        self.insert_text(doc_id, text)
        return doc_id
