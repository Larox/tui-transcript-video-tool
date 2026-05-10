"""POST /rag/search — JSON wrapper around services.rag.retrieve.search()."""

from __future__ import annotations

from fastapi import APIRouter

from tui_transcript.api.schemas import RagSearchHit, RagSearchRequest
from tui_transcript.services.rag import background
from tui_transcript.services.rag.retrieve import search

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/search", response_model=list[RagSearchHit])
def rag_search(req: RagSearchRequest) -> list[RagSearchHit]:
    # Reuse the embedder + store the background worker was booted with.
    # In tests the worker holds FakeEmbedder/FakeVectorStore; in production
    # it's OpenAIEmbedder + SqliteVecStore. Falling through to None lets
    # search() construct the production defaults if the worker is down.
    embedder, store = background.get_components()
    hits = search(
        req.query,
        collection_id=req.collection_id,
        k=req.k,
        embedder=embedder,
        store=store,
    )
    return [RagSearchHit(**h.__dict__) for h in hits]
