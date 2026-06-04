from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from outlier_scout.models import Video


class FakeYouTubeClient:
    """In-memory stand-in for YouTubeClient used in tests."""

    def __init__(self, channels: Dict[str, dict], videos: Dict[str, List[Video]],
                 search_results: Dict[str, List[str]] = None):
        # channels: handle -> {"channel_id","title","uploads_playlist_id"}
        self._channels = channels
        # videos: uploads_playlist_id -> [Video, ...]
        self._videos = videos
        # search_results: query -> [handle, ...]
        self._search = search_results or {}

    def get_channel(self, handle: str) -> dict:
        return self._channels[handle]

    def get_recent_videos(self, uploads_playlist_id: str, max_items: int) -> List[Video]:
        return self._videos.get(uploads_playlist_id, [])[:max_items]

    def search_channels(self, query: str, max_results: int) -> List[str]:
        return self._search.get(query, [])[:max_results]
