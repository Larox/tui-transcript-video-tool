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
