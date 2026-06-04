from __future__ import annotations

from typing import Dict, List

from outlier_scout.models import Video


class FakeYouTubeClient:
    """In-memory stand-in for YouTubeClient used in tests."""

    def __init__(self, channels: Dict[str, dict], videos: Dict[str, List[Video]],
                 search_results: Dict[str, List[str]] = None,
                 video_index: Dict[str, Video] = None):
        # channels: handle OR channel_id -> {"channel_id","title","uploads_playlist_id"}
        self._channels = channels
        # videos: uploads_playlist_id -> [Video, ...]  (used for baselines/anchor)
        self._videos = videos
        # search_results: query -> [video_id, ...]
        self._search = search_results or {}
        # video_index: video_id -> Video  (used by get_videos)
        self._video_index = video_index or {}

    def get_channel(self, handle: str) -> dict:
        return self._channels[handle]

    def get_recent_videos(self, uploads_playlist_id: str, max_items: int) -> List[Video]:
        return self._videos.get(uploads_playlist_id, [])[:max_items]

    def get_videos(self, video_ids: List[str]) -> List[Video]:
        return [self._video_index[v] for v in video_ids if v in self._video_index]

    def search_videos(self, query: str, max_results: int,
                      published_after: str, relevance_language: str = "en") -> List[str]:
        return self._search.get(query, [])[:max_results]
