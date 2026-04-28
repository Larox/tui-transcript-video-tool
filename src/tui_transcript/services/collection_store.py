"""High-level service for managing collections, tags, and search."""

from __future__ import annotations

from tui_transcript.models import COLLECTION_TYPES
from tui_transcript.services.history import HistoryDB


class CollectionStore:
    """Wraps HistoryDB collection/tag/search operations with validation."""

    def __init__(self, db: HistoryDB | None = None) -> None:
        self._db = db or HistoryDB()
        self._owns_db = db is None

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def list_collections(self) -> list[dict]:
        return self._db.list_collections()

    def get_collection(self, collection_id: int) -> dict:
        c = self._db.get_collection(collection_id)
        if c is None:
            raise KeyError(f"Collection {collection_id} not found")
        return c

    def get_collection_with_items(self, collection_id: int) -> dict:
        c = self.get_collection(collection_id)
        c["items"] = self._db.list_collection_items(collection_id)
        # Attach tags to each item
        for item in c["items"]:
            item["tags"] = self._db.get_video_tags(item["id"])
        return c

    def create_collection(
        self,
        name: str,
        collection_type: str = "other",
        description: str = "",
    ) -> dict:
        if not name.strip():
            raise ValueError("Collection name cannot be empty")
        if collection_type not in COLLECTION_TYPES:
            raise ValueError(
                f"Invalid collection type: {collection_type}. "
                f"Must be one of: {', '.join(COLLECTION_TYPES)}"
            )
        return self._db.create_collection(name.strip(), collection_type, description)

    def update_collection(
        self,
        collection_id: int,
        *,
        name: str | None = None,
        collection_type: str | None = None,
        description: str | None = None,
    ) -> dict:
        if collection_type is not None and collection_type not in COLLECTION_TYPES:
            raise ValueError(f"Invalid collection type: {collection_type}")
        result = self._db.update_collection(
            collection_id,
            name=name,
            collection_type=collection_type,
            description=description,
        )
        if result is None:
            raise KeyError(f"Collection {collection_id} not found")
        return result

    def delete_collection(self, collection_id: int) -> None:
        if not self._db.delete_collection(collection_id):
            raise KeyError(f"Collection {collection_id} not found")

    def add_item(self, collection_id: int, video_id: int) -> None:
        self.get_collection(collection_id)  # verify exists
        self._db.add_collection_item(collection_id, video_id)

    def add_items(self, collection_id: int, video_ids: list[int]) -> None:
        self.get_collection(collection_id)
        for vid in video_ids:
            self._db.add_collection_item(collection_id, vid)

    def remove_item(self, collection_id: int, video_id: int) -> None:
        if not self._db.remove_collection_item(collection_id, video_id):
            raise KeyError(
                f"Video {video_id} not in collection {collection_id}"
            )

    def reorder_items(self, collection_id: int, video_ids: list[int]) -> None:
        self.get_collection(collection_id)
        self._db.reorder_collection_items(collection_id, video_ids)

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def list_tags(self) -> list[dict]:
        return self._db.list_tags()

    def create_tag(self, name: str, color: str = "#6b7280") -> dict:
        if not name.strip():
            raise ValueError("Tag name cannot be empty")
        return self._db.create_tag(name.strip().lower(), color)

    def delete_tag(self, tag_id: int) -> None:
        if not self._db.delete_tag(tag_id):
            raise KeyError(f"Tag {tag_id} not found")

    def add_video_tag(self, video_id: int, tag_id: int) -> None:
        self._db.add_video_tag(video_id, tag_id)

    def remove_video_tag(self, video_id: int, tag_id: int) -> None:
        if not self._db.remove_video_tag(video_id, tag_id):
            raise KeyError(f"Tag {tag_id} not on video {video_id}")

    def get_video_tags(self, video_id: int) -> list[dict]:
        return self._db.get_video_tags(video_id)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def index_transcript(
        self, video_id: int, output_title: str, source_path: str, content: str
    ) -> None:
        self._db.index_transcript(video_id, output_title, source_path, content)

    def search(
        self,
        query: str,
        *,
        collection_id: int | None = None,
        tag_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return self._db.search_transcripts(
            query, collection_id=collection_id, tag_name=tag_name, limit=limit
        )

    # ------------------------------------------------------------------
    # Videos
    # ------------------------------------------------------------------

    def list_videos(self) -> list[dict]:
        return self._db.list_videos()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._owns_db:
            self._db.close()
