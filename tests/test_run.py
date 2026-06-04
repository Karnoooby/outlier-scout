import json
from datetime import datetime, timezone, timedelta
from outlier_scout.run import run_pipeline
from outlier_scout.config import Config
from outlier_scout.models import Video
from outlier_scout.store import Store
from tests.fakes import FakeYouTubeClient, FakeAnthropic


def cfg(**kw):
    base = dict(
        seed_channels=["@Chan"], keywords=[], outlier_threshold=2.5,
        lookback_days=14, max_channels=15, min_videos_per_format=5,
        recipient_email="me@example.com", youtube_api_key="x",
        anthropic_api_key="y",
    )
    base.update(kw)
    return Config(**base)


def build_clients(now):
    longs = []
    for i in range(5):
        longs.append(Video(id=f"L{i}", title=f"L{i}", channel_id="c1",
            channel_title="Chan", views=100,
            published_at=now - timedelta(days=2), duration_s=300,
            description="d", thumbnail_url="http://t", url=f"http://yt/L{i}"))
    longs.append(Video(id="HIT", title="HIT", channel_id="c1",
        channel_title="Chan", views=400, published_at=now - timedelta(days=2),
        duration_s=300, description="d", thumbnail_url="http://t",
        url="http://yt/HIT"))
    yt = FakeYouTubeClient(
        channels={"@Chan": {"channel_id": "c1", "title": "Chan",
                           "uploads_playlist_id": "UP1"}},
        videos={"UP1": longs},
    )
    payload = json.dumps({"description": "d", "why_outlier": "w",
                          "niche_application": "a"})
    an = FakeAnthropic([payload])
    return yt, an


def test_run_pipeline_reports_new_outlier(tmp_path):
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    yt, an = build_clients(now)
    store = Store(str(tmp_path / "r.db"))
    digest = run_pipeline(cfg(), yt, an, store, now)
    assert digest.new_count == 1
    assert "HIT" in digest.html


def test_run_pipeline_dedups_second_run(tmp_path):
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    yt, an = build_clients(now)
    store = Store(str(tmp_path / "r.db"))
    run_pipeline(cfg(), yt, an, store, now)          # first run records HIT
    yt2, an2 = build_clients(now)
    digest = run_pipeline(cfg(), yt2, an2, store, now)  # second run: nothing new
    assert digest.new_count == 0


def test_run_pipeline_dedups_same_channel_from_seed_and_discovery(tmp_path):
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    yt, an = build_clients(now)
    # Add a discovery result ("UC1") that resolves to the SAME uploads playlist
    # as the seed "@Chan", i.e. the same underlying channel.
    yt._channels["UC1"] = {"channel_id": "c1", "title": "Chan",
                           "uploads_playlist_id": "UP1"}
    yt._search = {"kw": ["UC1"]}
    store = Store(str(tmp_path / "r.db"))
    cfg_both = cfg(keywords=["kw"])  # seed "@Chan" + discovered "UC1" => same channel
    digest = run_pipeline(cfg_both, yt, an, store, now)
    # The HIT outlier must appear exactly once despite two entry points.
    assert digest.new_count == 1
    assert an.messages.calls == 1  # analyzed once, not twice
