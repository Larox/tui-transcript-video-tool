from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class NamingMode(Enum):
    SEQUENTIAL = "sequential"
    ORIGINAL = "original"


class JobStatus(Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    UPLOADING = "uploading"
    DONE = "done"
    ERROR = "error"


class OutputMode(Enum):
    GOOGLE_DOCS = "google_docs"
    MARKDOWN = "markdown"


LANGUAGES: dict[str, str] = {
    "es": "Spanish",
    "en": "English",
    "multi": "Multilingual",
    "fr": "French",
    "pt": "Portuguese",
    "de": "German",
    "it": "Italian",
    "hi": "Hindi",
    "ja": "Japanese",
    "ru": "Russian",
    "nl": "Dutch",
}


@dataclass
class AppConfig:
    deepgram_api_key: str = ""
    google_service_account_json: str = ""
    drive_folder_id: str = ""
    naming_mode: NamingMode = NamingMode.SEQUENTIAL
    prefix: str = "Transcripcion"
    markdown_output_dir: str = "./output"

    @property
    def output_mode(self) -> OutputMode:
        if self.google_service_account_json and self.drive_folder_id:
            return OutputMode.GOOGLE_DOCS
        return OutputMode.MARKDOWN


@dataclass
class VideoJob:
    path: Path
    language: str = "es"
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    transcript: str = ""
    doc_id: str = ""
    doc_url: str = ""
    output_path: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        """Serialize for API/JSON. Path becomes string."""
        return {
            "path": str(self.path),
            "language": self.language,
            "status": self.status.value,
            "progress": self.progress,
            "transcript": self.transcript,
            "doc_id": self.doc_id,
            "doc_url": self.doc_url,
            "output_path": self.output_path,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VideoJob:
        """Deserialize from API/JSON. Path can be str or Path."""
        path = data["path"]
        if not isinstance(path, Path):
            path = Path(path)
        return cls(
            path=path,
            language=data.get("language", "es"),
            status=JobStatus(data.get("status", JobStatus.PENDING.value)),
            progress=data.get("progress", 0.0),
            transcript=data.get("transcript", ""),
            doc_id=data.get("doc_id", ""),
            doc_url=data.get("doc_url", ""),
            output_path=data.get("output_path", ""),
            error=data.get("error", ""),
        )


def build_doc_title(config: AppConfig, file_path: Path, seq_number: int) -> str:
    if config.naming_mode == NamingMode.SEQUENTIAL:
        return f"{config.prefix}_{seq_number}"
    return f"{config.prefix}_{file_path.stem}"
