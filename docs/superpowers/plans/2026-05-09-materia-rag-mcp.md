# Materia RAG + MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-materia retrieval-augmented generation. Users upload PDFs into a materia; the system extracts, chunks, embeds, and stores them in `sqlite-vec`. Existing class transcripts are silently mirrored into the same index. A stdio MCP server exposes two read-only tools (`list_materias`, `search_knowledge`) so external host LLMs (Claude Desktop, Cursor, Claude Code) can search by materia and topic.

**Architecture:** Three new subsystems with strict boundaries: ingestion (`extract → chunk → embed → store`), retrieval (`embed query → vector search → filter`), and surfaces (FastAPI routes + stdio MCP). The web app and the MCP server call the same `services/rag/retrieve.search()` function — there is no MCP-specific search path. All vendor-specific code (sqlite-vec, OpenAI, pypdf) is isolated behind Protocols so day-2 swaps (Chroma, BGE-M3, .ipynb extractor) are one new file each.

**Tech Stack:** Python 3.12, FastAPI, sqlite-vec (1536-dim cosine vectors over the existing `~/.tui_transcript/history.db`), OpenAI `text-embedding-3-small`, pypdf, the official `mcp` Python SDK (stdio transport). React 19, TypeScript, Vite, TanStack Query, shadcn/ui.

**Spec:** [docs/superpowers/specs/2026-05-09-materia-rag-mcp-design.md](../specs/2026-05-09-materia-rag-mcp-design.md)

**Branch:** `feat/materia-rag-mcp` (already created from `main`; the spec is committed there)

---

## File Structure

**New files:**
- `src/tui_transcript/services/rag/__init__.py` — package marker
- `src/tui_transcript/services/rag/embedder.py` — `Embedder` Protocol, `OpenAIEmbedder`, `FakeEmbedder`
- `src/tui_transcript/services/rag/store.py` — `VectorStore` Protocol, `Chunk`, `SqliteVecStore`, `FakeVectorStore`
- `src/tui_transcript/services/rag/chunker.py` — `ExtractedSection`, `Chunk`, `chunk_sections()`
- `src/tui_transcript/services/rag/extractors/__init__.py` — extractor registry
- `src/tui_transcript/services/rag/extractors/pdf.py` — `extract_pdf(path) -> list[ExtractedSection]`
- `src/tui_transcript/services/rag/extractors/transcript.py` — `extract_transcript(video_id) -> list[ExtractedSection]`
- `src/tui_transcript/services/rag/cost.py` — token counting + `embedding_jobs_log` writer + 2M cap + daily warning
- `src/tui_transcript/services/rag/ingest.py` — `ingest_file(file_id)`, `reindex_transcript(video_id, collection_id)`
- `src/tui_transcript/services/rag/background.py` — asyncio queue worker + lifespan startup/shutdown
- `src/tui_transcript/services/rag/retrieve.py` — `Hit`, `search()`
- `src/tui_transcript/api/routes/materia_files.py` — POST/GET/DELETE `/materias/{cid}/files`, POST `/materias/{cid}/reindex`
- `src/tui_transcript/api/routes/rag.py` — POST `/rag/search`
- `src/tui_transcript_mcp/__init__.py` — package marker
- `src/tui_transcript_mcp/tools.py` — pure functions: `list_materias()`, `search_knowledge()`
- `src/tui_transcript_mcp/server.py` — stdio entry point, `main()` registered as console script
- `tests/fixtures/two_pages.pdf` — checked-in tiny PDF for extractor tests
- `tests/test_rag_chunker.py`
- `tests/test_rag_extractor_pdf.py`
- `tests/test_rag_extractor_transcript.py`
- `tests/test_rag_embedder.py`
- `tests/test_rag_store_sqlite_vec.py`
- `tests/test_rag_cost.py`
- `tests/test_rag_ingest.py`
- `tests/test_rag_retrieve.py`
- `tests/test_rag_api.py`
- `tests/test_rag_background.py`
- `tests/test_mcp_tools.py`
- `tests/test_mcp_smoke.py`
- `frontend/src/api/rag.ts` — typed client for materia_files + /rag/search
- `frontend/src/components/MateriaFiles.tsx` — Archivos tab content

**Modified:**
- `pyproject.toml` — add `sqlite-vec`, `pypdf`, `openai`, `mcp`, `tiktoken` (runtime); add `reportlab` (dev, for fixture PDF generation); new console_script `tui-transcript-mcp`
- `src/tui_transcript/services/history.py` — add 4 RAG tables + `embedding_jobs_log` to `_migrate()`; load sqlite-vec extension
- `src/tui_transcript/api/main.py` — register `materia_files` + `rag` routers; add lifespan that starts the background worker
- `src/tui_transcript/api/routes/transcription.py` — after pipeline succeeds, enqueue `reindex_transcript` for every collection containing the video
- `src/tui_transcript/api/routes/collections.py` — after `add_item`, enqueue `reindex_transcript` for the new collection membership
- `frontend/src/pages/CourseDetail.tsx` — add an "Archivos" tab that mounts `MateriaFiles`
- `tests/conftest.py` — extend the `db` fixture so sqlite-vec extension loads in tests

**Out of plan (per spec):** notebook/code extractors, reranker, hybrid search, "Pregunta" chat UI, smart materia auto-routing, HTTP MCP, BGE-M3, multi-user, auto re-embed-on-model-change.

---

## Task 1: Add backend dependencies + verify sqlite-vec loads

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add deps to `pyproject.toml`**

Edit the `dependencies` array to include the five new runtime packages, add `reportlab` to the dev group (used only to generate the test fixture PDF), and register the MCP console script:

```toml
[project]
name = "tui-transcript"
version = "0.1.0"
description = "TUI app to transcribe video files via Deepgram and export to Markdown"
requires-python = ">=3.12"
dependencies = [
    "textual",
    "deepgram-sdk",
    "python-dotenv",
    "fastapi",
    "uvicorn[standard]",
    "python-multipart",
    "anthropic>=0.25",
    "faster-whisper>=1.0",
    "huggingface-hub>=0.24",
    "pydantic-ai[anthropic]>=1.90.0",
    "sqlite-vec>=0.1.6",
    "pypdf>=5.0",
    "openai>=1.50",
    "mcp>=1.0",
    "tiktoken>=0.7",
]

[project.scripts]
tui-transcript = "tui_transcript.app:main"
tui-transcript-api = "tui_transcript.api.main:run"
tui-transcript-mcp = "tui_transcript_mcp.server:main"

[dependency-groups]
dev = [
    "httpx>=0.28.1",
    "pytest>=9.0.3",
    "pytest-asyncio>=0.23",
    "reportlab>=4.0",
]
```

- [ ] **Step 2: Sync deps**

Run: `uv sync`
Expected: prints "Resolved … packages" then "Installed … packages" listing the five new packages.

- [ ] **Step 3: Verify sqlite-vec loads against an in-memory DB**

Run:
```bash
uv run python -c "
import sqlite3, sqlite_vec
conn = sqlite3.connect(':memory:')
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.execute('CREATE VIRTUAL TABLE v USING vec0(embedding float[3])')
conn.execute('INSERT INTO v(rowid, embedding) VALUES (1, ?)', (b'\\x00\\x00\\x80\\x3f\\x00\\x00\\x00\\x40\\x00\\x00\\x40\\x40',))
print('ok:', conn.execute('SELECT COUNT(*) FROM v').fetchone()[0])
"
```
Expected: prints `ok: 1`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add sqlite-vec, pypdf, openai, mcp, tiktoken for RAG layer"
```

---

## Task 2: RAG schema in HistoryDB

**Files:**
- Modify: `src/tui_transcript/services/history.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_rag_schema.py`

- [ ] **Step 1: Load sqlite-vec extension in HistoryDB**

In `src/tui_transcript/services/history.py`, find the `__init__` method (around line 211). Add the extension load before `executescript(_SCHEMA)`:

```python
def __init__(self, db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(str(db_path))
    self._conn.execute("PRAGMA journal_mode=WAL")
    self._conn.execute("PRAGMA foreign_keys=ON")
    # Load sqlite-vec extension for RAG vector search.
    import sqlite_vec
    self._conn.enable_load_extension(True)
    sqlite_vec.load(self._conn)
    self._conn.enable_load_extension(False)
    self._conn.executescript(_SCHEMA)
    self._conn.executescript(_FTS_SCHEMA)
    self._migrate()
```

- [ ] **Step 2: Add a failing schema test**

Create `tests/test_rag_schema.py`:

```python
"""Verify RAG schema is created on HistoryDB init."""

from __future__ import annotations

from pathlib import Path

from tui_transcript.services.history import HistoryDB


def test_rag_tables_exist(tmp_path: Path) -> None:
    db = HistoryDB(tmp_path / "h.db")
    try:
        rows = {
            r[0]
            for r in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')"
            )
        }
        # Note: virtual tables show up with type='table' too in sqlite_master.
        for name in ("materia_files", "rag_chunks", "rag_chunk_meta", "embedding_jobs_log"):
            assert name in rows, f"missing table: {name}"
    finally:
        db.close()


def test_rag_chunks_dimension_is_1536(tmp_path: Path) -> None:
    db = HistoryDB(tmp_path / "h.db")
    try:
        # vec0 stores raw float32. Round-trip a 1536-dim vector to confirm the dim.
        import struct
        vec = struct.pack(f"{1536}f", *([0.1] * 1536))
        db._conn.execute("INSERT INTO rag_chunks(rowid, embedding) VALUES (1, ?)", (vec,))
        row = db._conn.execute("SELECT rowid FROM rag_chunks WHERE rowid = 1").fetchone()
        assert row == (1,)
    finally:
        db.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_rag_schema.py -v`
Expected: FAIL with "missing table: materia_files".

- [ ] **Step 4: Add the schema to `_migrate()`**

Open `src/tui_transcript/services/history.py`, find `_migrate()` (around line 224). At the **end** of the method body (after the existing migrations), add the four new statements. They must be idempotent (`CREATE ... IF NOT EXISTS`):

```python
        # --- RAG schema (idempotent) ---
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS materia_files (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id   INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                filename        TEXT NOT NULL,
                storage_path    TEXT NOT NULL,
                mime_type       TEXT NOT NULL,
                size_bytes      INTEGER NOT NULL,
                status          TEXT NOT NULL,
                error_message   TEXT,
                uploaded_at     TEXT NOT NULL,
                indexed_at      TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks USING vec0(
                embedding float[1536]
            );

            CREATE TABLE IF NOT EXISTS rag_chunk_meta (
                rowid           INTEGER PRIMARY KEY,
                collection_id   INTEGER NOT NULL,
                source_type     TEXT NOT NULL,
                source_id       TEXT NOT NULL,
                chunk_index     INTEGER NOT NULL,
                text            TEXT NOT NULL,
                page_number     INTEGER,
                embedding_model TEXT NOT NULL,
                UNIQUE(source_type, source_id, chunk_index, embedding_model)
            );
            CREATE INDEX IF NOT EXISTS idx_rag_meta_collection
                ON rag_chunk_meta(collection_id);
            CREATE INDEX IF NOT EXISTS idx_rag_meta_source
                ON rag_chunk_meta(source_type, source_id);

            CREATE TABLE IF NOT EXISTS embedding_jobs_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_id   TEXT NOT NULL,
                batch_size  INTEGER NOT NULL,
                tokens      INTEGER NOT NULL,
                latency_ms  INTEGER NOT NULL,
                cost_usd    REAL NOT NULL,
                created_at  TEXT NOT NULL
            );
        """)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_rag_schema.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Confirm no other tests break**

Run: `uv run pytest -v`
Expected: every existing test still PASSES (the new tables are additive and idempotent).

- [ ] **Step 7: Commit**

```bash
git add src/tui_transcript/services/history.py tests/test_rag_schema.py
git commit -m "feat(rag): add materia_files, rag_chunks, rag_chunk_meta, embedding_jobs_log"
```

---

## Task 3: Embedder Protocol + FakeEmbedder + OpenAIEmbedder

**Files:**
- Create: `src/tui_transcript/services/rag/__init__.py`
- Create: `src/tui_transcript/services/rag/embedder.py`
- Create: `tests/test_rag_embedder.py`

- [ ] **Step 1: Create the package marker**

Create `src/tui_transcript/services/rag/__init__.py` containing exactly:

```python
"""RAG layer: extraction, chunking, embedding, storage, retrieval."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_rag_embedder.py`:

