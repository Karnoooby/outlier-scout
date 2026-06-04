import textwrap
import pytest
from outlier_scout.config import load_config


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    """Stop load_config from reading the project's real .env during tests,
    so env-var assertions depend only on what each test sets."""
    monkeypatch.setattr("outlier_scout.config.load_dotenv", lambda *a, **k: None)


def write_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent("""
        seed_channels: ["@ChanA"]
        keywords: ["gaming psychology"]
        outlier_threshold: 2.5
        lookback_days: 14
        max_channels: 15
        min_videos_per_format: 5
        recipient_email: "me@example.com"
    """))
    return p


def test_load_config_reads_yaml_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    cfg = load_config(str(write_yaml(tmp_path)))
    assert cfg.seed_channels == ["@ChanA"]
    assert cfg.outlier_threshold == 2.5
    assert cfg.max_channels == 15
    assert cfg.youtube_api_key == "yt-key"
    assert cfg.anthropic_api_key == "an-key"


def test_load_config_missing_youtube_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
        load_config(str(write_yaml(tmp_path)))
