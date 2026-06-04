import textwrap
import pytest
from outlier_scout.config import load_config


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    monkeypatch.setattr("outlier_scout.config.load_dotenv", lambda *a, **k: None)


def write_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent("""
        anchor_channel: "@karnooby"
        anchor_video_count: 12
        adjacent_hints: ["psychology"]
        report_window_days: 7
        lookback_days: 90
        max_videos_per_query: 8
        relevance_language: "en"
        outlier_threshold: 2.5
        outlier_ceiling: 80
        min_videos_per_format: 3
        max_subscribers: 250000
        min_subscribers: 0
        recipient_email: "me@example.com"
    """))
    return p


def test_load_config_reads_yaml_and_youtube_key(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    cfg = load_config(str(write_yaml(tmp_path)))
    assert cfg.anchor_channel == "@karnooby"
    assert cfg.anchor_video_count == 12
    assert cfg.adjacent_hints == ["psychology"]
    assert cfg.report_window_days == 7
    assert cfg.outlier_ceiling == 80
    assert cfg.relevance_language == "en"
    assert cfg.max_subscribers == 250000
    assert cfg.min_subscribers == 0
    assert cfg.youtube_api_key == "yt-key"


def test_load_config_missing_youtube_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
        load_config(str(write_yaml(tmp_path)))


def test_load_config_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    p = tmp_path / "config.yaml"
    p.write_text('anchor_channel: "@x"\nrecipient_email: "me@example.com"\n')
    cfg = load_config(str(p))
    assert cfg.anchor_video_count == 12
    assert cfg.report_window_days == 7
    assert cfg.outlier_threshold == 2.5
    assert cfg.outlier_ceiling == 80
    assert cfg.min_videos_per_format == 3
    assert cfg.max_subscribers == 250000
    assert cfg.min_subscribers == 0
    assert cfg.adjacent_hints == []