```python
"""Embedder Protocol implementations: FakeEmbedder + OpenAIEmbedder."""

from __future__ import annotations

import os

import pytest

from tui_transcript.services.rag.embedder import FakeEmbedder, OpenAIEmbedder


def test_fake_embedder_returns_correct_dim() -> None:
    e = FakeEmbedder(dim=1536)
    vecs = e.embed(["hello", "world"])
    assert len(vecs) == 2
    assert all(len(v) == 1536 for v in vecs)


def test_fake_embedder_is_deterministic() -> None:
    e = FakeEmbedder(dim=1536)
    a = e.embed(["redes neuronales"])[0]
    b = e.embed(["redes neuronales"])[0]
    assert a == b


def test_fake_embedder_different_inputs_different_vectors() -> None:
    e = FakeEmbedder(dim=1536)
    a = e.embed(["redes neuronales"])[0]
    b = e.embed(["arquitectura de software"])[0]
    assert a != b


def test_fake_embedder_model_name() -> None:
    assert FakeEmbedder().model == "fake-embedder-v1"


def test_openai_embedder_model_name() -> None:
    e = OpenAIEmbedder()
    assert e.model == "text-embedding-3-small"


@pytest.mark.openai
def test_openai_embedder_real_call() -> None:
    """Opt-in: hits the real OpenAI API. Skipped unless `pytest -m openai`."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    e = OpenAIEmbedder()
    vecs = e.embed(["hello world"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 1536
    assert all(isinstance(x, float) for x in vecs[0])
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_embedder.py -v`
Expected: ImportError — `tui_transcript.services.rag.embedder` does not exist.

- [ ] **Step 4: Implement `embedder.py`**

Create `src/tui_transcript/services/rag/embedder.py`:

```python
"""Embedding providers behind a single Protocol.

Migration boundary: this is the only file allowed to call OpenAI's embeddings
endpoint or any other vendor SDK. Adding a local BGE-M3 backend later means
adding one new class here that implements `Embedder`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import struct
from typing import Protocol

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Anything that turns text into fixed-dimension float vectors."""

    model: str  # canonical name written into rag_chunk_meta.embedding_model
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text. Order preserved."""
        ...


class FakeEmbedder:
    """Deterministic, network-free embedder for tests.

    Hashes each text and stretches the digest into `dim` floats. Same text →
    same vector; different texts → different vectors. Not semantically
    meaningful — only useful for verifying ingest/retrieve plumbing.
    """

    model: str = "fake-embedder-v1"

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            digest = hashlib.sha256(t.encode("utf-8")).digest()
            # Repeat the 32-byte digest until we have dim*4 bytes of float32 source.
            need = self.dim * 4
            buf = (digest * ((need // len(digest)) + 1))[:need]
            floats = list(struct.unpack(f"{self.dim}f", buf))
            # Normalize to unit length so cosine math behaves.
            norm = sum(x * x for x in floats) ** 0.5 or 1.0
            out.append([x / norm for x in floats])
        return out


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small backend."""

    model: str = "text-embedding-3-small"
    dim: int = 1536

    def __init__(self, api_key: str | None = None) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]
```

- [ ] **Step 5: Register the `openai` marker for opt-in tests**

Open `pyproject.toml`. Find `[tool.pytest.ini_options]`. Replace with:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "openai: integration test that hits the live OpenAI API; opt-in via -m openai",
]
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_embedder.py -v`
Expected: 5 PASS, 1 SKIPPED (the `@pytest.mark.openai` test — skipped unless invoked with `-m openai`).

- [ ] **Step 7: Commit**

```bash
git add src/tui_transcript/services/rag/__init__.py src/tui_transcript/services/rag/embedder.py tests/test_rag_embedder.py pyproject.toml
git commit -m "feat(rag): Embedder Protocol with FakeEmbedder and OpenAIEmbedder"
```

---

## Task 4: VectorStore Protocol + FakeVectorStore + SqliteVecStore

**Files:**
- Create: `src/tui_transcript/services/rag/store.py`
- Create: `tests/test_rag_store_sqlite_vec.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_store_sqlite_vec.py`:

```python
"""VectorStore Protocol implementations: FakeVectorStore + SqliteVecStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.store import (
    Chunk,
    FakeVectorStore,
    SqliteVecStore,
)


@pytest.fixture()
def store(tmp_path: Path):
    db = HistoryDB(tmp_path / "h.db")
    # Manually insert a collection so FK doesn't bite.
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (1, 'M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    s = SqliteVecStore(db=db)
    yield s
    db.close()


def _chunk(idx: int, text: str, vec: list[float]) -> Chunk:
    return Chunk(
        collection_id=1,
        source_type="pdf",
        source_id="42",
        chunk_index=idx,
        text=text,
        page_number=1,
        embedding_model="fake-embedder-v1",
        embedding=vec,
    )


def test_upsert_and_query(store: SqliteVecStore) -> None:
    e = FakeEmbedder()
    chunks = [
        _chunk(i, t, e.embed([t])[0])
        for i, t in enumerate(["redes neuronales", "matrices", "calculo"])
    ]
    store.upsert(chunks)

    qvec = e.embed(["redes neuronales"])[0]
    hits = store.query(
        qvec,
        collection_id=1,
        embedding_model="fake-embedder-v1",
        k=3,
    )
    assert len(hits) == 3
    # The exact-match query should rank first.
    assert hits[0].text == "redes neuronales"
    assert hits[0].score > hits[1].score


def test_upsert_is_idempotent(store: SqliteVecStore) -> None:
    e = FakeEmbedder()
    c = _chunk(0, "x", e.embed(["x"])[0])
    store.upsert([c])
    store.upsert([c])  # second call must not raise nor duplicate
    rows = store._db._conn.execute(
        "SELECT COUNT(*) FROM rag_chunk_meta WHERE source_type='pdf' AND source_id='42'"
    ).fetchone()[0]
    assert rows == 1


def test_delete_removes_meta_and_vector(store: SqliteVecStore) -> None:
    e = FakeEmbedder()
    chunks = [_chunk(i, f"t{i}", e.embed([f"t{i}"])[0]) for i in range(3)]
    store.upsert(chunks)
    store.delete(source_type="pdf", source_id="42", embedding_model="fake-embedder-v1")
    n_meta = store._db._conn.execute(
        "SELECT COUNT(*) FROM rag_chunk_meta WHERE source_id='42'"
    ).fetchone()[0]
    n_vec = store._db._conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
    assert n_meta == 0
    assert n_vec == 0


def test_query_filters_by_collection(store: SqliteVecStore) -> None:
    # Add a second collection.
    store._db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (2, 'Other', 'course', '', '2026-05-09', '2026-05-09')"
    )
    store._db._conn.commit()
    e = FakeEmbedder()
    a = _chunk(0, "alpha", e.embed(["alpha"])[0])
    b = Chunk(
        collection_id=2,
        source_type="pdf",
        source_id="99",
        chunk_index=0,
        text="alpha",
        page_number=1,
        embedding_model="fake-embedder-v1",
        embedding=e.embed(["alpha"])[0],
    )
    store.upsert([a, b])
    hits = store.query(
        e.embed(["alpha"])[0],
        collection_id=1,
        embedding_model="fake-embedder-v1",
        k=10,
    )
    assert all(h.collection_id == 1 for h in hits)


def test_fake_vector_store_roundtrip() -> None:
    s = FakeVectorStore()
    e = FakeEmbedder()
    c = _chunk(0, "t", e.embed(["t"])[0])
    s.upsert([c])
    hits = s.query(e.embed(["t"])[0], collection_id=1, embedding_model="fake-embedder-v1", k=1)
    assert hits[0].text == "t"
    s.delete(source_type="pdf", source_id="42", embedding_model="fake-embedder-v1")
    assert s.query(e.embed(["t"])[0], collection_id=1, embedding_model="fake-embedder-v1", k=1) == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_store_sqlite_vec.py -v`
Expected: ImportError — `tui_transcript.services.rag.store` does not exist.

- [ ] **Step 3: Implement `store.py`**

Create `src/tui_transcript/services/rag/store.py`:

```python
"""VectorStore Protocol + SqliteVecStore + FakeVectorStore.

Migration boundary: this is the only file that knows `sqlite-vec` exists.
Swapping to Chroma / pgvector / LanceDB later means adding one new class here
that implements `VectorStore` and a one-time backfill script.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Protocol

from tui_transcript.services.history import HistoryDB


@dataclass
class Chunk:
    """One chunk ready to write to the index."""

    collection_id: int
    source_type: str            # 'pdf' | 'transcript'
    source_id: str
    chunk_index: int
    text: str
    page_number: int | None
    embedding_model: str
    embedding: list[float]


@dataclass
class StoreHit:
    """One nearest-neighbour result. Distinct from retrieve.Hit (retrieve adds JOINs)."""

    rowid: int
    score: float                # cosine similarity in [-1, 1]; usually [0, 1]
    collection_id: int
    source_type: str
    source_id: str
    chunk_index: int
    text: str
    page_number: int | None


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def query(
        self,
        embedding: list[float],
        *,
        collection_id: int | None,
        embedding_model: str,
        k: int = 8,
    ) -> list[StoreHit]: ...
    def delete(
        self,
        *,
        source_type: str,
        source_id: str,
        embedding_model: str,
    ) -> None: ...


