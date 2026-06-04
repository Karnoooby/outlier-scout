from datetime import datetime, timezone
from outlier_scout.models import Video, Outlier


def make_video(**kw):
    defaults = dict(
        id="v1", title="T", channel_id="c1", channel_title="Chan",
        views=1000, published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        duration_s=240, description="d", thumbnail_url="http://t/x.jpg",
        url="http://yt/v1",
    )
    defaults.update(kw)
    return Video(**defaults)


def test_video_holds_fields():
    v = make_video(views=5000)
    assert v.views == 5000
    assert v.id == "v1"


def test_outlier_holds_fields_with_niche():
    v = make_video()
    o = Outlier(video=v, multiplier=3.2, video_format="Long",
                baseline_median=1000.0, age_days=2,
                niche_label="gaming psychology", niche_type="core")
    assert o.multiplier == 3.2
    assert o.video_format == "Long"
    assert o.niche_label == "gaming psychology"
    assert o.niche_type == "core"


def test_outlier_niche_fields_default_empty():
    v = make_video()
    o = Outlier(video=v, multiplier=3.0, video_format="Short",
                baseline_median=500.0, age_days=1)
    assert o.niche_label == ""
    assert o.niche_type == ""


from outlier_scout.outliers import (
    parse_duration, classify_format, median, format_median,
)


def test_parse_duration_minutes_seconds():
    assert parse_duration("PT4M13S") == 253


def test_parse_duration_hours():
    assert parse_duration("PT1H2M3S") == 3723


def test_parse_duration_bad_input_is_zero():
    assert parse_duration("garbage") == 0


def test_classify_format_boundary():
    assert classify_format(180) == "Short"
    assert classify_format(181) == "Long"


def test_median_odd_and_even():
    assert median([1, 3, 2]) == 2
    assert median([1, 2, 3, 4]) == 2.5


def test_format_median_returns_median_for_format():
    vids = [make_video(id=f"L{i}", duration_s=300, views=v)
            for i, v in enumerate([100, 200, 300])]
    assert format_median(vids, "Long", min_videos=3) == 200


def test_format_median_none_when_too_few():
    vids = [make_video(id=f"L{i}", duration_s=300, views=100) for i in range(2)]
    assert format_median(vids, "Long", min_videos=3) is None


def test_format_median_only_counts_matching_format():
    vids = [
        make_video(id="s1", duration_s=30, views=10),
        make_video(id="s2", duration_s=30, views=20),
        make_video(id="s3", duration_s=30, views=30),
        make_video(id="L1", duration_s=300, views=9999),
    ]
    assert format_median(vids, "Short", min_videos=3) == 20
    assert format_median(vids, "Long", min_videos=3) is None  # only 1 long

