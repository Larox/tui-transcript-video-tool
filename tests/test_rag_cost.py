"""Cost helpers for embedding spend."""

from __future__ import annotations

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.cost import (
    EmbeddingCostError,
    PRICE_PER_1M_TOKENS,
    SOURCE_TOKEN_CAP,
    count_tokens,
    enforce_source_cap,
    log_embedding_batch,
    daily_total_usd,
)


def test_count_tokens_basic() -> None:
    n = count_tokens(["hello world", "another"])
    assert n > 0
    assert isinstance(n, int)


def test_enforce_source_cap_passes_under_limit() -> None:
    enforce_source_cap(SOURCE_TOKEN_CAP - 1)


def test_enforce_source_cap_raises_over_limit() -> None:
    import pytest
    with pytest.raises(EmbeddingCostError):
        enforce_source_cap(SOURCE_TOKEN_CAP + 1)


def test_log_embedding_batch_writes_row(db: HistoryDB) -> None:
    log_embedding_batch(
        db=db,
        source_type="pdf",
        source_id="42",
        batch_size=10,
        tokens=5000,
        latency_ms=1234,
    )
    row = db._conn.execute(
        "SELECT batch_size, tokens, cost_usd FROM embedding_jobs_log"
    ).fetchone()
    assert row[0] == 10
    assert row[1] == 5000
    expected = 5000 * PRICE_PER_1M_TOKENS / 1_000_000
    assert abs(row[2] - expected) < 1e-9


def test_daily_total_usd_sums_today(db: HistoryDB) -> None:
    log_embedding_batch(db=db, source_type="pdf", source_id="1", batch_size=1, tokens=1_000_000, latency_ms=10)
    log_embedding_batch(db=db, source_type="pdf", source_id="2", batch_size=1, tokens=1_000_000, latency_ms=10)
    total = daily_total_usd(db=db)
    assert abs(total - 2 * PRICE_PER_1M_TOKENS) < 1e-9