def _to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class SqliteVecStore:
    """Backs the `rag_chunks` (vec0 virtual table) + `rag_chunk_meta` pair."""

    def __init__(self, db: HistoryDB | None = None) -> None:
        self._db = db or HistoryDB()

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        conn = self._db._conn
        for c in chunks:
            # Delete-then-insert keeps it idempotent under the UNIQUE constraint.
            row = conn.execute(
                "SELECT rowid FROM rag_chunk_meta WHERE source_type=? AND source_id=? "
                "AND chunk_index=? AND embedding_model=?",
                (c.source_type, c.source_id, c.chunk_index, c.embedding_model),
            ).fetchone()
            if row is not None:
                old_rowid = row[0]
                conn.execute("DELETE FROM rag_chunks WHERE rowid = ?", (old_rowid,))
                conn.execute("DELETE FROM rag_chunk_meta WHERE rowid = ?", (old_rowid,))

            cur = conn.execute(
                "INSERT INTO rag_chunk_meta "
                "(collection_id, source_type, source_id, chunk_index, text, page_number, embedding_model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    c.collection_id,
                    c.source_type,
                    c.source_id,
                    c.chunk_index,
                    c.text,
                    c.page_number,
                    c.embedding_model,
                ),
            )
            new_rowid = cur.lastrowid
            conn.execute(
                "INSERT INTO rag_chunks(rowid, embedding) VALUES (?, ?)",
                (new_rowid, _to_blob(c.embedding)),
            )
        conn.commit()

    def query(
        self,
        embedding: list[float],
        *,
        collection_id: int | None,
        embedding_model: str,
        k: int = 8,
    ) -> list[StoreHit]:
        conn = self._db._conn
        # vec0 returns `distance` = L2 by default; for normalized vectors L2 and
        # cosine are monotonically related. We approximate cosine similarity as
        # 1 - distance**2 / 2 (correct for unit vectors).
        sql = (
            "SELECT v.rowid, v.distance, m.collection_id, m.source_type, m.source_id, "
            "m.chunk_index, m.text, m.page_number "
            "FROM rag_chunks v "
            "JOIN rag_chunk_meta m ON m.rowid = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ? AND m.embedding_model = ?"
        )
        params: list = [_to_blob(embedding), k, embedding_model]
        if collection_id is not None:
            sql += " AND m.collection_id = ?"
            params.append(collection_id)
        rows = conn.execute(sql, params).fetchall()
        hits: list[StoreHit] = []
        for r in rows:
            distance = float(r[1])
            score = max(0.0, 1.0 - (distance * distance) / 2.0)
            hits.append(
                StoreHit(
                    rowid=r[0],
                    score=score,
                    collection_id=r[2],
                    source_type=r[3],
                    source_id=r[4],
                    chunk_index=r[5],
                    text=r[6],
                    page_number=r[7],
                )
            )
        return hits

    def delete(
        self,
        *,
        source_type: str,
        source_id: str,
        embedding_model: str,
    ) -> None:
        conn = self._db._conn
        rows = conn.execute(
            "SELECT rowid FROM rag_chunk_meta "
            "WHERE source_type=? AND source_id=? AND embedding_model=?",
            (source_type, source_id, embedding_model),
        ).fetchall()
        for (rowid,) in rows:
            conn.execute("DELETE FROM rag_chunks WHERE rowid = ?", (rowid,))
            conn.execute("DELETE FROM rag_chunk_meta WHERE rowid = ?", (rowid,))
        conn.commit()


class FakeVectorStore:
    """In-memory store for tests. Brute-force cosine, no SQLite involvement."""

    def __init__(self) -> None:
        self._items: list[Chunk] = []

    def upsert(self, chunks: list[Chunk]) -> None:
        for c in chunks:
            self._items = [
                x for x in self._items
                if not (
                    x.source_type == c.source_type
                    and x.source_id == c.source_id
                    and x.chunk_index == c.chunk_index
                    and x.embedding_model == c.embedding_model
                )
            ]
            self._items.append(c)

    def query(
        self,
        embedding: list[float],
        *,
        collection_id: int | None,
        embedding_model: str,
        k: int = 8,
    ) -> list[StoreHit]:
        candidates = [
            c for c in self._items
            if c.embedding_model == embedding_model
            and (collection_id is None or c.collection_id == collection_id)
        ]
        scored: list[tuple[float, Chunk]] = []
        for c in candidates:
            dot = sum(a * b for a, b in zip(embedding, c.embedding))
            scored.append((dot, c))
        scored.sort(key=lambda p: p[0], reverse=True)
        out: list[StoreHit] = []
        for rowid, (score, c) in enumerate(scored[:k]):
            out.append(
                StoreHit(
                    rowid=rowid,
                    score=score,
                    collection_id=c.collection_id,
                    source_type=c.source_type,
                    source_id=c.source_id,
                    chunk_index=c.chunk_index,
                    text=c.text,
                    page_number=c.page_number,
                )
            )
        return out

    def delete(
        self,
        *,
        source_type: str,
        source_id: str,
        embedding_model: str,
    ) -> None:
        self._items = [
            c for c in self._items
            if not (
                c.source_type == source_type
                and c.source_id == source_id
                and c.embedding_model == embedding_model
            )
        ]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_store_sqlite_vec.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/rag/store.py tests/test_rag_store_sqlite_vec.py
git commit -m "feat(rag): VectorStore Protocol with SqliteVecStore and FakeVectorStore"
```

---

## Task 5: Chunker

**Files:**
- Create: `src/tui_transcript/services/rag/chunker.py`
- Create: `tests/test_rag_chunker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_chunker.py`:

```python
"""Recursive paragraph-aware chunker."""

from __future__ import annotations

from tui_transcript.services.rag.chunker import (
    ExtractedSection,
    chunk_sections,
)


def test_short_section_yields_one_chunk() -> None:
    sec = ExtractedSection(text="Hola mundo.", page_number=1)
    chunks = chunk_sections([sec], target_chars=800, overlap_chars=100)
    assert len(chunks) == 1
    assert chunks[0].text == "Hola mundo."
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1


def test_long_section_splits_with_overlap() -> None:
    para = "Esto es una oración. " * 100  # ~2000 chars
    sec = ExtractedSection(text=para, page_number=3)
    chunks = chunk_sections([sec], target_chars=800, overlap_chars=100)
    assert len(chunks) >= 3
    for i, c in enumerate(chunks):
        assert len(c.text) <= 900  # target + slack for boundary alignment
        assert c.chunk_index == i
        assert c.page_number == 3
    # Adjacent chunks share at least some characters thanks to overlap.
    assert chunks[0].text[-50:] in chunks[1].text or chunks[1].text[:50] in chunks[0].text


def test_multiple_sections_produce_continuous_indices() -> None:
    secs = [
        ExtractedSection(text="A" * 1500, page_number=1),
        ExtractedSection(text="B" * 1500, page_number=2),
    ]
    chunks = chunk_sections(secs, target_chars=800, overlap_chars=100)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))
    # Page numbers preserved.
    page_1 = [c for c in chunks if c.page_number == 1]
    page_2 = [c for c in chunks if c.page_number == 2]
    assert page_1 and page_2


def test_paragraph_boundary_preserved_when_possible() -> None:
    text = ("First paragraph " * 30) + "\n\n" + ("Second paragraph " * 30)
    sec = ExtractedSection(text=text, page_number=1)
    chunks = chunk_sections([sec], target_chars=600, overlap_chars=80)
    # The split should land on the paragraph boundary.
    assert any(c.text.endswith("First paragraph ".strip()) or c.text.rstrip().endswith("paragraph") for c in chunks)


def test_empty_input() -> None:
    assert chunk_sections([], target_chars=800, overlap_chars=100) == []
    assert chunk_sections([ExtractedSection(text="", page_number=1)], target_chars=800, overlap_chars=100) == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_chunker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `chunker.py`**

Create `src/tui_transcript/services/rag/chunker.py`:

```python
"""Paragraph-aware recursive chunker.

Splits each ExtractedSection into chunks of approximately `target_chars`,
preferring paragraph boundaries (`\n\n`), then sentence boundaries (`. `),
then character boundaries. Adjacent chunks overlap by `overlap_chars`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractedSection:
    """One unit of upstream content (e.g. one PDF page, one transcript paragraph)."""

    text: str
    page_number: int | None = None


@dataclass
class ChunkOut:
    """One produced chunk, before embedding."""

    text: str
    chunk_index: int
    page_number: int | None


def chunk_sections(
    sections: list[ExtractedSection],
    *,
    target_chars: int = 800,
    overlap_chars: int = 100,
) -> list[ChunkOut]:
    """Chunk a list of sections, preserving page provenance."""
    out: list[ChunkOut] = []
    idx = 0
    for sec in sections:
        text = (sec.text or "").strip()
        if not text:
            continue
        for piece in _split_one(text, target_chars=target_chars, overlap_chars=overlap_chars):
            out.append(ChunkOut(text=piece, chunk_index=idx, page_number=sec.page_number))
            idx += 1
    return out


def _split_one(text: str, *, target_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= target_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + target_chars, n)
        if end < n:
            # Prefer paragraph break in the second half of the window.
            window_start = start + target_chars // 2
            cut = text.rfind("\n\n", window_start, end)
            if cut == -1:
                cut = text.rfind(". ", window_start, end)
                if cut != -1:
                    cut += 2  # include the ". "
            if cut != -1 and cut > start:
                end = cut
        pieces.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)
    return [p for p in pieces if p]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_chunker.py -v`
Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/rag/chunker.py tests/test_rag_chunker.py
git commit -m "feat(rag): paragraph-aware chunker"
```

---

## Task 6: PDF extractor

**Files:**
- Create: `tests/fixtures/two_pages.pdf` (binary)
- Create: `src/tui_transcript/services/rag/extractors/__init__.py`
- Create: `src/tui_transcript/services/rag/extractors/pdf.py`
- Create: `tests/test_rag_extractor_pdf.py`

- [ ] **Step 1: Generate the fixture PDF with reportlab**

Run this once to produce a 2-page PDF whose pages each contain real, extractable text:

```bash
mkdir -p tests/fixtures
uv run python -c "
from reportlab.pdfgen.canvas import Canvas
c = Canvas('tests/fixtures/two_pages.pdf', pagesize=(612, 792))
c.setFont('Helvetica', 18)
c.drawString(72, 720, 'Pagina uno: redes neuronales.')
c.showPage()
c.setFont('Helvetica', 18)
c.drawString(72, 720, 'Pagina dos: matrices y calculo.')
c.showPage()
c.save()
print('ok')
"
```

Expected: prints `ok` and creates `tests/fixtures/two_pages.pdf` (~1–2 KB).

- [ ] **Step 2: Verify extraction works manually**

Run:
```bash
uv run python -c "
from pypdf import PdfReader
r = PdfReader('tests/fixtures/two_pages.pdf')
for i, p in enumerate(r.pages):
    print(i, repr(p.extract_text()))
"
```
Expected: prints two lines, one per page, each containing the inserted text.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_rag_extractor_pdf.py`:

```python
"""PDF extractor."""

from __future__ import annotations

from pathlib import Path

from tui_transcript.services.rag.extractors.pdf import extract_pdf


FIXTURE = Path(__file__).parent / "fixtures" / "two_pages.pdf"


def test_extracts_two_pages() -> None:
    sections = extract_pdf(FIXTURE)
    assert len(sections) == 2
    assert sections[0].page_number == 1
    assert sections[1].page_number == 2
    assert "redes neuronales" in sections[0].text.lower()
    assert "matrices" in sections[1].text.lower()


def test_skips_blank_pages() -> None:
    # extract_pdf must drop pages whose extracted text is empty/whitespace.
    # Re-test against the fixture (no blanks): just confirm no empty sections.
    sections = extract_pdf(FIXTURE)
    assert all(s.text.strip() for s in sections)
```

- [ ] **Step 4: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_extractor_pdf.py -v`
Expected: ImportError.

- [ ] **Step 5: Implement extractors registry + PDF extractor**

Create `src/tui_transcript/services/rag/extractors/__init__.py`:

```python
"""Extractor registry — maps mime types to extraction functions.

Adding a new format (e.g. .ipynb) is one new module + one entry in this dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from tui_transcript.services.rag.chunker import ExtractedSection
from tui_transcript.services.rag.extractors.pdf import extract_pdf

Extractor = Callable[[Path], list[ExtractedSection]]

REGISTRY: dict[str, Extractor] = {
    "application/pdf": extract_pdf,
}


def get_extractor(mime_type: str) -> Extractor | None:
    return REGISTRY.get(mime_type)
```

Create `src/tui_transcript/services/rag/extractors/pdf.py`:

```python
"""PDF text extraction via pypdf."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from tui_transcript.services.rag.chunker import ExtractedSection


