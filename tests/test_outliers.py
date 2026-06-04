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


def test_outlier_holds_fields():
    v = make_video()
    o = Outlier(video=v, multiplier=3.2, video_format="Long",
                baseline_median=1000.0, age_days=2)
    assert o.multiplier == 3.2
    assert o.video_format == "Long"


from outlier_scout.outliers import (
    parse_duration, classify_format, median, score_channel,
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


def test_score_channel_flags_outliers_per_format():
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    longs = [make_video(id=f"L{i}", duration_s=300, views=100) for i in range(5)]
    longs.append(make_video(id="HIT", duration_s=300, views=400))  # 4x median 100
    outliers = score_channel(longs, threshold=2.5, min_videos_per_format=5, now=now)
    ids = [o.video.id for o in outliers]
    assert ids == ["HIT"]
    assert outliers[0].multiplier == 4.0
    assert outliers[0].video_format == "Long"


def test_score_channel_skips_thin_format():
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    shorts = [make_video(id=f"S{i}", duration_s=30, views=100) for i in range(3)]
    shorts.append(make_video(id="S_HIT", duration_s=30, views=9999))
    outliers = score_channel(shorts, threshold=2.5, min_videos_per_format=5, now=now)
    assert outliers == []  # only 4 shorts < min 5, format skipped
