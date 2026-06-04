from datetime import datetime, timezone
from outlier_scout.report import render_digest
from outlier_scout.models import Video, Outlier, AnalyzedOutlier


def make_analyzed(mult, fmt, title):
    v = Video(id="v1", title=title, channel_id="c1", channel_title="Chan",
              views=4000, published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
              duration_s=300, description="d", thumbnail_url="http://t",
              url="http://yt/v1")
    o = Outlier(video=v, multiplier=mult, video_format=fmt,
                baseline_median=1000.0, age_days=2)
    return AnalyzedOutlier(outlier=o, description="desc",
                           why_outlier="why", niche_application="apply")


def test_render_digest_with_outliers():
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    d = render_digest([make_analyzed(4.0, "Long", "Big Video")], now)
    assert d.new_count == 1
    assert "Big Video" in d.html
    assert "4.0x" in d.html
    assert "apply" in d.markdown
    assert "2026-06-07" in d.subject


def test_render_digest_empty_week():
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    d = render_digest([], now)
    assert d.new_count == 0
    assert "no new outliers" in d.html.lower()