def extract_pdf(path: Path) -> list[ExtractedSection]:
    reader = PdfReader(str(path))
    out: list[ExtractedSection] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        out.append(ExtractedSection(text=text, page_number=i))
    return out
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_extractor_pdf.py -v`
Expected: both PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/two_pages.pdf src/tui_transcript/services/rag/extractors/ tests/test_rag_extractor_pdf.py
git commit -m "feat(rag): pypdf-based extractor + 2-page test fixture"
```

---

## Task 7: Transcript extractor

**Files:**
- Create: `src/tui_transcript/services/rag/extractors/transcript.py`
- Create: `tests/test_rag_extractor_transcript.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_extractor_transcript.py`:

```python
"""Transcript extractor reads from history.transcript_search."""

from __future__ import annotations

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.extractors.transcript import extract_transcript


def test_extracts_paragraphs(db: HistoryDB) -> None:
    # Seed a video + transcript.
    db.record(
        source_path="/v/lec.mp4",
        prefix="Test",
        naming_mode="sequential",
        sequential_number=1,
        output_title="Lec",
        output_mode="markdown",
        output_path="/o/Lec.md",
        language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/lec.mp4", "Primer parrafo.\n\nSegundo parrafo.\n\nTercero.")
    sections = extract_transcript(vid, db=db)
    assert len(sections) == 3
    assert sections[0].text == "Primer parrafo."
    assert sections[1].text == "Segundo parrafo."
    assert sections[2].text == "Tercero."
    assert all(s.page_number is None for s in sections)


def test_returns_empty_when_no_transcript(db: HistoryDB) -> None:
    assert extract_transcript(999, db=db) == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_extractor_transcript.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the extractor**

Create `src/tui_transcript/services/rag/extractors/transcript.py`:

```python
"""Pull a video's transcript text from history.transcript_search and split into paragraphs.

Transcripts arrive without page boundaries; we split on blank lines (the
standard paragraph separator emitted by both Deepgram and Whisper exports).
"""

from __future__ import annotations

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.chunker import ExtractedSection


def extract_transcript(video_id: int, *, db: HistoryDB | None = None) -> list[ExtractedSection]:
    own = db is None
    if own:
        db = HistoryDB()
    try:
        text = db.get_transcript_content(video_id)
        if not text:
            return []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return [ExtractedSection(text=p, page_number=None) for p in paragraphs]
    finally:
        if own:
            db.close()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_extractor_transcript.py -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/rag/extractors/transcript.py tests/test_rag_extractor_transcript.py
git commit -m "feat(rag): transcript extractor over history.transcript_search"
```

---

## Task 8: Cost helpers (token counter, log writer, 2M cap, daily warning)

**Files:**
- Create: `src/tui_transcript/services/rag/cost.py`
- Create: `tests/test_rag_cost.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_cost.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_cost.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `cost.py`**

Create `src/tui_transcript/services/rag/cost.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_cost.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/rag/cost.py tests/test_rag_cost.py
git commit -m "feat(rag): cost helpers — token counter, batch logging, source cap, daily warning"
```

---

## Task 9: Ingest pipeline

**Files:**
- Create: `src/tui_transcript/services/rag/ingest.py`
- Create: `tests/test_rag_ingest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_ingest.py`:

```python
"""End-to-end ingest pipeline with FakeEmbedder + FakeVectorStore."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.ingest import (
    ingest_file,
    reindex_transcript,
)
from tui_transcript.services.rag.store import FakeVectorStore


def _seed_collection(db: HistoryDB) -> int:
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    return db._conn.execute("SELECT id FROM collections").fetchone()[0]


def _insert_file(db: HistoryDB, collection_id: int, storage_path: Path) -> int:
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (
            collection_id,
            storage_path.name,
            str(storage_path),
            "application/pdf",
            storage_path.stat().st_size,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db._conn.commit()
    return cur.lastrowid


def test_ingest_pdf_writes_chunks_and_marks_indexed(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    fid = _insert_file(db, cid, pdf)

    store = FakeVectorStore()
    embedder = FakeEmbedder()

    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)

    row = db._conn.execute(
        "SELECT status, indexed_at FROM materia_files WHERE id = ?", (fid,)
    ).fetchone()
    assert row[0] == "indexed"
    assert row[1] is not None
    assert len(store._items) >= 2


def test_ingest_is_idempotent(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    fid = _insert_file(db, cid, pdf)

    store = FakeVectorStore()
    embedder = FakeEmbedder()
    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    n1 = len(store._items)
    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    n2 = len(store._items)
    assert n1 == n2


def test_ingest_marks_error_on_extractor_failure(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    bad = Path("/no/such.pdf")
    fid = _insert_file(db, cid, bad)
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    row = db._conn.execute(
        "SELECT status, error_message FROM materia_files WHERE id = ?", (fid,)
    ).fetchone()
    assert row[0] == "error"
    assert row[1]


def test_reindex_transcript_writes_chunks(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    db.record(
        source_path="/v/l.mp4",
        prefix="T",
        naming_mode="sequential",
        sequential_number=1,
        output_title="Lec",
        output_mode="markdown",
        output_path="/o/L.md",
        language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/l.mp4", "Uno.\n\nDos.\n\nTres.")

    store = FakeVectorStore()
    reindex_transcript(video_id=vid, collection_id=cid, db=db, embedder=FakeEmbedder(), store=store)
    assert len(store._items) >= 3
    assert all(c.source_type == "transcript" for c in store._items)
    assert all(c.collection_id == cid for c in store._items)


def test_reindex_transcript_overwrites_old_chunks(db: HistoryDB) -> None:
    cid = _seed_collection(db)
    db.record(
        source_path="/v/l.mp4",
        prefix="T",
        naming_mode="sequential",
        sequential_number=1,
        output_title="Lec",
        output_mode="markdown",
        output_path="/o/L.md",
        language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/l.mp4", "Uno.\n\nDos.")

    store = FakeVectorStore()
    embedder = FakeEmbedder()
    reindex_transcript(video_id=vid, collection_id=cid, db=db, embedder=embedder, store=store)
    n1 = len(store._items)
    # Re-run with the same content; count must stay the same.
    reindex_transcript(video_id=vid, collection_id=cid, db=db, embedder=embedder, store=store)
    assert len(store._items) == n1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_ingest.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `ingest.py`**

Create `src/tui_transcript/services/rag/ingest.py`:

```python
"""Ingest pipeline. Each entry point is idempotent."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.chunker import ChunkOut, chunk_sections
from tui_transcript.services.rag.cost import (
    EmbeddingCostError,
    count_tokens,
    enforce_source_cap,
    log_embedding_batch,
)
from tui_transcript.services.rag.embedder import Embedder, OpenAIEmbedder
from tui_transcript.services.rag.extractors import get_extractor
from tui_transcript.services.rag.extractors.transcript import extract_transcript
from tui_transcript.services.rag.store import (
    Chunk,
    SqliteVecStore,
    VectorStore,
)

logger = logging.getLogger(__name__)

EMBED_BATCH = 100


def ingest_file(
    *,
    file_id: int,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> None:
    """Extract → chunk → embed → store one materia_files row."""
    own_db = db is None
    if own_db:
        db = HistoryDB()
    embedder = embedder or OpenAIEmbedder()
    store = store or SqliteVecStore(db=db)
    try:
        row = db._conn.execute(
            "SELECT collection_id, storage_path, mime_type FROM materia_files WHERE id = ?",
            (file_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"materia_files id {file_id} not found")
        collection_id, storage_path, mime_type = row

        try:
            _set_status(db, file_id, "extracting")
            extractor = get_extractor(mime_type)
            if extractor is None:
                raise RuntimeError(f"No extractor for mime type: {mime_type}")
            sections = extractor(Path(storage_path))
            chunks_out = chunk_sections(sections)

            tokens = count_tokens([c.text for c in chunks_out])
            enforce_source_cap(tokens)

            _set_status(db, file_id, "embedding")
            store.delete(
                source_type="pdf",
                source_id=str(file_id),
                embedding_model=embedder.model,
            )
            _embed_and_upsert(
                db=db,
                store=store,
                embedder=embedder,
                source_type="pdf",
                source_id=str(file_id),
                collection_id=collection_id,
                chunks_out=chunks_out,
            )
            db._conn.execute(
                "UPDATE materia_files SET status='indexed', indexed_at=?, error_message=NULL "
                "WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), file_id),
            )
            db._conn.commit()
        except (EmbeddingCostError, Exception) as exc:
            logger.exception("ingest_file failed for file_id=%s", file_id)
            db._conn.execute(
                "UPDATE materia_files SET status='error', error_message=? WHERE id=?",
                (str(exc), file_id),
            )
            db._conn.commit()
    finally:
        if own_db:
            db.close()


def reindex_transcript(
    *,
    video_id: int,
    collection_id: int,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> None:
    """(Re-)embed a video's transcript into the index for one collection.

    Source identity is `(transcript, f"{video_id}-{collection_id}")` so the
    same transcript can live in multiple materias without collisions.
    """
    own_db = db is None
    if own_db:
        db = HistoryDB()
    embedder = embedder or OpenAIEmbedder()
    store = store or SqliteVecStore(db=db)
    try:
        sections = extract_transcript(video_id, db=db)
        if not sections:
            return
        chunks_out = chunk_sections(sections)
        tokens = count_tokens([c.text for c in chunks_out])
        try:
            enforce_source_cap(tokens)
        except EmbeddingCostError as exc:
            logger.warning("Skipping transcript %s: %s", video_id, exc)
            return

        source_id = f"{video_id}-{collection_id}"
        store.delete(
            source_type="transcript",
            source_id=source_id,
            embedding_model=embedder.model,
        )
        _embed_and_upsert(
            db=db,
            store=store,
            embedder=embedder,
            source_type="transcript",
            source_id=source_id,
            collection_id=collection_id,
            chunks_out=chunks_out,
        )
    finally:
        if own_db:
            db.close()


def _embed_and_upsert(
    *,
    db: HistoryDB,
    store: VectorStore,
    embedder: Embedder,
    source_type: str,
    source_id: str,
    collection_id: int,
    chunks_out: list[ChunkOut],
) -> None:
    for batch_start in range(0, len(chunks_out), EMBED_BATCH):
        batch = chunks_out[batch_start : batch_start + EMBED_BATCH]
        texts = [c.text for c in batch]
        t0 = time.perf_counter()
        vectors = embedder.embed(texts)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log_embedding_batch(
            db=db,
            source_type=source_type,
            source_id=source_id,
            batch_size=len(batch),
            tokens=count_tokens(texts),
            latency_ms=latency_ms,
        )
        store.upsert([
            Chunk(
                collection_id=collection_id,
                source_type=source_type,
                source_id=source_id,
                chunk_index=batch_start + i,
                text=c.text,
                page_number=c.page_number,
                embedding_model=embedder.model,
                embedding=vec,
            )
            for i, (c, vec) in enumerate(zip(batch, vectors))
        ])


def _set_status(db: HistoryDB, file_id: int, status: str) -> None:
    db._conn.execute("UPDATE materia_files SET status=? WHERE id=?", (status, file_id))
    db._conn.commit()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_ingest.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/rag/ingest.py tests/test_rag_ingest.py
git commit -m "feat(rag): ingest pipeline (extract → chunk → embed → store) with idempotency"
```

---

## Task 10: Background worker + crash recovery

**Files:**
- Create: `src/tui_transcript/services/rag/background.py`
- Create: `tests/test_rag_background.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_background.py`:

```python
"""Background ingestion worker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import background as bg
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.store import FakeVectorStore


