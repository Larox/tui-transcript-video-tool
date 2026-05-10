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
