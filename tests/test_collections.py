"""Tests for CollectionStore CRUD operations."""

from __future__ import annotations

import pytest

from tui_transcript.services.collection_store import CollectionStore
from tui_transcript.services.history import HistoryDB
from tests.conftest import _insert_video


class TestCollectionCRUD:
    def test_create_and_list(self, store: CollectionStore) -> None:
        c = store.create_collection("ML Course", "course", "Machine learning")
        assert c["name"] == "ML Course"
        assert c["collection_type"] == "course"

        collections = store.list_collections()
        assert len(collections) == 1
        assert collections[0]["item_count"] == 0

    def test_create_validates_type(self, store: CollectionStore) -> None:
        with pytest.raises(ValueError, match="Invalid collection type"):
            store.create_collection("Bad", "invalid_type")

    def test_create_validates_empty_name(self, store: CollectionStore) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            store.create_collection("", "course")

    def test_update(self, store: CollectionStore) -> None:
        c = store.create_collection("Old Name", "course")
        updated = store.update_collection(c["id"], name="New Name")
        assert updated["name"] == "New Name"

    def test_delete(self, store: CollectionStore) -> None:
        c = store.create_collection("To Delete", "other")
        store.delete_collection(c["id"])
        assert len(store.list_collections()) == 0

    def test_delete_nonexistent_raises(self, store: CollectionStore) -> None:
        with pytest.raises(KeyError):
            store.delete_collection(999)

    def test_get_nonexistent_raises(self, store: CollectionStore) -> None:
        with pytest.raises(KeyError):
            store.get_collection(999)


class TestCollectionItems:
    def test_add_and_list_items(self, store: CollectionStore, db: HistoryDB) -> None:
        vid1 = _insert_video(db, 1)
        vid2 = _insert_video(db, 2)
        c = store.create_collection("Course", "course")

        store.add_item(c["id"], vid1)
        store.add_item(c["id"], vid2)

        detail = store.get_collection_with_items(c["id"])
        assert len(detail["items"]) == 2
        assert detail["items"][0]["output_title"] == "Lecture 1"
        assert detail["items"][1]["output_title"] == "Lecture 2"

    def test_remove_item(self, store: CollectionStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        c = store.create_collection("Course", "course")
        store.add_item(c["id"], vid)
        store.remove_item(c["id"], vid)

        detail = store.get_collection_with_items(c["id"])
        assert len(detail["items"]) == 0

    def test_remove_nonexistent_item_raises(self, store: CollectionStore) -> None:
        c = store.create_collection("Course", "course")
        with pytest.raises(KeyError):
            store.remove_item(c["id"], 999)

    def test_reorder(self, store: CollectionStore, db: HistoryDB) -> None:
        vid1 = _insert_video(db, 1)
        vid2 = _insert_video(db, 2)
        vid3 = _insert_video(db, 3)
        c = store.create_collection("Course", "course")

        store.add_items(c["id"], [vid1, vid2, vid3])
        # Reverse order
        store.reorder_items(c["id"], [vid3, vid2, vid1])

        detail = store.get_collection_with_items(c["id"])
        ids = [item["id"] for item in detail["items"]]
        assert ids == [vid3, vid2, vid1]

    def test_add_duplicate_is_idempotent(self, store: CollectionStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        c = store.create_collection("Course", "course")
        store.add_item(c["id"], vid)
        store.add_item(c["id"], vid)  # should not raise

        detail = store.get_collection_with_items(c["id"])
        assert len(detail["items"]) == 1

    def test_item_count_in_list(self, store: CollectionStore, db: HistoryDB) -> None:
        vid1 = _insert_video(db, 1)
        vid2 = _insert_video(db, 2)
        c = store.create_collection("Course", "course")
        store.add_items(c["id"], [vid1, vid2])

        collections = store.list_collections()
        assert collections[0]["item_count"] == 2


class TestTags:
    def test_create_and_list(self, store: CollectionStore) -> None:
        t = store.create_tag("python", "#3b82f6")
        assert t["name"] == "python"
        assert t["color"] == "#3b82f6"

        tags = store.list_tags()
        assert len(tags) == 1

    def test_create_empty_name_raises(self, store: CollectionStore) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            store.create_tag("")

    def test_delete_tag(self, store: CollectionStore) -> None:
        t = store.create_tag("to-delete")
        store.delete_tag(t["id"])
        assert len(store.list_tags()) == 0

    def test_video_tagging(self, store: CollectionStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        t1 = store.create_tag("python")
        t2 = store.create_tag("ml")

        store.add_video_tag(vid, t1["id"])
        store.add_video_tag(vid, t2["id"])

        tags = store.get_video_tags(vid)
        assert len(tags) == 2
        names = {t["name"] for t in tags}
        assert names == {"ml", "python"}

    def test_remove_video_tag(self, store: CollectionStore, db: HistoryDB) -> None:
        vid = _insert_video(db, 1)
        t = store.create_tag("python")
        store.add_video_tag(vid, t["id"])
        store.remove_video_tag(vid, t["id"])
        assert len(store.get_video_tags(vid)) == 0
