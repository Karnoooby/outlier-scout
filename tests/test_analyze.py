import json
from datetime import datetime, timezone
from outlier_scout.analyze import analyze_outlier, NICHE
from outlier_scout.models import Video, Outlier
from tests.fakes import FakeAnthropic


def make_outlier():
    v = Video(id="v1", title="Why gamers rage", channel_id="c1",
              channel_title="Chan", views=4000,
              published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
              duration_s=300, description="d", thumbnail_url="http://t",
              url="http://yt/v1")
    return Outlier(video=v, multiplier=4.0, video_format="Long",
                   baseline_median=1000.0, age_days=2)


def test_analyze_parses_json_response():
    payload = json.dumps({
        "description": "desc", "why_outlier": "hook",
        "niche_application": "apply",
    })
    client = FakeAnthropic([payload])
    result = analyze_outlier(client, make_outlier(), niche=NICHE)
    assert result.description == "desc"
    assert result.why_outlier == "hook"
    assert result.niche_application == "apply"


def test_analyze_retries_once_then_falls_back_to_metadata():
    client = FakeAnthropic([RuntimeError("boom"), RuntimeError("boom2")])
    result = analyze_outlier(client, make_outlier(), niche=NICHE)
    assert client.messages.calls == 2
    assert "unavailable" in result.why_outlier.lower()
    assert result.description == "Why gamers rage"


def test_analyze_parses_json_with_trailing_prose():
    payload = ('{"description": "d", "why_outlier": "w", '
               '"niche_application": "a"}\n\nNote: extra {text} here.')
    client = FakeAnthropic([payload])
    result = analyze_outlier(client, make_outlier(), niche=NICHE)
    assert result.description == "d"
    assert result.niche_application == "a"


def test_analyze_falls_back_on_null_field():
    import json as _json
    payload = _json.dumps({"description": None, "why_outlier": "w",
                           "niche_application": "a"})
    client = FakeAnthropic([payload, payload])
    result = analyze_outlier(client, make_outlier(), niche=NICHE)
    assert client.messages.calls == 2
    assert "unavailable" in result.why_outlier.lower()