@pytest.fixture(autouse=True)
def _reset_worker() -> None:
    bg.shutdown()
    yield
    bg.shutdown()


def _seed_collection_and_file(db: HistoryDB, pdf: Path) -> tuple[int, int]:
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    cid = db._conn.execute("SELECT id FROM collections").fetchone()[0]
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cid, pdf.name, str(pdf), "application/pdf", pdf.stat().st_size,
         "pending", datetime.now(timezone.utc).isoformat()),
    )
    db._conn.commit()
    return cid, cur.lastrowid


@pytest.mark.asyncio
async def test_worker_processes_enqueued_file(db: HistoryDB) -> None:
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cid, fid = _seed_collection_and_file(db, pdf)

    store = FakeVectorStore()
    bg.start(db=db, embedder=FakeEmbedder(), store=store)
    bg.enqueue_ingest_file(fid)
    await bg.drain()

    status = db._conn.execute(
        "SELECT status FROM materia_files WHERE id=?", (fid,)
    ).fetchone()[0]
    assert status == "indexed"


@pytest.mark.asyncio
async def test_recover_stuck_jobs_on_start(db: HistoryDB) -> None:
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cid, fid = _seed_collection_and_file(db, pdf)
    db._conn.execute("UPDATE materia_files SET status='extracting' WHERE id=?", (fid,))
    db._conn.commit()

    store = FakeVectorStore()
    bg.start(db=db, embedder=FakeEmbedder(), store=store)
    await bg.drain()

    status = db._conn.execute(
        "SELECT status FROM materia_files WHERE id=?", (fid,)
    ).fetchone()[0]
    assert status == "indexed"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_background.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `background.py`**

Create `src/tui_transcript/services/rag/background.py`:

```python
"""In-process asyncio worker for RAG ingestion.

Single concurrency. The FastAPI app starts this in its lifespan; tests start
it explicitly. On start, every materia_files row stuck in extracting/embedding
is re-enqueued (recovery from crash).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import Embedder, OpenAIEmbedder
from tui_transcript.services.rag.ingest import ingest_file, reindex_transcript
from tui_transcript.services.rag.store import (
    SqliteVecStore,
    VectorStore,
)

logger = logging.getLogger(__name__)


_queue: asyncio.Queue | None = None
_task: asyncio.Task | None = None
_db: HistoryDB | None = None
_embedder: Embedder | None = None
_store: VectorStore | None = None


def start(
    *,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> None:
    """Start the worker. Idempotent."""
    global _queue, _task, _db, _embedder, _store
    if _task is not None and not _task.done():
        return
    _db = db or HistoryDB()
    _embedder = embedder or OpenAIEmbedder()
    _store = store or SqliteVecStore(db=_db)
    _queue = asyncio.Queue()
    _task = asyncio.create_task(_run())
    _recover_stuck_jobs()


def shutdown() -> None:
    """Stop the worker and drop state. Safe to call multiple times."""
    global _queue, _task, _db, _embedder, _store
    if _task is not None and not _task.done():
        _task.cancel()
    _queue = None
    _task = None
    _db = None
    _embedder = None
    _store = None


def enqueue_ingest_file(file_id: int) -> None:
    if _queue is None:
        raise RuntimeError("worker not started")
    _queue.put_nowait(("ingest_file", {"file_id": file_id}))


def enqueue_reindex_transcript(video_id: int, collection_id: int) -> None:
    if _queue is None:
        raise RuntimeError("worker not started")
    _queue.put_nowait(
        ("reindex_transcript", {"video_id": video_id, "collection_id": collection_id})
    )


async def drain() -> None:
    """Block until the queue is empty AND the in-flight job finishes. Test helper."""
    if _queue is None:
        return
    await _queue.join()


async def _run() -> None:
    assert _queue is not None
    while True:
        try:
            kind, kwargs = await _queue.get()
        except asyncio.CancelledError:
            return
        try:
            await asyncio.to_thread(_dispatch, kind, kwargs)
        except Exception:
            logger.exception("background worker job %s failed", kind)
        finally:
            _queue.task_done()


def _dispatch(kind: str, kwargs: dict) -> None:
    if kind == "ingest_file":
        ingest_file(db=_db, embedder=_embedder, store=_store, **kwargs)
    elif kind == "reindex_transcript":
        reindex_transcript(db=_db, embedder=_embedder, store=_store, **kwargs)
    else:
        raise RuntimeError(f"unknown job kind: {kind}")


def _recover_stuck_jobs() -> None:
    assert _db is not None
    rows = _db._conn.execute(
        "SELECT id FROM materia_files WHERE status IN ('extracting', 'embedding')"
    ).fetchall()
    for (file_id,) in rows:
        enqueue_ingest_file(file_id)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_background.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/rag/background.py tests/test_rag_background.py
git commit -m "feat(rag): asyncio background worker with crash recovery"
```

---

## Task 11: Retrieval

**Files:**
- Create: `src/tui_transcript/services/rag/retrieve.py`
- Create: `tests/test_rag_retrieve.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_retrieve.py`:

```python
"""retrieve.search() — used by both /rag/search and the MCP server."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import ingest
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.retrieve import Hit, search
from tui_transcript.services.rag.store import FakeVectorStore


def _seed_with_pdf(db: HistoryDB, store: FakeVectorStore, embedder: FakeEmbedder) -> int:
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('Redes', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    cid = db._conn.execute("SELECT id FROM collections").fetchone()[0]
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (cid, pdf.name, str(pdf), "application/pdf", pdf.stat().st_size,
         datetime.now(timezone.utc).isoformat()),
    )
    db._conn.commit()
    fid = cur.lastrowid
    ingest.ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    return cid


def test_search_returns_hits_for_known_text(db: HistoryDB) -> None:
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    cid = _seed_with_pdf(db, store, embedder)
    hits = search(
        "redes neuronales",
        db=db,
        embedder=embedder,
        store=store,
    )
    assert len(hits) >= 1
    assert all(isinstance(h, Hit) for h in hits)
    assert any("redes" in h.text.lower() for h in hits)
    assert hits[0].collection_id == cid
    assert hits[0].collection_name == "Redes"
    assert hits[0].source_type == "pdf"


def test_search_filters_by_collection(db: HistoryDB) -> None:
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    cid = _seed_with_pdf(db, store, embedder)
    # Add a second collection with no content; result must still come from cid.
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('Otro', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    other = db._conn.execute(
        "SELECT id FROM collections WHERE name='Otro'"
    ).fetchone()[0]

    none_hits = search("redes neuronales", collection_id=other, db=db, embedder=embedder, store=store)
    assert none_hits == []
    some_hits = search("redes neuronales", collection_id=cid, db=db, embedder=embedder, store=store)
    assert len(some_hits) >= 1


def test_search_drops_low_scores(db: HistoryDB) -> None:
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    _seed_with_pdf(db, store, embedder)
    # FakeEmbedder gives unrelated text a near-orthogonal vector → score < 0.25
    hits = search("totally orthogonal nonsense xyzzy", db=db, embedder=embedder, store=store)
    # We don't assert empty (collisions possible) but no result should exceed the floor.
    assert all(h.score >= 0.25 for h in hits)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_retrieve.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `retrieve.py`**

Create `src/tui_transcript/services/rag/retrieve.py`:

```python
"""Single retrieval entry point shared by web app and MCP."""

from __future__ import annotations

from dataclasses import dataclass

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import Embedder, OpenAIEmbedder
from tui_transcript.services.rag.store import (
    SqliteVecStore,
    StoreHit,
    VectorStore,
)

SCORE_FLOOR = 0.25


@dataclass
class Hit:
    text: str
    score: float
    collection_id: int
    collection_name: str
    source_type: str             # 'pdf' | 'transcript'
    source_label: str            # filename or class title
    source_id: str
    page_number: int | None
    chunk_index: int


