"""Config API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tui_transcript.models import NamingMode
from tui_transcript.services.config_store import EnvConfigStore

from tui_transcript.api.schemas import ConfigResponse, ConfigUpdate

router = APIRouter(prefix="/config", tags=["config"])


def _mask_key(key: str) -> str:
    """Mask API key for response."""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


@router.get("", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    """Get current config. Deepgram key is masked."""
    config = EnvConfigStore().load()
    return ConfigResponse(
        deepgram_api_key=_mask_key(config.deepgram_api_key) if config.deepgram_api_key else "",
        naming_mode=config.naming_mode.value,
        prefix=config.prefix,
        course_name=config.course_name,
        markdown_output_dir=config.markdown_output_dir,
        anthropic_api_key=_mask_key(config.anthropic_api_key) if config.anthropic_api_key else "",
    )


@router.put("")
def put_config(update: ConfigUpdate) -> dict:
    """Update config. Only provided fields are changed."""
    store = EnvConfigStore()
    config = store.load()

    if update.deepgram_api_key is not None:
        config.deepgram_api_key = update.deepgram_api_key
    if update.naming_mode is not None:
        try:
            config.naming_mode = NamingMode(update.naming_mode)
        except ValueError:
            raise HTTPException(400, f"Invalid naming_mode: {update.naming_mode}")
    if update.prefix is not None:
        config.prefix = update.prefix
    if update.course_name is not None:
        config.course_name = update.course_name
    if update.markdown_output_dir is not None:
        config.markdown_output_dir = update.markdown_output_dir
    if update.anthropic_api_key is not None:
        config.anthropic_api_key = update.anthropic_api_key

    if not config.course_name.strip():
        raise HTTPException(
            400,
            "Course name is required",
        )

    store.save(config)
    return {"ok": True}
