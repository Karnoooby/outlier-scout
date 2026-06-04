from __future__ import annotations

from outlier_scout.outliers import classify_format


def build_anchor_profile(client, handle: str, count: int) -> dict:
    """The anchor channel's most recent `count` uploads, as a JSON-friendly dict
    the agent reads to derive the niche."""
    channel = client.get_channel(handle)
    videos = client.get_recent_videos(channel["uploads_playlist_id"], count)
    return {
        "channel": channel["title"],
        "videos": [
            {
                "title": v.title,
                "format": classify_format(v.duration_s),
                "views": v.views,
                "description": (v.description or "")[:500],
            }
            for v in videos
        ],
    }
