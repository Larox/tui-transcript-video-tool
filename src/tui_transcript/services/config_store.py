"""Config storage abstraction. TUI uses .env; web can use DB/session."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from tui_transcript.models import AppConfig, NamingMode

ENV_PATH = Path(".env")


class ConfigStore(Protocol):
    """Interface for loading and saving app config."""

    def load(self) -> AppConfig:
        """Load config. Returns defaults if not found."""
        ...

    def save(self, config: AppConfig) -> None:
        """Persist config."""
        ...


def _load_env() -> dict[str, str]:
    from dotenv import dotenv_values
    if ENV_PATH.exists():
        return {k: (v or "") for k, v in dotenv_values(ENV_PATH).items()}
    return {}


def _save_env(key: str, value: str) -> None:
    from dotenv import set_key
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), key, value)


class EnvConfigStore:
    """Config store that reads/writes .env file."""

    def load(self) -> AppConfig:
        env = _load_env()
        naming = NamingMode.SEQUENTIAL
        if env.get("NAMING_MODE") == "original":
            naming = NamingMode.ORIGINAL
        return AppConfig(
            deepgram_api_key=env.get("DEEPGRAM_API_KEY", ""),
            google_service_account_json=env.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
            drive_folder_id=env.get("DRIVE_FOLDER_ID", ""),
            naming_mode=naming,
            prefix=env.get("PREFIX", "Transcripcion"),
            markdown_output_dir=env.get("MARKDOWN_OUTPUT_DIR", "./output"),
        )

    def save(self, config: AppConfig) -> None:
        _save_env("DEEPGRAM_API_KEY", config.deepgram_api_key)
        _save_env("GOOGLE_SERVICE_ACCOUNT_JSON", config.google_service_account_json)
        _save_env("DRIVE_FOLDER_ID", config.drive_folder_id)
        _save_env("NAMING_MODE", config.naming_mode.value)
        _save_env("PREFIX", config.prefix)
        _save_env("MARKDOWN_OUTPUT_DIR", config.markdown_output_dir)
