# Materia RAG + MCP Server — Design Spec

**Date:** 2026-05-09
**Status:** Approved
**Branch:** `feat/materia-rag-mcp`
**Scope:** Narrow vertical slice (option A, expanded to "C-shaped pipeline"): PDFs + existing transcripts as day-1 sources, stdio MCP server, single-user.

---

## Overview

Add a per-materia retrieval-augmented generation (RAG) layer to `tui-transcript`. Users upload PDFs into a materia; the system extracts, chunks, embeds, and stores them in a vector index. Existing class transcripts are silently mirrored into the same index. An MCP server (stdio transport) exposes two read-only tools so an external host LLM (Claude Desktop, Cursor, Claude Code) can search the user's knowledge base by materia and topic.

**Core premise:** Both the web app and the MCP server call the *same* retrieval function. There is no "MCP-specific" search path.

---

## Approach

Three subsystems with strict boundaries:

```
┌─ Ingestion ────────────────┐    ┌─ Retrieval ────────────┐
│  upload  → extract → chunk │    │  embed query → vector  │
│         → embed → store    │ →  │  search → filter → top │
└────────────────────────────┘    └────────────────────────┘
           ↓                                    ↑
       sqlite-vec (rag_chunks + rag_chunk_meta)
                                                ↑
                                  ┌─ Surfaces ──┴─────────┐
                                  │  FastAPI routes        │
                                  │  MCP server (stdio)    │
                                  └────────────────────────┘
```

**Stack:**
- Embeddings: OpenAI `text-embedding-3-small` (1536 dims).
- Vector store: `sqlite-vec` extension on the existing `~/.tui_transcript/history.db`.
- MCP transport: stdio.
- Background indexing: in-process `asyncio.Queue` worker, concurrency 1.

**Migration-friendly boundaries:**
- `services/rag/store.py` is the only file that knows `sqlite-vec` exists. Swapping to Chroma / pgvector / LanceDB later is one new file implementing `VectorStore`.
- `services/rag/embedder.py` is the only file that calls OpenAI's embeddings endpoint. Adding local `BGE-M3` later is one new `Embedder` impl.
- `services/rag/extractors/` is a registry. Adding `.ipynb` / `.py` extractors later is a new file + registration.

---

## Data model

Three new tables in `~/.tui_transcript/history.db`:

```sql
CREATE TABLE materia_files (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  collection_id   INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  filename        TEXT NOT NULL,
  storage_path    TEXT NOT NULL,
  mime_type       TEXT NOT NULL,
  size_bytes      INTEGER NOT NULL,
  status          TEXT NOT NULL,           -- 'pending'|'extracting'|'embedding'|'indexed'|'error'
  error_message   TEXT,
  uploaded_at     TEXT NOT NULL,
  indexed_at      TEXT
);

CREATE VIRTUAL TABLE rag_chunks USING vec0(
  embedding float[1536]
);

CREATE TABLE rag_chunk_meta (
  rowid           INTEGER PRIMARY KEY,     -- matches rag_chunks.rowid
  collection_id   INTEGER NOT NULL,
  source_type     TEXT NOT NULL,           -- 'pdf' | 'transcript'
  source_id       TEXT NOT NULL,           -- materia_files.id (str) or video_id (str)
  chunk_index     INTEGER NOT NULL,
  text            TEXT NOT NULL,
  page_number     INTEGER,
  embedding_model TEXT NOT NULL,
  UNIQUE(source_type, source_id, chunk_index, embedding_model)
);
CREATE INDEX idx_rag_meta_collection ON rag_chunk_meta(collection_id);
CREATE INDEX idx_rag_meta_source     ON rag_chunk_meta(source_type, source_id);

CREATE TABLE embedding_jobs_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT NOT NULL,
  source_id   TEXT NOT NULL,
  batch_size  INTEGER NOT NULL,
  tokens      INTEGER NOT NULL,
  latency_ms  INTEGER NOT NULL,
  cost_usd    REAL NOT NULL,
  created_at  TEXT NOT NULL
);
```

Storing `embedding_model` per chunk allows multiple model generations to coexist; queries filter to the current model. No "everything stops working during reindex" window.

---

## Module layout