def search(
    query: str,
    *,
    collection_id: int | None = None,
    k: int = 8,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> list[Hit]:
    own = db is None
    if own:
        db = HistoryDB()
    embedder = embedder or OpenAIEmbedder()
    store = store or SqliteVecStore(db=db)
    try:
        if not query.strip():
            return []
        qvec = embedder.embed([query])[0]
        raw = store.query(
            qvec,
            collection_id=collection_id,
            embedding_model=embedder.model,
            k=k * 2,
        )
        hits = [_hydrate(h, db) for h in raw if h.score >= SCORE_FLOOR]
        return hits[:k]
    finally:
        if own:
            db.close()


def _hydrate(h: StoreHit, db: HistoryDB) -> Hit:
    name_row = db._conn.execute(
        "SELECT name FROM collections WHERE id = ?", (h.collection_id,)
    ).fetchone()
    collection_name = name_row[0] if name_row else "?"

    if h.source_type == "pdf":
        row = db._conn.execute(
            "SELECT filename FROM materia_files WHERE id = ?", (int(h.source_id),)
        ).fetchone()
        source_label = row[0] if row else h.source_id
    elif h.source_type == "transcript":
        # source_id is "{video_id}-{collection_id}"
        video_id = int(h.source_id.split("-", 1)[0])
        row = db._conn.execute(
            "SELECT output_title FROM processed_videos WHERE id = ?", (video_id,)
        ).fetchone()
        source_label = row[0] if row else h.source_id
    else:
        source_label = h.source_id

    return Hit(
        text=h.text,
        score=h.score,
        collection_id=h.collection_id,
        collection_name=collection_name,
        source_type=h.source_type,
        source_label=source_label,
        source_id=h.source_id,
        page_number=h.page_number,
        chunk_index=h.chunk_index,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_retrieve.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tui_transcript/services/rag/retrieve.py tests/test_rag_retrieve.py
git commit -m "feat(rag): retrieval with collection filter, score floor, source-label hydration"
```

---

## Task 12: API routes — file CRUD + reindex + /rag/search

**Files:**
- Create: `src/tui_transcript/api/routes/materia_files.py`
- Create: `src/tui_transcript/api/routes/rag.py`
- Modify: `src/tui_transcript/api/main.py`
- Modify: `src/tui_transcript/api/schemas.py`
- Create: `tests/test_rag_api.py`

- [ ] **Step 1: Add response schemas**

Open `src/tui_transcript/api/schemas.py`. At the end of the file add:

```python
# ------------------------------------------------------------------
# RAG: materia files + search
# ------------------------------------------------------------------


class MateriaFileEntry(BaseModel):
    id: int
    collection_id: int
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    error_message: str | None
    uploaded_at: str
    indexed_at: str | None


class RagSearchHit(BaseModel):
    text: str
    score: float
    collection_id: int
    collection_name: str
    source_type: str
    source_label: str
    source_id: str
    page_number: int | None
    chunk_index: int


class RagSearchRequest(BaseModel):
    query: str
    collection_id: int | None = None
    k: int = 8
```

- [ ] **Step 2: Write the failing API tests**

Create `tests/test_rag_api.py`:

```python
"""Materia files routes + /rag/search."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Force HistoryDB and the materia_files storage root into tmp_path.
    from tui_transcript.services.history import HistoryDB
    from tui_transcript.api.routes import materia_files as mf_routes

    db_path = tmp_path / "h.db"
    monkeypatch.setattr(
        "tui_transcript.services.history.DB_PATH", db_path
    )
    monkeypatch.setattr(mf_routes, "STORAGE_ROOT", tmp_path / "files")

    # Use FakeEmbedder + FakeVectorStore for the worker.
    from tui_transcript.services.rag import background
    from tui_transcript.services.rag.embedder import FakeEmbedder
    from tui_transcript.services.rag.store import FakeVectorStore

    background.shutdown()

    # Build app AFTER patches so lifespan picks them up.
    from tui_transcript.api.main import app

    # Seed a collection.
    db = HistoryDB(db_path)
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    db.close()

    with TestClient(app) as c:
        # Override the worker init to use fakes (TestClient triggers lifespan).
        background.shutdown()
        background.start(embedder=FakeEmbedder(), store=FakeVectorStore())
        yield c
    background.shutdown()


def test_upload_lists_then_deletes(client) -> None:
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    with open(pdf, "rb") as fh:
        r = client.post(
            "/api/materias/1/files",
            files={"file": ("two_pages.pdf", fh, "application/pdf")},
        )
    assert r.status_code == 201, r.text
    fid = r.json()["id"]

    listing = client.get("/api/materias/1/files").json()
    assert any(f["id"] == fid for f in listing)

    deleted = client.delete(f"/api/materias/1/files/{fid}")
    assert deleted.status_code == 200

    listing2 = client.get("/api/materias/1/files").json()
    assert all(f["id"] != fid for f in listing2)


def test_rag_search_returns_hits_after_ingest(client) -> None:
    import asyncio
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    with open(pdf, "rb") as fh:
        client.post(
            "/api/materias/1/files",
            files={"file": ("two_pages.pdf", fh, "application/pdf")},
        )
    # Drain the worker.
    from tui_transcript.services.rag import background
    asyncio.get_event_loop().run_until_complete(background.drain())

    r = client.post(
        "/api/rag/search",
        json={"query": "redes neuronales", "collection_id": 1, "k": 4},
    )
    assert r.status_code == 200
    hits = r.json()
    assert len(hits) >= 1
    assert hits[0]["collection_id"] == 1


def test_reindex_endpoint(client) -> None:
    r = client.post("/api/materias/1/reindex")
    assert r.status_code == 202
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest tests/test_rag_api.py -v`
Expected: ImportError or 404 — routes don't exist yet.

- [ ] **Step 4: Implement `routes/materia_files.py`**

Create `src/tui_transcript/api/routes/materia_files.py`:

```python
"""HTTP routes for per-materia files + reindex queueing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from tui_transcript.api.schemas import MateriaFileEntry
from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import background

router = APIRouter(prefix="/materias", tags=["materia-files"])

STORAGE_ROOT = Path.home() / ".tui_transcript" / "materia_files"


def _db() -> HistoryDB:
    return HistoryDB()


@router.post("/{collection_id}/files", response_model=MateriaFileEntry, status_code=201)
async def upload_file(collection_id: int, file: UploadFile = File(...)) -> MateriaFileEntry:
    db = _db()
    try:
        if db._conn.execute(
            "SELECT 1 FROM collections WHERE id=?", (collection_id,)
        ).fetchone() is None:
            raise HTTPException(404, f"Collection {collection_id} not found")

        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        materia_dir = STORAGE_ROOT / str(collection_id)
        materia_dir.mkdir(parents=True, exist_ok=True)
        storage_path = materia_dir / f"{uuid.uuid4()}-{file.filename}"
        body = await file.read()
        storage_path.write_bytes(body)

        cur = db._conn.execute(
            "INSERT INTO materia_files "
            "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (
                collection_id,
                file.filename,
                str(storage_path),
                file.content_type or "application/octet-stream",
                len(body),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db._conn.commit()
        fid = cur.lastrowid
        background.enqueue_ingest_file(fid)
        row = db._conn.execute(
            "SELECT id, collection_id, filename, mime_type, size_bytes, status, "
            "error_message, uploaded_at, indexed_at FROM materia_files WHERE id=?",
            (fid,),
        ).fetchone()
        return _row_to_entry(row)
    finally:
        db.close()


@router.get("/{collection_id}/files", response_model=list[MateriaFileEntry])
def list_files(collection_id: int) -> list[MateriaFileEntry]:
    db = _db()
    try:
        rows = db._conn.execute(
            "SELECT id, collection_id, filename, mime_type, size_bytes, status, "
            "error_message, uploaded_at, indexed_at FROM materia_files "
            "WHERE collection_id=? ORDER BY uploaded_at DESC",
            (collection_id,),
        ).fetchall()
        return [_row_to_entry(r) for r in rows]
    finally:
        db.close()


@router.delete("/{collection_id}/files/{file_id}")
def delete_file(collection_id: int, file_id: int) -> dict:
    db = _db()
    try:
        row = db._conn.execute(
            "SELECT storage_path FROM materia_files WHERE id=? AND collection_id=?",
            (file_id, collection_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"File {file_id} not in materia {collection_id}")
        try:
            Path(row[0]).unlink(missing_ok=True)
        except OSError:
            pass
        # Drop chunks too.
        from tui_transcript.services.rag.store import SqliteVecStore
        from tui_transcript.services.rag.embedder import OpenAIEmbedder
        store = SqliteVecStore(db=db)
        store.delete(
            source_type="pdf",
            source_id=str(file_id),
            embedding_model=OpenAIEmbedder.model,
        )
        db._conn.execute("DELETE FROM materia_files WHERE id=?", (file_id,))
        db._conn.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/{collection_id}/reindex", status_code=202)
def reindex_materia(collection_id: int) -> dict:
    """Re-enqueue every file in this materia + every transcript already attached."""
    db = _db()
    try:
        for (fid,) in db._conn.execute(
            "SELECT id FROM materia_files WHERE collection_id=?", (collection_id,)
        ).fetchall():
            background.enqueue_ingest_file(fid)
        for (vid,) in db._conn.execute(
            "SELECT video_id FROM collection_items WHERE collection_id=?",
            (collection_id,),
        ).fetchall():
            background.enqueue_reindex_transcript(vid, collection_id)
        return {"ok": True}
    finally:
        db.close()


def _row_to_entry(r) -> MateriaFileEntry:
    return MateriaFileEntry(
        id=r[0],
        collection_id=r[1],
        filename=r[2],
        mime_type=r[3],
        size_bytes=r[4],
        status=r[5],
        error_message=r[6],
        uploaded_at=r[7],
        indexed_at=r[8],
    )
```

- [ ] **Step 5: Implement `routes/rag.py`**

Create `src/tui_transcript/api/routes/rag.py`:

```python
"""POST /rag/search — JSON wrapper around services.rag.retrieve.search()."""

from __future__ import annotations

from fastapi import APIRouter

from tui_transcript.api.schemas import RagSearchHit, RagSearchRequest
from tui_transcript.services.rag.retrieve import search

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/search", response_model=list[RagSearchHit])
def rag_search(req: RagSearchRequest) -> list[RagSearchHit]:
    hits = search(req.query, collection_id=req.collection_id, k=req.k)
    return [RagSearchHit(**h.__dict__) for h in hits]
```

- [ ] **Step 6: Wire routers + lifespan in `api/main.py`**

Open `src/tui_transcript/api/main.py`. Two edits:

**(a)** Extend the imports block (the multi-line `from tui_transcript.api.routes import (...)` around lines 15–29) to include the two new modules. The block becomes:

```python
from tui_transcript.api.routes import (
    collections,
    config,
    dashboard,
    documents,
    files,
    generation,
    learning,
    materia_files,
    models,
    paths,
    rag,
    search,
    stats,
    tags,
    transcription,
)
```

**(b)** Extend the existing `lifespan` function (around lines 59–65) to boot and shut down the RAG worker. Replace the function body with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    auto_register_legacy_output_dir()
    from tui_transcript.services.session_store import get_store
    get_store()
    from tui_transcript.services.rag import background as rag_background
    rag_background.start()
    try:
        yield
    finally:
        rag_background.shutdown()
```

**(c)** Add two `include_router` lines next to the existing block at the bottom:

```python
app.include_router(materia_files.router, prefix="/api")
app.include_router(rag.router, prefix="/api")
```

- [ ] **Step 7: Run tests to verify pass**

Run: `uv run pytest tests/test_rag_api.py -v`
Expected: 3 PASS.

- [ ] **Step 8: Run the full backend test suite**

Run: `uv run pytest tests/ -v --ignore=tests/test_rag_embedder.py::test_openai_embedder_real_call`
Expected: every existing test still PASSES.

- [ ] **Step 9: Commit**

```bash
git add src/tui_transcript/api/routes/materia_files.py src/tui_transcript/api/routes/rag.py src/tui_transcript/api/main.py src/tui_transcript/api/schemas.py tests/test_rag_api.py
git commit -m "feat(rag): /materias/{cid}/files (POST/GET/DELETE), /reindex, /rag/search routes"
```

---

## Task 13: Auto-reindex hooks (transcript completion + add to materia)

**Files:**
- Modify: `src/tui_transcript/api/routes/transcription.py`
- Modify: `src/tui_transcript/api/routes/collections.py`
- Create: `tests/test_rag_auto_reindex.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rag_auto_reindex.py`:

```python
"""Auto-enqueue reindex on transcript completion + collection attach."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_add_video_to_collection_enqueues_reindex(monkeypatch, tmp_path) -> None:
    from tui_transcript.services.history import HistoryDB
    monkeypatch.setattr("tui_transcript.services.history.DB_PATH", tmp_path / "h.db")
    from tui_transcript.services.rag import background
    from tui_transcript.services.rag.embedder import FakeEmbedder
    from tui_transcript.services.rag.store import FakeVectorStore
    background.shutdown()

    # Seed: collection + a transcribed video.
    db = HistoryDB(tmp_path / "h.db")
    db._conn.execute(
        "INSERT INTO collections (name, collection_type, description, created_at, updated_at) "
        "VALUES ('M', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db.record(
        source_path="/v/x.mp4", prefix="T", naming_mode="sequential",
        sequential_number=1, output_title="Lec", output_mode="markdown",
        output_path="/o/L.md", language="es",
    )
    vid = db._conn.execute("SELECT id FROM processed_videos").fetchone()[0]
    db.index_transcript(vid, "Lec", "/v/x.mp4", "Uno.\n\nDos.")
    db._conn.commit()
    db.close()

    from tui_transcript.api.main import app

    with patch.object(background, "enqueue_reindex_transcript") as enq, \
         TestClient(app) as c:
        background.start(embedder=FakeEmbedder(), store=FakeVectorStore())
        # collections.add_items takes a list of video_ids in the body.
        r = c.post("/api/collections/1/items", json={"video_ids": [vid]})
        assert r.status_code in (200, 201)
        enq.assert_called_with(vid, 1)
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_rag_auto_reindex.py -v`
Expected: FAIL — `enqueue_reindex_transcript` is never called.

- [ ] **Step 3: Hook the collection-add endpoint**

Open `src/tui_transcript/api/routes/collections.py`. Find the `add_items` handler (around line 99 — `@router.post("/{collection_id}/items", status_code=201)`). Replace its body with:

```python
@router.post("/{collection_id}/items", status_code=201)
def add_items(collection_id: int, body: CollectionAddItems) -> dict:
    store = _store()
    try:
        store.add_items(collection_id, body.video_ids)
        # Enqueue RAG reindex for each newly attached transcript.
        from tui_transcript.services.rag import background as _rag_bg
        for vid in body.video_ids:
            try:
                _rag_bg.enqueue_reindex_transcript(vid, collection_id)
            except RuntimeError:
                # Worker not started (isolated tests without lifespan).
                pass
        return {"ok": True, "added": len(body.video_ids)}
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    finally:
        store.close()
```

- [ ] **Step 4: Hook the transcription pipeline post-completion**

Open `src/tui_transcript/api/routes/transcription.py`. Find `_run_pipeline_with_sse`. After the `if collection_id is not None:` block that attaches videos to the collection, add another block that enqueues the reindex for every job that produced a video:

```python
        # Enqueue RAG reindex for the produced videos in every collection
        # that already contains them.
        from tui_transcript.services.rag import background as _rag_bg
        for job in jobs:
            if job.video_id is None:
                continue
            cids = [
                row[0]
                for row in HistoryDB()._conn.execute(
                    "SELECT collection_id FROM collection_items WHERE video_id=?",
                    (job.video_id,),
                ).fetchall()
            ]
            for cid in cids:
                try:
                    _rag_bg.enqueue_reindex_transcript(job.video_id, cid)
                except RuntimeError:
                    pass
```

(If `HistoryDB` is not yet imported in this file, add `from tui_transcript.services.history import HistoryDB` at the top.)

- [ ] **Step 5: Run test to verify pass**

Run: `uv run pytest tests/test_rag_auto_reindex.py -v`
Expected: PASS.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: all PASS (the `openai`-marked test is skipped).

- [ ] **Step 7: Commit**

```bash
git add src/tui_transcript/api/routes/transcription.py src/tui_transcript/api/routes/collections.py tests/test_rag_auto_reindex.py
git commit -m "feat(rag): auto-enqueue transcript reindex on pipeline complete + collection attach"
```

---

## Task 14: Frontend API client + Archivos tab

**Files:**
- Create: `frontend/src/api/rag.ts`
- Create: `frontend/src/components/MateriaFiles.tsx`
- Modify: `frontend/src/pages/CourseDetail.tsx`

- [ ] **Step 1: Create `frontend/src/api/rag.ts`**

```typescript
const API_BASE = '/api';

export interface MateriaFileEntry {
  id: number;
  collection_id: number;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: 'pending' | 'extracting' | 'embedding' | 'indexed' | 'error';
  error_message: string | null;
  uploaded_at: string;
  indexed_at: string | null;
}

export interface RagSearchHit {
  text: string;
  score: number;
  collection_id: number;
  collection_name: string;
  source_type: 'pdf' | 'transcript';
  source_label: string;
  source_id: string;
  page_number: number | null;
  chunk_index: number;
}

export async function listMateriaFiles(collectionId: number): Promise<MateriaFileEntry[]> {
  const res = await fetch(`${API_BASE}/materias/${collectionId}/files`);
  if (!res.ok) throw new Error('Failed to list files');
  return res.json();
}

export async function uploadMateriaFile(
  collectionId: number,
  file: File,
): Promise<MateriaFileEntry> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/materias/${collectionId}/files`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Upload failed');
  }
  return res.json();
}

export async function deleteMateriaFile(
  collectionId: number,
  fileId: number,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/materias/${collectionId}/files/${fileId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error('Delete failed');
}

export async function reindexMateria(collectionId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/materias/${collectionId}/reindex`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Reindex failed');
}

export async function ragSearch(
  query: string,
  collectionId?: number,
  k: number = 8,
): Promise<RagSearchHit[]> {
  const res = await fetch(`${API_BASE}/rag/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, collection_id: collectionId ?? null, k }),
  });
  if (!res.ok) throw new Error('Search failed');
  return res.json();
}
```

- [ ] **Step 2: Create `frontend/src/components/MateriaFiles.tsx`**

```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload as UploadIcon,
} from 'lucide-react';
import {
  listMateriaFiles,
  uploadMateriaFile,
  deleteMateriaFile,
  reindexMateria,
  type MateriaFileEntry,
} from '@/api/rag';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const ACCEPT = '.pdf,application/pdf';

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusIcon({ status }: { status: MateriaFileEntry['status'] }) {
  if (status === 'indexed')
    return <CheckCircle2 className="size-4 text-green-500 shrink-0" />;
  if (status === 'error')
    return <AlertCircle className="size-4 text-destructive shrink-0" />;
  return <Loader2 className="size-4 animate-spin text-primary shrink-0" />;
}

