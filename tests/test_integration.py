"""Integration test: transcription -> collection -> tag -> search end-to-end."""

from __future__ import annotations

from pathlib import Path

import pytest

from tui_transcript.services.collection_store import CollectionStore
from tui_transcript.services.history import HistoryDB


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDB:
    db = HistoryDB(tmp_path / "integration.db")
    yield db
    db.close()


@pytest.fixture()
def store(db: HistoryDB) -> CollectionStore:
    return CollectionStore(db=db)


def _simulate_transcription(db: HistoryDB, idx: int, transcript: str) -> int:
    """Simulate what the pipeline does after a successful transcription."""
    source = f"/videos/lecture_{idx}.mp4"
    title = f"Lecture {idx}"
    output = f"/output/Lecture_{idx}.md"

    # 1. Record the processed video (what pipeline.py does)
    db.record(
        source_path=source,
        prefix="Test",
        naming_mode="sequential",
        sequential_number=idx,
        output_title=title,
        output_mode="markdown",
        output_path=output,
        language="en",
    )

    # 2. Get the video ID
    video = db.get_video_by_source_and_prefix(source, "Test", "markdown")
    assert video is not None
    vid = video["id"]

    # 3. Index transcript for search (what pipeline.py now does)
    db.index_transcript(vid, title, source, transcript)

    return vid


class TestEndToEnd:
    def test_full_workflow(self, store: CollectionStore, db: HistoryDB) -> None:
        """Test the complete flow: transcribe -> organize -> search."""

        # --- Step 1: Simulate transcribing 3 videos ---
        vid1 = _simulate_transcription(
            db, 1,
            "Welcome to the machine learning course. Today we cover neural networks "
            "and backpropagation algorithms for training deep learning models."
        )
        vid2 = _simulate_transcription(
            db, 2,
            "In this session we explore convolutional neural networks for image "
            "classification and object detection using Python and PyTorch."
        )
        vid3 = _simulate_transcription(
            db, 3,
            "Design patterns in software engineering. We discuss the singleton "
            "pattern, factory pattern, and observer pattern with practical examples."
        )

        # --- Step 2: Create collections ---
        ml_course = store.create_collection(
            "Machine Learning 101", "course", "Intro to ML"
        )
        design_mentorship = store.create_collection(
            "Software Design Mentorship", "mentorship", "Design patterns review"
        )

        # --- Step 3: Add videos to collections ---
        store.add_items(ml_course["id"], [vid1, vid2])
        store.add_item(design_mentorship["id"], vid3)

        # Verify collections have correct counts
        collections = store.list_collections()
        by_name = {c["name"]: c for c in collections}
        assert by_name["Machine Learning 101"]["item_count"] == 2
        assert by_name["Software Design Mentorship"]["item_count"] == 1

        # --- Step 4: Tag videos ---
        python_tag = store.create_tag("python", "#3b82f6")
        ml_tag = store.create_tag("machine-learning", "#ef4444")
        patterns_tag = store.create_tag("design-patterns", "#22c55e")

        store.add_video_tag(vid1, ml_tag["id"])
        store.add_video_tag(vid2, ml_tag["id"])
        store.add_video_tag(vid2, python_tag["id"])
        store.add_video_tag(vid3, patterns_tag["id"])

        # Verify tags
        assert len(store.get_video_tags(vid2)) == 2

        # --- Step 5: Search across all transcripts ---
        results = store.search("neural")
        assert len(results) == 2  # vid1 and vid2

        results = store.search("pattern")
        assert len(results) == 1  # only vid3
        assert results[0]["video_id"] == vid3

        # --- Step 6: Search within a collection ---
        results = store.search("neural", collection_id=ml_course["id"])
        assert len(results) == 2

        results = store.search("neural", collection_id=design_mentorship["id"])
        assert len(results) == 0  # no neural networks in design mentorship

        # --- Step 7: Search filtered by tag ---
        results = store.search("Python", tag_name="python")
        assert len(results) == 1
        assert results[0]["video_id"] == vid2

        # --- Step 8: Collection detail with items and their tags ---
        detail = store.get_collection_with_items(ml_course["id"])
        assert len(detail["items"]) == 2
        # First item should have tags
        item_tags = {t["name"] for item in detail["items"] for t in item["tags"]}
        assert "machine-learning" in item_tags
        assert "python" in item_tags

        # --- Step 9: Reorder items ---
        store.reorder_items(ml_course["id"], [vid2, vid1])
        detail = store.get_collection_with_items(ml_course["id"])
        assert detail["items"][0]["id"] == vid2
        assert detail["items"][1]["id"] == vid1

        # --- Step 10: Remove from collection (doesn't delete transcript) ---
        store.remove_item(ml_course["id"], vid1)
        detail = store.get_collection_with_items(ml_course["id"])
        assert len(detail["items"]) == 1

        # Transcript still searchable globally
        results = store.search("backpropagation")
        assert len(results) == 1

    def test_delete_collection_preserves_transcripts(
        self, store: CollectionStore, db: HistoryDB
    ) -> None:
        """Deleting a collection should not delete the videos or their search index."""
        vid = _simulate_transcription(db, 1, "Important content about databases")
        c = store.create_collection("Temp", "other")
        store.add_item(c["id"], vid)

        store.delete_collection(c["id"])

        # Video still searchable
        results = store.search("databases")
        assert len(results) == 1

        # Video still listed
        videos = store.list_videos()
        assert any(v["id"] == vid for v in videos)

    def test_delete_tag_preserves_video(
        self, store: CollectionStore, db: HistoryDB
    ) -> None:
        """Deleting a tag should remove associations but not videos."""
        vid = _simulate_transcription(db, 1, "Python tutorial")
        t = store.create_tag("python")
        store.add_video_tag(vid, t["id"])

        store.delete_tag(t["id"])

        # Video still exists, just untagged
        assert len(store.get_video_tags(vid)) == 0
        assert len(store.search("Python")) == 1
