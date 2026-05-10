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
