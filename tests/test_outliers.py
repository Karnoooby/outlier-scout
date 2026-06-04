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
