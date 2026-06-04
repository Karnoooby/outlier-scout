from __future__ import annotations

from datetime import datetime
from typing import List

from googleapiclient.discovery import build

from outlier_scout.models import Video
from outlier_scout.outliers import parse_duration


class YouTubeClient:
    """Thin wrapper over the YouTube Data API v3."""

    def __init__(self, api_key: str):
        self._yt = build("youtube", "v3", developerKey=api_key)

    def get_channel(self, handle: str) -> dict:
        part = "contentDetails,snippet,statistics"
        if handle.startswith("@"):
            resp = self._yt.channels().list(
                part=part, forHandle=handle.lstrip("@"),
            ).execute()
        else:
            resp = self._yt.channels().list(part=part, id=handle).execute()
        items = resp.get("items", [])
        if not items:
            raise LookupError(f"Channel not found: {handle}")
        it = items[0]
        stats = it.get("statistics", {})
        # subscriber_count is None when the channel hides its subscriber count.
        if stats.get("hiddenSubscriberCount") or "subscriberCount" not in stats:
            subscriber_count = None
        else:
            subscriber_count = int(stats["subscriberCount"])
        return {
            "channel_id": it["id"],
            "title": it["snippet"]["title"],
            "uploads_playlist_id":
                it["contentDetails"]["relatedPlaylists"]["uploads"],
            "subscriber_count": subscriber_count,
        }

    def get_recent_videos(self, uploads_playlist_id: str,
                          max_items: int) -> List[Video]:
        ids: List[str] = []
        page = None
        while len(ids) < max_items:
            resp = self._yt.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=min(50, max_items - len(ids)),
                pageToken=page,
            ).execute()
            ids += [i["contentDetails"]["videoId"] for i in resp.get("items", [])]
            page = resp.get("nextPageToken")
            if not page:
                break
        return self.get_videos(ids)

    def get_videos(self, video_ids: List[str]) -> List[Video]:
        out: List[Video] = []
        for start in range(0, len(video_ids), 50):
            batch = video_ids[start:start + 50]
            resp = self._yt.videos().list(
                part="statistics,contentDetails,snippet",
                id=",".join(batch),
            ).execute()
            for it in resp.get("items", []):
                snip, stats, cd = it["snippet"], it.get("statistics", {}), it["contentDetails"]
                published = datetime.fromisoformat(
                    snip["publishedAt"].replace("Z", "+00:00")
                )
                thumbs = snip.get("thumbnails", {})
                thumb = (thumbs.get("high") or thumbs.get("default") or {}).get("url", "")
                out.append(Video(
                    id=it["id"],
                    title=snip["title"],
                    channel_id=snip["channelId"],
                    channel_title=snip["channelTitle"],
                    views=int(stats.get("viewCount", 0)),
                    published_at=published,
                    duration_s=parse_duration(cd["duration"]),
                    description=snip.get("description", ""),
                    thumbnail_url=thumb,
                    url=f"https://www.youtube.com/watch?v={it['id']}",
                ))
        return out

    def search_videos(self, query: str, max_results: int,
                      published_after: str, relevance_language: str = "en") -> List[str]:
        """Recent, high-view video IDs for a query (RFC3339 published_after, e.g.
        '2026-05-28T00:00:00Z'). Returns video IDs in id.videoId."""
        resp = self._yt.search().list(
            part="snippet", q=query, type="video", order="viewCount",
            maxResults=min(50, max_results), publishedAfter=published_after,
            relevanceLanguage=relevance_language,
        ).execute()
        return [it["id"]["videoId"] for it in resp.get("items", [])]
