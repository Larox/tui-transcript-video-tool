"""Embedding providers behind a single Protocol.

Migration boundary: this is the only file allowed to call OpenAI's embeddings
endpoint or any other vendor SDK. Adding a local BGE-M3 backend later means
adding one new class here that implements `Embedder`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Protocol

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Anything that turns text into fixed-dimension float vectors."""

    model: str  # canonical name written into rag_chunk_meta.embedding_model
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text. Order preserved."""
        ...


_WORD_RE = re.compile(r"\w+", re.UNICODE)


class FakeEmbedder:
    """Deterministic, network-free embedder for tests.

    Bag-of-words sparse embedding: each lowercased word in the input deterministically
    hashes to one of `dim` slots, and its count is added there. The vector is then
    normalized to unit length. Same text → same vector; texts that share words have
    non-zero cosine similarity; texts with no shared words are orthogonal. Not
    semantically meaningful, but good enough for offline retrieval-plumbing tests.
    """

    model: str = "fake-embedder-v1"

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            vec = [0.0] * self.dim
            for word in _WORD_RE.findall(t.lower()):
                h = hashlib.sha256(word.encode("utf-8")).digest()
                slot = int.from_bytes(h[:8], "big") % self.dim
                vec[slot] += 1.0
            norm = sum(x * x for x in vec) ** 0.5
            if norm == 0.0:
                # Fallback: an entirely word-less input still gets a deterministic vector
                # so identical empty/punctuation strings remain equal.
                h = hashlib.sha256(t.encode("utf-8")).digest()
                slot = int.from_bytes(h[:8], "big") % self.dim
                vec[slot] = 1.0
                norm = 1.0
            out.append([x / norm for x in vec])
        return out


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small backend."""

    model: str = "text-embedding-3-small"
    dim: int = 1536

    def __init__(self, api_key: str | None = None) -> None:
        # Defer client construction so instances can be built without a key
        # (e.g. in unit tests that only assert on `model`/`dim`).
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._get_client().embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]
