from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from outlier_scout.hunt import hunt
from outlier_scout.models import Video
from tests.fakes import FakeYouTubeClient


NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


@dataclass
class Cfg:
    anchor_channel: str = "@me"
    report_window_days: int = 7
    lookback_days: int = 90
    max_videos_per_query: int = 8
    relevance_language: str = "en"
    outlier_threshold: float = 2.5
    outlier_ceiling: float = 80.0
    min_videos_per_format: int = 3


def vid(id, channel_id, views, dur=300, days_old=2):
    return Video(id=id, title=id, channel_id=channel_id, channel_title=channel_id,
                 views=views, published_at=NOW - timedelta(days=days_old),
                 duration_s=dur, description="", thumbnail_url="",
                 url=f"http://yt/{id}")


def baseline_videos(channel_id, median_views, n=5, dur=300):
    # n videos all at median_views so the channel's format median == median_views
    return [vid(f"{channel_id}_b{i}", channel_id, median_views, dur, days_old=40)
            for i in range(n)]


def build_client(candidate, base_median=1000, base_dur=300):
    """One discovered channel 'C' with a baseline; one search query 'q' that
    returns the candidate video id."""
    return FakeYouTubeClient(
        channels={
            "@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"},
            "C": {"channel_id": "C", "title": "C", "uploads_playlist_id": "UPc"},
        },
        videos={"UPc": baseline_videos("C", base_median, dur=base_dur)},
        search_results={"q": [candidate.id]},
        video_index={candidate.id: candidate},
    )


def niches(label="core niche", ntype="core", queries=("q",)):
    return [{"label": label, "type": ntype, "queries": list(queries)}]


def test_hunt_flags_video_above_threshold():
    cand = vid("HIT", "C", 4000)  # 4x the 1000 baseline
    client = build_client(cand)
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda vid_id: False)
    assert [o.video.id for o in out] == ["HIT"]
    assert out[0].multiplier == 4.0
    assert out[0].niche_label == "core niche"
    assert out[0].niche_type == "core"


def test_hunt_drops_below_threshold():
    client = build_client(vid("LOW", "C", 2000))  # 2x < 2.5
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_drops_above_ceiling():
    client = build_client(vid("LOTTERY", "C", 200000))  # 200x > 80 ceiling
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_drops_outside_report_window():
    client = build_client(vid("OLD", "C", 4000, days_old=30))  # > 7d window
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_skips_thin_format_baseline():
    # channel has only 2 long videos -> baseline None -> skip
    cand = vid("HIT", "C", 4000)
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"},
                  "C": {"channel_id": "C", "title": "C", "uploads_playlist_id": "UPc"}},
        videos={"UPc": baseline_videos("C", 1000, n=2)},
        search_results={"q": ["HIT"]},
        video_index={"HIT": cand},
    )
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_excludes_anchor_channel():
    cand = vid("MINE", "anchor", 4000)
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"}},
        videos={"UPme": baseline_videos("anchor", 1000)},
        search_results={"q": ["MINE"]},
        video_index={"MINE": cand},
    )
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_filters_already_reported():
    client = build_client(vid("HIT", "C", 4000))
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda vid_id: vid_id == "HIT")
    assert out == []


def test_hunt_caches_channel_baseline_across_queries():
    cand = vid("HIT", "C", 4000)
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"},
                  "C": {"channel_id": "C", "title": "C", "uploads_playlist_id": "UPc"}},
        videos={"UPc": baseline_videos("C", 1000)},
        search_results={"q1": ["HIT"], "q2": ["HIT"]},
        video_index={"HIT": cand},
    )
    calls = {"n": 0}
    orig = client.get_recent_videos
    def counting(pid, n):
        if pid == "UPc":
            calls["n"] += 1
        return orig(pid, n)
    client.get_recent_videos = counting
    out = hunt(client, niches(queries=("q1", "q2")), Cfg(), NOW, is_reported=lambda v: False)
    assert [o.video.id for o in out] == ["HIT"]   # seen-video dedup keeps it once
    assert calls["n"] == 1                          # baseline fetched once (cached)
