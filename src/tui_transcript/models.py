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


@dataclass
class TranscriptParagraph:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    text: str
    paragraphs: list[TranscriptParagraph] = field(default_factory=list)


@dataclass
class KeyMoment:
    timestamp: str   # "H:MM:SS"
    description: str


COLLECTION_TYPES = ("course", "mentorship", "tutorship", "academic", "other")


@dataclass
class Collection:
    id: int
    name: str
    collection_type: str  # one of COLLECTION_TYPES
    description: str = ""
    item_count: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Tag:
    id: int
    name: str
    color: str = "#6b7280"


@dataclass
class CollectionItem:
    id: int
    source_path: str
    output_title: str
    output_path: str
    language: str
    processed_at: str
    position: int = 0
    tags: list[Tag] = field(default_factory=list)


@dataclass
class SearchResult:
    video_id: int
    output_title: str
    source_path: str
    excerpt: str
    rank: float = 0.0


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
    naming_mode: NamingMode = NamingMode.SEQUENTIAL
    prefix: str = "Transcripcion"
    markdown_output_dir: str = "./output"
    course_name: str = ""
    anthropic_api_key: str = ""


@dataclass
class VideoJob:
    path: Path
    language: str = "es"
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    transcript: str = ""
    output_path: str = ""
    error: str = ""
    key_moments: list[KeyMoment] = field(default_factory=list)
    engine: str = "deepgram"
    whisper_model: str | None = None
    output_title: str | None = None
    video_id: int | None = None

    def to_dict(self) -> dict:
        """Serialize for API/JSON. Path becomes string."""
        return {
            "path": str(self.path),
            "language": self.language,
            "status": self.status.value,
            "progress": self.progress,
            "transcript": self.transcript,
            "output_path": self.output_path,
            "error": self.error,
            "key_moments": [
                {"timestamp": m.timestamp, "description": m.description}
                for m in self.key_moments
            ],
            "engine": self.engine,
            "whisper_model": self.whisper_model,
            "output_title": self.output_title,
            "video_id": self.video_id,
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
            output_path=data.get("output_path", ""),
            error=data.get("error", ""),
            key_moments=[
                KeyMoment(**m) for m in data.get("key_moments", [])
            ],
            engine=data.get("engine", "deepgram"),
            whisper_model=data.get("whisper_model"),
            output_title=data.get("output_title"),
            video_id=data.get("video_id"),
        )


def build_doc_title(config: AppConfig, file_path: Path, seq_number: int) -> str:
    if config.naming_mode == NamingMode.SEQUENTIAL:
        return f"{config.prefix}_{seq_number}"
    return f"{config.prefix}_{file_path.stem}"