```
src/tui_transcript/services/rag/
  __init__.py
  store.py           # VectorStore Protocol + SqliteVecStore
  embedder.py        # Embedder Protocol + OpenAIEmbedder
  chunker.py         # ExtractedSection -> list[Chunk]; ~800 chars, 100 overlap
  extractors/
    __init__.py      # registry: {mime_type: Extractor}
    pdf.py           # PDF -> [ExtractedSection(text, page_number)]
    transcript.py    # video_id -> [ExtractedSection(text, paragraph_index)]
  ingest.py          # ingest_file(file_id), reindex_transcript(video_id)
  retrieve.py        # search(query, collection_id?, k=8) -> list[Hit]
  background.py      # asyncio queue worker (single concurrency)

src/tui_transcript/api/routes/materia_files.py
  POST   /materias/{cid}/files          (multipart upload)
  GET    /materias/{cid}/files          (list with status)
  DELETE /materias/{cid}/files/{fid}    (deletes file + chunks)
  POST   /materias/{cid}/reindex        (queue full re-embed of materia)
  POST   /rag/search                    (web/CLI ad-hoc retrieval)

src/tui_transcript_mcp/                  # NEW top-level package
  __init__.py
  server.py                              # stdio MCP entry point
  tools.py                               # list_materias, search_knowledge

frontend/src/pages/CourseDetail.tsx      # add "Archivos" tab
frontend/src/components/MateriaFiles.tsx # new component
frontend/src/api/rag.ts                  # client for materia_files + /rag/search
```

`pyproject.toml` adds:
- `sqlite-vec` (vector extension)
- `pypdf` (PDF text extraction — pure Python, MIT, no system deps)
- `openai` (embeddings client; we already have `openai-compatible` paths via pydantic-ai but use the SDK directly here)
- `mcp` (official Python SDK for MCP server)

New script: `tui_transcript_mcp = "tui_transcript_mcp.server:main"`.

---

## Ingestion flow

**Path A — User uploads a PDF:**

1. `POST /materias/{cid}/files` (multipart). Server writes file to `~/.tui_transcript/materia_files/{cid}/{uuid}-{name}`, INSERTs `materia_files` with `status='pending'`, enqueues `ingest.ingest_file(file_id)`, returns `201` immediately.
2. Worker: `status='extracting'` → `extractors[mime].extract()` returns `[ExtractedSection]` per page → `status='embedding'` → `chunker.split()` → batch-embed (batch size 100) → `store.upsert()` → `status='indexed'`.
3. Frontend polls `GET /materias/{cid}/files` every 2s while any row is non-terminal.

**Path B — Transcript becomes available:**

After `pipeline.py` completes a video, the existing `_run_pipeline_with_sse` post-completion hook (where we already attach to a collection) additionally enqueues `ingest.reindex_transcript(video_id)` for **every collection that contains this video**. Same pipeline downstream. Silent — no UI feedback. Mirrors how summary generation is implicit.

When a video is added to a new materia (`POST /collections/{cid}/items`), enqueue the same reindex for that materia — transcripts catch up retroactively.

**Idempotency.** Every reindex starts with `store.delete(source_type, source_id, embedding_model)`, then re-inserts. The `UNIQUE(source_type, source_id, chunk_index, embedding_model)` constraint enforces no duplicates. Re-running `ingest_file` is always safe.

**Failure handling.** Worker exceptions write `status='error'` + `error_message`. UI renders an error + "Reintentar" button that re-enqueues. No silent retries.

**Background worker.** Single in-process `asyncio.Queue` + `asyncio.Task` started at FastAPI startup (`app.lifespan`). Concurrency = 1. On startup, re-enqueue every row stuck in `extracting` or `embedding` (recovery from crash).

**Cost guardrails:**
- Refuse to embed any single source over 2M tokens (~$0.04). Surface as `status='error'`.
- Daily WARN log when total embedding cost exceeds $1/day.

---

## Retrieval

```python
# services/rag/retrieve.py
@dataclass
class Hit:
    text: str
    score: float                  # cosine similarity, 0..1
    collection_id: int
    collection_name: str
    source_type: str              # 'pdf' | 'transcript'
    source_label: str             # filename or class title
    source_id: str
    page_number: int | None
    chunk_index: int

def search(
    query: str,
    *,
    collection_id: int | None = None,
    k: int = 8,
    embedder: Embedder = OpenAIEmbedder(),
    store: VectorStore = SqliteVecStore(),
) -> list[Hit]: ...
```

Flow inside `search`:
1. Embed query (one OpenAI call, ~50ms).
2. `store.query(embedding, materia_id=collection_id, k=k*2, embedding_model=embedder.model)` — overfetch 2× to allow filtering.
3. Drop hits with `score < 0.25` (low-similarity floor).
4. JOIN to `collections` and to either `materia_files` or `processed_videos` for `source_label`.

**No reranker, no hybrid, no chat UI in v1.** All deferred (see Out of Scope).

`POST /rag/search` is a thin JSON wrapper over `search()` for ad-hoc/curl testing.

