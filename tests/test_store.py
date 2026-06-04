from datetime import datetime, timezone
from outlier_scout.store import Store


def test_unseen_video_is_not_reported(tmp_path):
    s = Store(str(tmp_path / "r.db"))
    assert s.is_reported("v1") is False


def test_mark_then_is_reported(tmp_path):
    s = Store(str(tmp_path / "r.db"))
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    s.mark_reported(["v1", "v2"], now)
    assert s.is_reported("v1") is True
    assert s.is_reported("v2") is True
    assert s.is_reported("v3") is False


def test_persists_across_instances(tmp_path):
    db = str(tmp_path / "r.db")
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    Store(db).mark_reported(["v1"], now)
    assert Store(db).is_reported("v1") is True


def test_mark_is_idempotent(tmp_path):
    s = Store(str(tmp_path / "r.db"))
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    s.mark_reported(["v1"], now)
    s.mark_reported(["v1"], now)  # must not raise
    assert s.is_reported("v1") is True
