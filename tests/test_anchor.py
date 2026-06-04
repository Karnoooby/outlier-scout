from datetime import datetime, timezone
from outlier_scout.anchor import build_anchor_profile
from outlier_scout.models import Video
from tests.fakes import FakeYouTubeClient


def vid(id, dur, views, desc=""):
    return Video(id=id, title=id, channel_id="anchor", channel_title="Me",
                 views=views, published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                 duration_s=dur, description=desc, thumbnail_url="", url=f"http://yt/{id}")


def test_build_anchor_profile_returns_recent_videos():
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me",
                          "uploads_playlist_id": "UP"}},
        videos={"UP": [vid("a", 30, 100, "short desc"), vid("b", 300, 50)]},
    )
    profile = build_anchor_profile(client, "@me", count=12)
    assert profile["channel"] == "Me"
    assert [v["format"] for v in profile["videos"]] == ["Short", "Long"]
    assert profile["videos"][0]["title"] == "a"
    assert profile["videos"][0]["views"] == 100


def test_build_anchor_profile_respects_count():
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me",
                          "uploads_playlist_id": "UP"}},
        videos={"UP": [vid(str(i), 300, i) for i in range(20)]},
    )
    profile = build_anchor_profile(client, "@me", count=5)
    assert len(profile["videos"]) == 5
