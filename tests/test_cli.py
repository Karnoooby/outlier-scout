from datetime import datetime, timezone, timedelta
from outlier_scout.cli import normalize_niche_queries, outliers_to_json
from outlier_scout.models import Video, Outlier


def test_normalize_niche_queries_flattens_core_and_adjacent():
    agent = {
        "core": {"label": "gaming psychology", "queries": ["a", "b"]},
        "adjacent": [
            {"label": "dopamine", "queries": ["c"]},
            {"label": "discipline", "queries": ["d", "e"]},
        ],
    }
    out = normalize_niche_queries(agent)
    assert out[0] == {"label": "gaming psychology", "type": "core", "queries": ["a", "b"]}
    assert out[1] == {"label": "dopamine", "type": "adjacent", "queries": ["c"]}
    assert out[2]["type"] == "adjacent"
    assert out[2]["queries"] == ["d", "e"]


def test_outliers_to_json_serializes_fields():
    now = datetime(2026, 6, 4, tzinfo=timezone.utc)
    v = Video(id="v1", title="T", channel_id="C", channel_title="Chan",
              views=4000, published_at=now - timedelta(days=2), duration_s=300,
              description="d" * 1000, thumbnail_url="http://t", url="http://yt/v1")
    o = Outlier(video=v, multiplier=4.0, video_format="Long",
                baseline_median=1000.0, age_days=2,
                niche_label="gaming psychology", niche_type="core")
    rows = outliers_to_json([o])
    assert rows[0]["id"] == "v1"
    assert rows[0]["multiplier"] == 4.0
    assert rows[0]["niche_label"] == "gaming psychology"
    assert rows[0]["niche_type"] == "core"
    assert rows[0]["url"] == "http://yt/v1"
    assert rows[0]["channel_title"] == "Chan"
    assert len(rows[0]["description"]) <= 500
