"""Cost guardrails for embedding spend.

Per-source hard cap: 2M tokens (~$0.04 with text-embedding-3-small).
Daily soft warning: WARN log when the day's running total exceeds $1.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import tiktoken

from tui_transcript.services.history import HistoryDB

logger = logging.getLogger(__name__)

PRICE_PER_1M_TOKENS = 0.02            # text-embedding-3-small as of 2026-05
SOURCE_TOKEN_CAP = 2_000_000          # ~$0.04 per single source
DAILY_WARN_USD = 1.00


class EmbeddingCostError(RuntimeError):
    """Raised when a single source exceeds the per-source token cap."""


_ENCODER = None


def _encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        # cl100k_base covers all OpenAI embedding + GPT-4 family models.
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def count_tokens(texts: list[str]) -> int:
    enc = _encoder()
    return sum(len(enc.encode(t)) for t in texts)


def enforce_source_cap(token_count: int) -> None:
    if token_count > SOURCE_TOKEN_CAP:
        raise EmbeddingCostError(
            f"Source exceeds embedding token cap "
            f"({token_count:,} > {SOURCE_TOKEN_CAP:,}). "
            f"Estimated cost ${token_count * PRICE_PER_1M_TOKENS / 1_000_000:.2f}."
        )


def log_embedding_batch(
    *,
    db: HistoryDB,
    source_type: str,
    source_id: str,
    batch_size: int,
    tokens: int,
    latency_ms: int,
) -> None:
    cost = tokens * PRICE_PER_1M_TOKENS / 1_000_000
    db._conn.execute(
        "INSERT INTO embedding_jobs_log "
        "(source_type, source_id, batch_size, tokens, latency_ms, cost_usd, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            source_type,
            source_id,
            batch_size,
            tokens,
            latency_ms,
            cost,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db._conn.commit()
    total = daily_total_usd(db=db)
    if total > DAILY_WARN_USD:
        logger.warning(
            "Embedding spend today is $%.4f (above warn threshold $%.2f).",
            total, DAILY_WARN_USD,
        )


def daily_total_usd(*, db: HistoryDB) -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    row = db._conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM embedding_jobs_log "
        "WHERE substr(created_at, 1, 10) = ?",
        (today,),
    ).fetchone()
    return float(row[0])