export function MateriaFiles({ collectionId }: { collectionId: number }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const { data: files = [], isLoading } = useQuery({
    queryKey: ['materia-files', collectionId],
    queryFn: () => listMateriaFiles(collectionId),
    refetchInterval: (q) => {
      const items = (q.state.data ?? []) as MateriaFileEntry[];
      const anyPending = items.some(
        (f) => f.status !== 'indexed' && f.status !== 'error',
      );
      return anyPending ? 2000 : false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadMateriaFile(collectionId, file),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['materia-files', collectionId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteMateriaFile(collectionId, id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['materia-files', collectionId] });
    },
  });

  const reindexMutation = useMutation({
    mutationFn: () => reindexMateria(collectionId),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['materia-files', collectionId] });
    },
  });

  const handleFiles = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setUploading(true);
    try {
      for (const f of Array.from(list)) {
        await uploadMutation.mutateAsync(f);
      }
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Archivos</h2>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => reindexMutation.mutate()}
            disabled={reindexMutation.isPending}
          >
            <RefreshCw className="size-3.5 mr-1.5" />
            Reindexar
          </Button>
          <Button
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <Loader2 className="size-3.5 mr-1.5 animate-spin" />
            ) : (
              <UploadIcon className="size-3.5 mr-1.5" />
            )}
            Subir PDF
          </Button>
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      {isLoading ? (
        <div className="flex justify-center py-6">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : files.length === 0 ? (
        <p className="text-sm text-muted-foreground italic">
          No hay archivos en esta materia. Sube un PDF para empezar.
        </p>
      ) : (
        <div className="space-y-2">
          {files.map((f) => (
            <Card key={f.id} className="py-0">
              <CardContent className="px-4 py-3 flex items-center gap-3">
                <FileText className="size-4 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{f.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatSize(f.size_bytes)} · {f.status}
                    {f.error_message ? ` — ${f.error_message}` : ''}
                  </p>
                </div>
                <StatusIcon status={f.status} />
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7 text-muted-foreground hover:text-destructive"
                  onClick={() => deleteMutation.mutate(f.id)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add the Archivos tab to `CourseDetail.tsx`**

Open `frontend/src/pages/CourseDetail.tsx`. Find where the existing tabs are rendered (look for the tab strip — `Mis Clases` or similar). Add a new tab entry and panel using whatever tab component is already in use. If the page uses simple buttons (matching `ClassDetail.tsx`'s pattern), add:

1. Import: `import { MateriaFiles } from '@/components/MateriaFiles';`
2. Extend the tabs array with `{ id: 'archivos', label: 'Archivos', icon: FileText }` (import `FileText` from `lucide-react` if not already).
3. Add the corresponding panel: `{activeTab === 'archivos' && <MateriaFiles collectionId={collection.id} />}` next to the existing panels.

If `CourseDetail.tsx` does not currently have tabs (single panel), introduce the same tab pattern used in `ClassDetail.tsx` (a `useState<Tab>` + a row of buttons + conditional rendering), and put the existing classes list under a new `'clases'` tab plus the new `'archivos'` tab.

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual smoke test**

Start the backend (`uv run tui-transcript-api`) and the frontend (`cd frontend && npm run dev`). Open a materia, switch to "Archivos", upload a small PDF. Verify:
- The file appears with status `pending` → `extracting` → `embedding` → `indexed` (polling at 2s).
- After indexing, the status icon goes green.
- Delete removes the file.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/rag.ts frontend/src/components/MateriaFiles.tsx frontend/src/pages/CourseDetail.tsx
git commit -m "feat(rag): Archivos tab with upload/list/delete/reindex"
```

---

## Task 15: MCP server — package + list_materias

**Files:**
- Create: `src/tui_transcript_mcp/__init__.py`
- Create: `src/tui_transcript_mcp/tools.py`
- Create: `tests/test_mcp_tools.py`

- [ ] **Step 1: Create the package marker**

Create `src/tui_transcript_mcp/__init__.py` containing exactly:

```python
"""Stdio MCP server exposing read-only RAG tools."""
```

- [ ] **Step 2: Update `pyproject.toml` to ship the new package**

Open `pyproject.toml`, find `[tool.hatch.build.targets.wheel]`, change:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/tui_transcript", "src/tui_transcript_mcp"]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_mcp_tools.py`:

```python
"""Pure functions behind the MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag import ingest
from tui_transcript.services.rag.embedder import FakeEmbedder
from tui_transcript.services.rag.store import FakeVectorStore
from tui_transcript_mcp.tools import (
    MateriaInfo,
    McpHit,
    list_materias,
    search_knowledge,
    MateriaNotFound,
    AmbiguousMateria,
)


def _seed(db: HistoryDB) -> tuple[int, FakeVectorStore]:
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (1, 'Redes Neuronales', 'course', 'Curso de DL', '2026-05-09', '2026-05-09')"
    )
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (2, 'Calculo', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    pdf = Path(__file__).parent / "fixtures" / "two_pages.pdf"
    cur = db._conn.execute(
        "INSERT INTO materia_files "
        "(collection_id, filename, storage_path, mime_type, size_bytes, status, uploaded_at) "
        "VALUES (1, 'Redes.pdf', ?, 'application/pdf', ?, 'pending', ?)",
        (str(pdf), pdf.stat().st_size, datetime.now(timezone.utc).isoformat()),
    )
    db._conn.commit()
    fid = cur.lastrowid
    store = FakeVectorStore()
    embedder = FakeEmbedder()
    ingest.ingest_file(file_id=fid, db=db, embedder=embedder, store=store)
    return fid, store


def test_list_materias_returns_counts(db: HistoryDB) -> None:
    _seed(db)
    materias = list_materias(db=db)
    assert any(m.name == "Redes Neuronales" and m.file_count >= 1 for m in materias)
    assert any(m.name == "Calculo" and m.file_count == 0 for m in materias)


def test_search_knowledge_with_exact_materia(db: HistoryDB) -> None:
    _, store = _seed(db)
    hits = search_knowledge(
        "redes neuronales",
        materia_name="Redes Neuronales",
        db=db,
        embedder=FakeEmbedder(),
        store=store,
    )
    assert len(hits) >= 1
    assert all(isinstance(h, McpHit) for h in hits)
    assert hits[0].materia == "Redes Neuronales"
    assert "Redes.pdf" in hits[0].source


def test_search_knowledge_fuzzy_materia(db: HistoryDB) -> None:
    _, store = _seed(db)
    hits = search_knowledge(
        "redes neuronales",
        materia_name="redes",  # lowercase, partial
        db=db,
        embedder=FakeEmbedder(),
        store=store,
    )
    assert hits[0].materia == "Redes Neuronales"


def test_search_knowledge_unknown_materia_raises(db: HistoryDB) -> None:
    _seed(db)
    with pytest.raises(MateriaNotFound) as exc:
        search_knowledge("x", materia_name="zoology", db=db,
                         embedder=FakeEmbedder(), store=FakeVectorStore())
    assert "zoology" in str(exc.value)


def test_search_knowledge_ambiguous_materia_raises(db: HistoryDB) -> None:
    db._conn.execute(
        "INSERT INTO collections (id, name, collection_type, description, created_at, updated_at) "
        "VALUES (3, 'Redes Sociales', 'course', '', '2026-05-09', '2026-05-09')"
    )
    db._conn.commit()
    _seed(db)
    with pytest.raises(AmbiguousMateria) as exc:
        search_knowledge("x", materia_name="redes", db=db,
                         embedder=FakeEmbedder(), store=FakeVectorStore())
    assert "Redes Neuronales" in str(exc.value)
    assert "Redes Sociales" in str(exc.value)


def test_search_knowledge_no_materia_searches_all(db: HistoryDB) -> None:
    _, store = _seed(db)
    hits = search_knowledge("redes neuronales", db=db,
                            embedder=FakeEmbedder(), store=store)
    assert len(hits) >= 1
```

- [ ] **Step 4: Run tests to verify failure**

Run: `uv run pytest tests/test_mcp_tools.py -v`
Expected: ImportError.

- [ ] **Step 5: Implement `tools.py`**

Create `src/tui_transcript_mcp/tools.py`:

```python
"""Pure functions behind the MCP tools.

`server.py` wraps these in MCP tool decorators. Keeping the logic here lets us
unit-test without spawning the stdio process.
"""

from __future__ import annotations

from dataclasses import dataclass

from tui_transcript.services.history import HistoryDB
from tui_transcript.services.rag.embedder import Embedder
from tui_transcript.services.rag.retrieve import Hit, search
from tui_transcript.services.rag.store import VectorStore


class MateriaNotFound(LookupError):
    pass


class AmbiguousMateria(LookupError):
    pass


@dataclass
class MateriaInfo:
    id: int
    name: str
    description: str
    file_count: int
    transcript_count: int
    indexed_chunk_count: int


@dataclass
class McpHit:
    text: str
    source: str
    materia: str
    score: float


def list_materias(*, db: HistoryDB | None = None) -> list[MateriaInfo]:
    own = db is None
    if own:
        db = HistoryDB()
    try:
        rows = db._conn.execute(
            "SELECT c.id, c.name, COALESCE(c.description, ''), "
            "  (SELECT COUNT(*) FROM materia_files mf WHERE mf.collection_id=c.id), "
            "  (SELECT COUNT(*) FROM collection_items ci WHERE ci.collection_id=c.id), "
            "  (SELECT COUNT(*) FROM rag_chunk_meta rm WHERE rm.collection_id=c.id) "
            "FROM collections c ORDER BY c.name"
        ).fetchall()
        return [MateriaInfo(*r) for r in rows]
    finally:
        if own:
            db.close()


def search_knowledge(
    query: str,
    *,
    materia_name: str | None = None,
    k: int = 8,
    db: HistoryDB | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> list[McpHit]:
    own = db is None
    if own:
        db = HistoryDB()
    try:
        collection_id: int | None = None
        if materia_name is not None:
            collection_id = _resolve_materia(db, materia_name)
        hits = search(
            query,
            collection_id=collection_id,
            k=k,
            db=db,
            embedder=embedder,
            store=store,
        )
        return [_to_mcp(h) for h in hits]
    finally:
        if own:
            db.close()


def _resolve_materia(db: HistoryDB, name: str) -> int:
    name_norm = name.strip().lower()
    rows = db._conn.execute("SELECT id, name FROM collections").fetchall()
    exact = [r for r in rows if r[1].lower() == name_norm]
    if len(exact) == 1:
        return exact[0][0]
    if len(exact) > 1:
        raise AmbiguousMateria(
            f"Multiple materias match exactly '{name}': "
            + ", ".join(r[1] for r in exact)
        )
    fuzzy = [r for r in rows if name_norm in r[1].lower()]
    if len(fuzzy) == 1:
        return fuzzy[0][0]
    if len(fuzzy) > 1:
        raise AmbiguousMateria(
            f"Materia '{name}' is ambiguous. Candidates: "
            + ", ".join(r[1] for r in fuzzy)
        )
    raise MateriaNotFound(
        f"No materia matches '{name}'. Available: "
        + ", ".join(r[1] for r in rows)
    )


def _to_mcp(h: Hit) -> McpHit:
    if h.source_type == "pdf":
        page = f", p.{h.page_number}" if h.page_number else ""
        source = f"PDF: {h.source_label}{page}"
    elif h.source_type == "transcript":
        source = f"Clase: {h.source_label} (transcripción)"
    else:
        source = f"{h.source_type}: {h.source_label}"
    return McpHit(text=h.text, source=source, materia=h.collection_name, score=h.score)
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/test_mcp_tools.py -v`
Expected: 6 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/tui_transcript_mcp/ tests/test_mcp_tools.py pyproject.toml
git commit -m "feat(mcp): list_materias + search_knowledge tool functions"
```

---

## Task 16: MCP server stdio entry point + smoke test

**Files:**
- Create: `src/tui_transcript_mcp/server.py`
- Create: `tests/test_mcp_smoke.py`

- [ ] **Step 1: Implement the stdio server**

Create `src/tui_transcript_mcp/server.py`:

```python
"""Stdio MCP server. Console script: `tui-transcript-mcp`.

Two read-only tools:
- list_materias()
- search_knowledge(query, materia_name=None, k=8)
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tui_transcript_mcp.tools import (
    AmbiguousMateria,
    MateriaNotFound,
    list_materias,
    search_knowledge,
)

logger = logging.getLogger(__name__)


def _build_server() -> Server:
    server = Server("tui-transcript")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name="list_materias",
                description=(
                    "List all materias (courses) in the user's knowledge base, "
                    "with file/transcript/chunk counts. Call this first to know "
                    "what materias exist."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="search_knowledge",
                description=(
                    "Semantic search over the user's materias (PDFs + class transcripts). "
                    "Pass `materia_name` to scope the search to one materia (use list_materias "
                    "to discover names). Omit `materia_name` to search across all materias."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "materia_name": {"type": "string"},
                        "k": {"type": "integer", "default": 8},
                    },
                    "required": ["query"],
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "list_materias":
            materias = await asyncio.to_thread(list_materias)
            payload = "\n".join(
                f"- {m.name} (id={m.id}): {m.file_count} files, "
                f"{m.transcript_count} transcripts, {m.indexed_chunk_count} chunks"
                + (f". {m.description}" if m.description else "")
                for m in materias
            )
            return [TextContent(type="text", text=payload or "(no materias)")]

        if name == "search_knowledge":
            try:
                hits = await asyncio.to_thread(
                    search_knowledge,
                    arguments["query"],
                    materia_name=arguments.get("materia_name"),
                    k=int(arguments.get("k", 8)),
                )
            except (MateriaNotFound, AmbiguousMateria) as exc:
                return [TextContent(type="text", text=f"Error: {exc}")]
            if not hits:
                return [TextContent(type="text", text="(no results)")]
            blocks = [
                f"[{h.score:.2f}] {h.source} — {h.materia}\n{h.text}"
                for h in hits
            ]
            return [TextContent(type="text", text="\n\n---\n\n".join(blocks))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _serve() -> None:
    server = _build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """Console script entry point."""
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Sync deps so the console_script registers**

Run: `uv sync`
Expected: completes successfully; `uv run which tui-transcript-mcp` (or `uv run tui-transcript-mcp --help` — note the SDK does not expose --help by default, so `which` is the right check) finds the new script.

Run: `uv run python -c "from tui_transcript_mcp.server import main; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Write the smoke test**

Create `tests/test_mcp_smoke.py`:

```python
"""Smoke test the stdio MCP server boots and answers `list_tools`."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest


@pytest.mark.asyncio
async def test_mcp_server_lists_tools() -> None:
    """Spawn the server as a subprocess and verify the MCP handshake + tools list."""
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tui_transcript_mcp.server"],
        env={**os.environ, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "fake")},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=10)
            tools = await asyncio.wait_for(session.list_tools(), timeout=10)
            names = {t.name for t in tools.tools}
            assert names == {"list_materias", "search_knowledge"}
```

- [ ] **Step 4: Make `python -m tui_transcript_mcp.server` runnable**

Add `if __name__ == "__main__": main()` is already in server.py from step 1 — verified.

- [ ] **Step 5: Run the smoke test**

Run: `uv run pytest tests/test_mcp_smoke.py -v`
Expected: PASS within ~10s.

- [ ] **Step 6: Manual MCP host test (optional but recommended)**

Add to your Claude Desktop config at `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tui-transcript": {
      "command": "tui-transcript-mcp",
      "env": { "OPENAI_API_KEY": "sk-..." }
    }
  }
}
```

Restart Claude Desktop. In a chat, ask "What materias are in my knowledge base?" — Claude should call `list_materias`. Then ask "What does my knowledge base say about redes neuronales?" — Claude should call `search_knowledge` and quote chunks.

- [ ] **Step 7: Commit**

```bash
git add src/tui_transcript_mcp/server.py tests/test_mcp_smoke.py
git commit -m "feat(mcp): stdio server with list_materias + search_knowledge"
```

---

## Task 17: Final regression sweep + push

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: every test PASSES (the `openai`-marked test is SKIPPED).

- [ ] **Step 2: Type-check the frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: zero errors.

- [ ] **Step 3: Verify the API still boots**

Run (in a separate terminal): `uv run tui-transcript-api`
Expected: Uvicorn starts; logs show "Application startup complete." with no errors. Visit `http://localhost:8000/docs` and confirm the new routes (`POST /api/materias/{cid}/files`, `POST /api/rag/search`, etc.) are listed. Stop the server (Ctrl-C).

- [ ] **Step 4: Push the branch**

Run:
```bash
git push -u origin feat/materia-rag-mcp
```

Expected: branch pushes; the GitHub URL for opening a PR is printed.

---

## Self-Review Notes (for the implementer)

- The OpenAI cost ceilings (`PRICE_PER_1M_TOKENS`, `SOURCE_TOKEN_CAP`, `DAILY_WARN_USD`) are hardcoded constants in `cost.py`. If OpenAI changes their pricing, update them in one place.
- `SqliteVecStore.query()` converts L2 distance to an approximate cosine similarity using `1 - d²/2`, which is exact for unit vectors. `OpenAIEmbedder` returns unit vectors; `FakeEmbedder` is normalized to unit length too. If a future Embedder returns un-normalized vectors, the score interpretation breaks — normalize there.
- `reindex_transcript` uses `source_id = "{video_id}-{collection_id}"` so the same transcript can live in multiple materias without colliding on the `UNIQUE(source_type, source_id, chunk_index, embedding_model)` constraint.
- The MCP server opens its own `HistoryDB`. Since SQLite WAL is already enabled in `HistoryDB.__init__`, the FastAPI app and the MCP server can both run against `~/.tui_transcript/history.db` simultaneously without locking issues.
- The Archivos tab UI polls every 2 s while any file is non-terminal. That is fine for local single-user; if we ever go multi-user, switch to SSE.
