from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from outlier_scout.models import Video

# How many recent uploads to pull per channel before date-filtering.
MAX_ITEMS_PER_CHANNEL = 50


def fetch_channel_videos(client, handle: str, lookback_days: int,
                         now: datetime) -> List[Video]:
    """Resolve a channel handle and return its videos within the lookback window."""
    channel = client.get_channel(handle)
    videos = client.get_recent_videos(
        channel["uploads_playlist_id"], MAX_ITEMS_PER_CHANNEL
    )
    cutoff = now - timedelta(days=lookback_days)
    return [v for v in videos if v.published_at >= cutoff]
