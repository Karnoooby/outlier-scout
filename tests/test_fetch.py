from datetime import datetime, timezone, timedelta
from outlier_scout.fetch import fetch_channel_videos
from outlier_scout.models import Video
from tests.fakes import FakeYouTubeClient


def vid(id, days_old, now):
    return Video(
        id=id, title=id, channel_id="c1", channel_title="Chan",
        views=100, published_at=now - timedelta(days=days_old),
        duration_s=300, description="", thumbnail_url="", url=f"http://yt/{id}",
    )


def test_fetch_filters_by_lookback_window():
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    playlist = "UP1"
    videos = [vid("recent", 3, now), vid("old", 40, now)]
    client = FakeYouTubeClient(
        channels={"@Chan": {"channel_id": "c1", "title": "Chan",
                            "uploads_playlist_id": playlist}},
        videos={playlist: videos},
    )
    out = fetch_channel_videos(client, "@Chan", lookback_days=14, now=now)
    ids = [v.id for v in out]
    assert ids == ["recent"]