---

## MCP server

**Process model.** Standalone stdio server. Console script `tui_transcript_mcp` registered in `pyproject.toml`. Opens the same `~/.tui_transcript/history.db` as FastAPI (read-only; SQLite WAL allows concurrent access). Reads `OPENAI_API_KEY` from the host's environment.

User configures their MCP host once. Claude Desktop / Cursor / Claude Code accept an `env` block to forward credentials:

```json
{
  "mcpServers": {
    "tui-transcript": {
      "command": "tui_transcript_mcp",
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

**Tools:**

```python
list_materias() -> list[MateriaInfo]

class MateriaInfo:
    id: int
    name: str
    description: str          # "" when collection.description is empty
    file_count: int
    transcript_count: int
    indexed_chunk_count: int  # signal: is this materia worth searching?
```

```python
search_knowledge(
    query: str,
    materia_name: str | None = None,
    k: int = 8,
) -> list[McpHit]

class McpHit:                 # distinct from services/rag/retrieve.py Hit
    text: str
    source: str               # "PDF: cap3_redes.pdf, p.12" or "Clase: Lección 3 (transcripción)"
    materia: str
    score: float
```

The MCP layer collapses the structured `Hit` (with `source_type`, `source_label`, `page_number`, etc.) into a single human-readable `source` string. Reasoning: tool responses are read by an LLM, not parsed programmatically — a single citation string is what the LLM needs to attribute the chunk in its answer.

**`materia_name` resolution:** exact case-insensitive match → `LIKE %name%` fallback → if 0 or >1 match, raise a tool error including the candidate list. The host LLM re-calls with disambiguated input.

Omitting `materia_name` searches across all materias.

**Read-only.** No write tools — no upload/delete/reindex. Management lives in the web app. Avoids accidentally giving an external host destructive power over the index.

**No streaming, no auth.** stdio inherits the host process's trust boundary. HTTP MCP + auth is a future spec.

---

## Cost, observability, testing

**Cost.** `text-embedding-3-small` = $0.02/1M tokens. A 100-page PDF ≈ $0.001. A 1-hour transcript ≈ $0.0002. Per-source 2M-token cap, $1/day soft warning.

**Observability.** Every embedding batch writes one row to `embedding_jobs_log` (`source_type, source_id, batch_size, tokens, latency_ms, cost_usd, created_at`). Retrieval logs nothing per query (volume risk via MCP) — add later if needed.

**Tests.**
- Unit: `chunker.py` (deterministic string splits), `extractors/pdf.py` (checked-in 2-page test PDF), `extractors/transcript.py` (fixture).
- Integration with fakes: `FakeEmbedder` (deterministic `hash(text)`-based vectors), `FakeVectorStore` (dict). End-to-end ingest + retrieve runs offline. Verifies: idempotency, materia filter, score floor.
- One opt-in real-network test (`pytest -m openai`) hits the live OpenAI API with a 50-token doc. Skipped by default.
- MCP smoke test: spawn server as subprocess, call `list_materias`, assert protocol shape.

No frontend tests for the new tab (matches existing convention).

---

## Out of scope (explicit)

- Notebook (`.ipynb`) / code (`.py`) extractors. Registry supports them; not registered v1.
- Reranker (Voyage rerank-2, Cohere rerank-3). v2.
- Hybrid search (BM25 + vector). Existing FTS5 stays separate.
- "Pregunta" chat UI inside the materia. `/rag/search` JSON exists; UI is a separate spec.
- Smart materia auto-routing inside the MCP (LLM picks materia from query). v2 if `list_materias`-based routing turns out to be poor in practice.
- HTTP MCP transport.
- Local embedding fallback (BGE-M3). Architecture supports it; not registered v1.
- Multi-user / auth.
- Auto re-embed on model change. Old chunks coexist (filtered by `embedding_model`); CLI re-embed command is v2.

---

## Future migration path (vector store)

When `sqlite-vec` becomes a bottleneck (>1M chunks, query latency >500ms):

1. Implement new adapter (`ChromaStore` / `PgVectorStore`) — ~200 lines, satisfies `VectorStore` Protocol.
2. Backfill: stream `rag_chunks` + `rag_chunk_meta` rows, push to new store. Vectors are floats — no re-embedding needed.
3. Switch `VECTOR_STORE` env var, redeploy. Materia filter that was a SQL JOIN becomes the new store's `where={"materia_id": X}`.
4. Delete `SqliteVecStore` once confident.

Stable chunk IDs — the natural composite key `(source_type, source_id, chunk_index, embedding_model)` — preserve identity across the migration so any evaluation set / regression tests still apply.
