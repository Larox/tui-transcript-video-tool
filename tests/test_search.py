"""Tests for full-text search functionality."""

from __future__ import annotations

from tui_transcript.services.collection_store import CollectionStore
from tui_transcript.services.history import HistoryDB
from tests.conftest import _insert_video


class TestSearch:
    def test_basic_search(self, store: CollectionStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.index_transcript(
            vid, "Lecture 1", "/videos/lecture_1.mp4",
            "Machine learning is a subset of artificial intelligence"
        )

        results = store.search("machine learning")
        assert len(results) == 1
        assert results[0]["video_id"] == vid
        assert "<mark>" in results[0]["excerpt"]

    def test_search_no_results(self, store: CollectionStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.index_transcript(vid, "Lecture 1", "/v.mp4", "Python basics")

        results = store.search("quantum physics")
        assert len(results) == 0

    def test_search_empty_query(self, store: CollectionStore) -> None:
        results = store.search("")
        assert results == []

    def test_search_multiple_transcripts(self, store: CollectionStore, db: HistoryDB) -> None:
        vid1 = _insert_video(db, 1)
        vid2 = _insert_video(db, 2)
        store.index_transcript(vid1, "Lecture 1", "/v1.mp4", "Introduction to neural networks")
        store.index_transcript(vid2, "Lecture 2", "/v2.mp4", "Advanced neural networks and deep learning")

        results = store.search("neural")
        assert len(results) == 2

    def test_search_filter_by_collection(self, store: CollectionStore, db: HistoryDB) -> None:
        vid1 = _insert_video(db, 1)
        vid2 = _insert_video(db, 2)
        store.index_transcript(vid1, "Lecture 1", "/v1.mp4", "Python programming basics")
        store.index_transcript(vid2, "Lecture 2", "/v2.mp4", "Python web development")

        c = store.create_collection("Web Dev", "course")
        store.add_item(c["id"], vid2)

        # Search within collection
        results = store.search("Python", collection_id=c["id"])
        assert len(results) == 1
        assert results[0]["video_id"] == vid2

    def test_search_filter_by_tag(self, store: CollectionStore, db: HistoryDB) -> None:
        vid1 = _insert_video(db, 1)
        vid2 = _insert_video(db, 2)
        store.index_transcript(vid1, "Lecture 1", "/v1.mp4", "Data structures overview")
        store.index_transcript(vid2, "Lecture 2", "/v2.mp4", "Data analysis with pandas")

        t = store.create_tag("data-science")
        store.add_video_tag(vid2, t["id"])

        results = store.search("Data", tag_name="data-science")
        assert len(results) == 1
        assert results[0]["video_id"] == vid2

    def test_index_update_replaces(self, store: CollectionStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        store.index_transcript(vid, "Lecture 1", "/v.mp4", "Old content about cats")
        store.index_transcript(vid, "Lecture 1", "/v.mp4", "New content about dogs")

        assert len(store.search("cats")) == 0
        assert len(store.search("dogs")) == 1
