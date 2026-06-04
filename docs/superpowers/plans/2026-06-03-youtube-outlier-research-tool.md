# YouTube Outlier Research Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MVP that weekly discovers YouTube outlier videos, analyzes each with Claude for the owner's gaming+psychology niche, and produces an email digest of only-new outliers.

**Architecture:** A linear Python pipeline (`Config → Discover → Fetch → Detect → Dedup → Analyze → Report`) orchestrated by `run.py`. Determinism lives in Python (quota, math, dedup); a single Claude stage does analysis (Approach A). `run.py` emits a digest payload; a scheduled Claude agent (Sun 08:00) runs it and sends the email via the Gmail integration.

**Tech Stack:** Python 3.9, `google-api-python-client`, `python-dotenv`, `PyYAML`, `anthropic` SDK, stdlib `sqlite3`, `pytest` (+`pytest` mocks via `unittest.mock`).

---

## File Structure

```
outlier_scout/
  __init__.py        # package marker
  models.py          # dataclasses: Video, Outlier, AnalyzedOutlier, Digest
  outliers.py        # duration parsing, median, per-channel scoring
  config.py          # Config dataclass + load_config()
  store.py           # SQLite dedup store
  youtube.py         # YouTubeClient: thin wrapper over googleapiclient
  fetch.py           # fetch_channel_videos() using a YouTubeClient
  discover.py        # discover_channels() using a YouTubeClient
  analyze.py         # analyze_outlier() via Anthropic SDK (prompt caching + retry)
  report.py          # render_digest() -> Digest(subject, html, markdown)
  run.py             # orchestrate the pipeline; CLI entrypoint
tests/
  __init__.py
  fakes.py           # FakeYouTubeClient, FakeAnthropic for tests
  test_outliers.py
  test_config.py
  test_store.py
  test_fetch.py
  test_discover.py
  test_analyze.py
  test_report.py
  test_run.py
config.yaml          # tunable, non-secret parameters
requirements.txt     # pinned deps
pytest.ini           # pytest config
```

The existing root `outliers.py` script is superseded by `outlier_scout/outliers.py` and removed in the final task.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `outlier_scout/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Write `requirements.txt`**

```
google-api-python-client==2.197.0
python-dotenv==1.2.1
PyYAML==6.0.2
anthropic==0.69.0
pytest==8.3.4
```

- [ ] **Step 2: Install into the existing venv**

Run: `./venv/bin/pip install -r requirements.txt`
Expected: all packages install (google-api-python-client and python-dotenv already satisfied).

- [ ] **Step 3: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
filterwarnings =
    ignore::FutureWarning
```

- [ ] **Step 4: Create empty package markers**

Create `outlier_scout/__init__.py` containing:

```python
"""Outlier Scout: weekly YouTube outlier research pipeline."""
```

Create `tests/__init__.py` as an empty file.

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `./venv/bin/python -m pytest`
Expected: "no tests ran" exit 5, no import errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini outlier_scout/__init__.py tests/__init__.py
git commit -m "chore: scaffold outlier_scout package and test harness"
```

---

### Task 2: Data models

**Files:**
- Create: `outlier_scout/models.py`
- Test: `tests/test_outliers.py` (shared with Task 3; create here)

- [ ] **Step 1: Write the failing test**

Create `tests/test_outliers.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_outliers.py -v`
Expected: FAIL with "No module named 'outlier_scout.models'".

- [ ] **Step 3: Write `outlier_scout/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class Video:
    id: str
    title: str
    channel_id: str
    channel_title: str
    views: int
    published_at: datetime
    duration_s: int
    description: str
    thumbnail_url: str
    url: str


@dataclass
class Outlier:
    video: Video
    multiplier: float
    video_format: str          # "Short" or "Long"
    baseline_median: float
    age_days: int


@dataclass
class AnalyzedOutlier:
    outlier: Outlier
    description: str
    why_outlier: str
    niche_application: str


@dataclass
class Digest:
    subject: str
    html: str
    markdown: str
    new_count: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_outliers.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add outlier_scout/models.py tests/test_outliers.py
git commit -m "feat: add data models for videos and outliers"
```

---

### Task 3: Outlier scoring (the math)

**Files:**
- Create: `outlier_scout/outliers.py`
- Test: `tests/test_outliers.py` (append)

- [ ] **Step 1: Append failing tests to `tests/test_outliers.py`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/test_outliers.py -v`
Expected: FAIL with "No module named 'outlier_scout.outliers'".

- [ ] **Step 3: Write `outlier_scout/outliers.py`**

```python
from __future__ import annotations

import re
import statistics
from datetime import datetime
from typing import List

from outlier_scout.models import Video, Outlier

SHORTS_THRESHOLD_S = 180
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_duration(iso: str) -> int:
    """ISO 8601 duration (e.g. PT4M13S) -> total seconds. 0 on bad input."""
    m = _DURATION_RE.fullmatch(iso or "")
    if not m:
        return 0
    h, mi, s = (int(g or 0) for g in m.groups())
    return h * 3600 + mi * 60 + s


def classify_format(duration_s: int) -> str:
    return "Short" if duration_s <= SHORTS_THRESHOLD_S else "Long"


def median(values: List[float]) -> float:
    return statistics.median(values)


def score_channel(
    videos: List[Video],
    threshold: float,
    min_videos_per_format: int,
    now: datetime,
) -> List[Outlier]:
    """Score each video against its own channel's per-format median.

    A format with fewer than `min_videos_per_format` videos is skipped
    (unreliable baseline). Returns outliers with multiplier >= threshold,
    sorted by multiplier descending.
    """
    groups = {"Short": [], "Long": []}
    for v in videos:
        groups[classify_format(v.duration_s)].append(v)

    outliers: List[Outlier] = []
    for fmt, group in groups.items():
        if len(group) < min_videos_per_format:
            continue
        base = median([v.views for v in group])
        if base <= 0:
            continue
        for v in group:
            mult = v.views / base
            if mult >= threshold:
                outliers.append(Outlier(
                    video=v,
                    multiplier=round(mult, 2),
                    video_format=fmt,
                    baseline_median=base,
                    age_days=(now - v.published_at).days,
                ))
    outliers.sort(key=lambda o: o.multiplier, reverse=True)
    return outliers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_outliers.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add outlier_scout/outliers.py tests/test_outliers.py
git commit -m "feat: per-channel outlier scoring with format-aware baselines"
```

---

### Task 4: Configuration loading

**Files:**
- Create: `outlier_scout/config.py`, `config.yaml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import textwrap
import pytest
from outlier_scout.config import load_config


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL with "No module named 'outlier_scout.config'".

- [ ] **Step 3: Write `outlier_scout/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    seed_channels: List[str]
    keywords: List[str]
    outlier_threshold: float
    lookback_days: int
    max_channels: int
    min_videos_per_format: int
    recipient_email: str
    youtube_api_key: str
    anthropic_api_key: str


def load_config(path: str) -> Config:
    load_dotenv()
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    if not youtube_api_key:
        raise ValueError("YOUTUBE_API_KEY not found in environment (.env)")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment (.env)")

    return Config(
        seed_channels=data.get("seed_channels", []),
        keywords=data.get("keywords", []),
        outlier_threshold=float(data.get("outlier_threshold", 2.5)),
        lookback_days=int(data.get("lookback_days", 14)),
        max_channels=int(data.get("max_channels", 15)),
        min_videos_per_format=int(data.get("min_videos_per_format", 5)),
        recipient_email=data["recipient_email"],
        youtube_api_key=youtube_api_key,
        anthropic_api_key=anthropic_api_key,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Write `config.yaml`** (committed, no secrets)

```yaml
# Channels you already follow / compete with (handles, include the @).
seed_channels: []

# Discovery search terms.
keywords:
  - "gaming psychology"
  - "psychology of gaming"
  - "video game addiction"

outlier_threshold: 2.5     # multiplier vs the channel's own format median
lookback_days: 14          # only consider videos published in the last N days
max_channels: 15           # tight MVP cap on channels scanned per run
min_videos_per_format: 5   # skip a format with fewer recent videos
recipient_email: "f.karnib1996@gmail.com"
```

- [ ] **Step 6: Add ANTHROPIC_API_KEY to `.env.example`**

Modify `.env.example` to read:

```
YOUTUBE_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

- [ ] **Step 7: Commit**

```bash
git add outlier_scout/config.py config.yaml tests/test_config.py .env.example
git commit -m "feat: config loading from yaml + env"
```

---

### Task 5: Dedup store (SQLite)

**Files:**
- Create: `outlier_scout/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_store.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_store.py -v`
Expected: FAIL with "No module named 'outlier_scout.store'".

- [ ] **Step 3: Write `outlier_scout/store.py`**

```python
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import List


class Store:
    """Remembers which video IDs have already been emailed."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS reported ("
            "  video_id TEXT PRIMARY KEY,"
            "  first_reported TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def is_reported(self, video_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM reported WHERE video_id = ?", (video_id,)
        )
        return cur.fetchone() is not None

    def mark_reported(self, video_ids: List[str], when: datetime) -> None:
        self._conn.executemany(
            "INSERT OR IGNORE INTO reported (video_id, first_reported) "
            "VALUES (?, ?)",
            [(vid, when.isoformat()) for vid in video_ids],
        )
        self._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_store.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Add the data dir to `.gitignore`**

Append to `.gitignore`:

```
data/
```

- [ ] **Step 6: Commit**

```bash
git add outlier_scout/store.py tests/test_store.py .gitignore
git commit -m "feat: sqlite dedup store for reported videos"
```

---

### Task 6: YouTube client + fetch

**Files:**
- Create: `outlier_scout/youtube.py`, `outlier_scout/fetch.py`, `tests/fakes.py`
- Test: `tests/test_fetch.py`

- [ ] **Step 1: Write the fake client in `tests/fakes.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from outlier_scout.models import Video


class FakeYouTubeClient:
    """In-memory stand-in for YouTubeClient used in tests."""

    def __init__(self, channels: Dict[str, dict], videos: Dict[str, List[Video]],
                 search_results: Dict[str, List[str]] = None):
        # channels: handle -> {"channel_id","title","uploads_playlist_id"}
        self._channels = channels
        # videos: uploads_playlist_id -> [Video, ...]
        self._videos = videos
        # search_results: query -> [handle, ...]
        self._search = search_results or {}

    def get_channel(self, handle: str) -> dict:
        return self._channels[handle]

    def get_recent_videos(self, uploads_playlist_id: str, max_items: int) -> List[Video]:
        return self._videos.get(uploads_playlist_id, [])[:max_items]

    def search_channels(self, query: str, max_results: int) -> List[str]:
        return self._search.get(query, [])[:max_results]
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_fetch.py`:

```python
from datetime import datetime, timezone, timedelta
from outlier_scout.fetch import fetch_channel_videos
from outlier_scout.models import Video
from tests.fakes import FakeYouTubeClient


def vid(id, days_old, now):
    return Video(
        id=id, title=id, channel_id="c1", channel_title="Chan",
        views=100, published_at=now - timedelta(days=days_old),
        duration_s=300, description="", thumbnail_url="", url=f"http://yt/{id}",
    )


def test_fetch_filters_by_lookback_window():
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    playlist = "UP1"
    videos = [vid("recent", 3, now), vid("old", 40, now)]
    client = FakeYouTubeClient(
        channels={"@Chan": {"channel_id": "c1", "title": "Chan",
                            "uploads_playlist_id": playlist}},
        videos={playlist: videos},
    )
    out = fetch_channel_videos(client, "@Chan", lookback_days=14, now=now)
    ids = [v.id for v in out]
    assert ids == ["recent"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_fetch.py -v`
Expected: FAIL with "No module named 'outlier_scout.fetch'".

- [ ] **Step 4: Write `outlier_scout/fetch.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from outlier_scout.models import Video

# How many recent uploads to pull per channel before date-filtering.
MAX_ITEMS_PER_CHANNEL = 50


def fetch_channel_videos(client, handle: str, lookback_days: int,
                         now: datetime) -> List[Video]:
    """Resolve a channel handle and return its videos within the lookback window."""
    channel = client.get_channel(handle)
    videos = client.get_recent_videos(
        channel["uploads_playlist_id"], MAX_ITEMS_PER_CHANNEL
    )
    cutoff = now - timedelta(days=lookback_days)
    return [v for v in videos if v.published_at >= cutoff]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/test_fetch.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Write the real `outlier_scout/youtube.py`** (thin wrapper; not unit-tested — exercised live)

```python
from __future__ import annotations

import re
from datetime import datetime
from typing import List

from googleapiclient.discovery import build

from outlier_scout.models import Video
from outlier_scout.outliers import parse_duration

_DUR = None  # placeholder to keep import list tidy


class YouTubeClient:
    """Thin wrapper over the YouTube Data API v3."""

    def __init__(self, api_key: str):
        self._yt = build("youtube", "v3", developerKey=api_key)

    def get_channel(self, handle: str) -> dict:
        resp = self._yt.channels().list(
            part="contentDetails,snippet",
            forHandle=handle.lstrip("@"),
        ).execute()
        items = resp.get("items", [])
        if not items:
            raise LookupError(f"Channel not found: {handle}")
        it = items[0]
        return {
            "channel_id": it["id"],
            "title": it["snippet"]["title"],
            "uploads_playlist_id":
                it["contentDetails"]["relatedPlaylists"]["uploads"],
        }

    def get_recent_videos(self, uploads_playlist_id: str,
                          max_items: int) -> List[Video]:
        ids: List[str] = []
        page = None
        while len(ids) < max_items:
            resp = self._yt.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=min(50, max_items - len(ids)),
                pageToken=page,
            ).execute()
            ids += [i["contentDetails"]["videoId"] for i in resp.get("items", [])]
            page = resp.get("nextPageToken")
            if not page:
                break
        return self._hydrate(ids)

    def _hydrate(self, video_ids: List[str]) -> List[Video]:
        out: List[Video] = []
        for start in range(0, len(video_ids), 50):
            batch = video_ids[start:start + 50]
            resp = self._yt.videos().list(
                part="statistics,contentDetails,snippet",
                id=",".join(batch),
            ).execute()
            for it in resp.get("items", []):
                snip, stats, cd = it["snippet"], it.get("statistics", {}), it["contentDetails"]
                published = datetime.fromisoformat(
                    snip["publishedAt"].replace("Z", "+00:00")
                )
                thumbs = snip.get("thumbnails", {})
                thumb = (thumbs.get("high") or thumbs.get("default") or {}).get("url", "")
                out.append(Video(
                    id=it["id"],
                    title=snip["title"],
                    channel_id=snip["channelId"],
                    channel_title=snip["channelTitle"],
                    views=int(stats.get("viewCount", 0)),
                    published_at=published,
                    duration_s=parse_duration(cd["duration"]),
                    description=snip.get("description", ""),
                    thumbnail_url=thumb,
                    url=f"https://www.youtube.com/watch?v={it['id']}",
                ))
        return out

    def search_channels(self, query: str, max_results: int) -> List[str]:
        resp = self._yt.search().list(
            part="snippet", q=query, type="channel",
            maxResults=min(50, max_results),
        ).execute()
        handles: List[str] = []
        for it in resp.get("items", []):
            handle = it["snippet"].get("customUrl") or it["snippet"]["channelId"]
            handles.append(handle)
        return handles
```

> Note: `search().list` returns channel IDs; `get_channel` accepts a handle *or* a bare channel ID via `forHandle` only for handles. For discovery we pass the channel ID through `get_channel` by ID — handled in Task 7 by resolving via the channels endpoint. To keep the MVP simple, `search_channels` returns channel IDs and Task 7's discovery resolves them through `get_channel`, which Task 7 extends to accept IDs. (See Task 7, Step 4.)

- [ ] **Step 7: Run the full suite (no regressions)**

Run: `./venv/bin/python -m pytest`
Expected: PASS (all prior tests still green).

- [ ] **Step 8: Commit**

```bash
git add outlier_scout/youtube.py outlier_scout/fetch.py tests/fakes.py tests/test_fetch.py
git commit -m "feat: youtube client wrapper and lookback-windowed fetch"
```

---

### Task 7: Channel discovery

**Files:**
- Create: `outlier_scout/discover.py`
- Modify: `outlier_scout/youtube.py` (let `get_channel` accept a channel ID)
- Test: `tests/test_discover.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_discover.py`:

```python
from outlier_scout.discover import discover_channels
from tests.fakes import FakeYouTubeClient


def test_discovery_merges_seeds_and_search_deduped_and_capped():
    client = FakeYouTubeClient(
        channels={}, videos={},
        search_results={"kw1": ["@A", "@B"], "kw2": ["@B", "@C", "@D"]},
    )
    result = discover_channels(
        client, keywords=["kw1", "kw2"], seed_channels=["@A", "@SEED"],
        max_channels=4,
    )
    # seeds first (order preserved), then new discovered, deduped, capped at 4
    assert result == ["@A", "@SEED", "@B", "@C"]


def test_discovery_respects_cap_with_only_seeds():
    client = FakeYouTubeClient(channels={}, videos={}, search_results={})
    result = discover_channels(
        client, keywords=[], seed_channels=["@A", "@B", "@C"], max_channels=2,
    )
    assert result == ["@A", "@B"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_discover.py -v`
Expected: FAIL with "No module named 'outlier_scout.discover'".

- [ ] **Step 3: Write `outlier_scout/discover.py`**

```python
from __future__ import annotations

from typing import List

# Channels to request per keyword before merging/capping.
RESULTS_PER_KEYWORD = 5


def discover_channels(client, keywords: List[str], seed_channels: List[str],
                      max_channels: int) -> List[str]:
    """Seed channels first, then keyword-discovered channels, deduped and capped."""
    ordered: List[str] = []
    seen = set()

    def add(handle: str):
        if handle not in seen:
            seen.add(handle)
            ordered.append(handle)

    for h in seed_channels:
        add(h)
    for kw in keywords:
        for h in client.search_channels(kw, RESULTS_PER_KEYWORD):
            add(h)

    return ordered[:max_channels]
```

- [ ] **Step 4: Make `get_channel` tolerate channel IDs in `outlier_scout/youtube.py`**

Replace the `get_channel` method body with:

```python
    def get_channel(self, handle: str) -> dict:
        if handle.startswith("@"):
            resp = self._yt.channels().list(
                part="contentDetails,snippet", forHandle=handle.lstrip("@"),
            ).execute()
        else:
            resp = self._yt.channels().list(
                part="contentDetails,snippet", id=handle,
            ).execute()
        items = resp.get("items", [])
        if not items:
            raise LookupError(f"Channel not found: {handle}")
        it = items[0]
        return {
            "channel_id": it["id"],
            "title": it["snippet"]["title"],
            "uploads_playlist_id":
                it["contentDetails"]["relatedPlaylists"]["uploads"],
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_discover.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add outlier_scout/discover.py outlier_scout/youtube.py tests/test_discover.py
git commit -m "feat: keyword + seed channel discovery"
```

---

### Task 8: Claude analysis stage

**Files:**
- Create: `outlier_scout/analyze.py`
- Modify: `tests/fakes.py` (add FakeAnthropic)
- Test: `tests/test_analyze.py`

- [ ] **Step 1: Add `FakeAnthropic` to `tests/fakes.py`**

Append:

```python
import json


class _FakeMessages:
    def __init__(self, scripted):
        self._scripted = list(scripted)  # list of str OR Exception
        self.calls = 0

    def create(self, **kwargs):
        item = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item

        class _Block:
            def __init__(self, text):
                self.text = text
        class _Resp:
            def __init__(self, text):
                self.content = [_Block(text)]
        return _Resp(item)


class FakeAnthropic:
    """Mimics anthropic.Anthropic with a scripted messages.create()."""

    def __init__(self, scripted):
        self.messages = _FakeMessages(scripted)
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_analyze.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_analyze.py -v`
Expected: FAIL with "No module named 'outlier_scout.analyze'".

- [ ] **Step 4: Write `outlier_scout/analyze.py`**

```python
from __future__ import annotations

import json
import re

from outlier_scout.models import Outlier, AnalyzedOutlier

MODEL = "claude-sonnet-4-6"

NICHE = (
    "The reader runs a small YouTube channel (~1,100 subscribers) making videos "
    "about gaming and psychology. They want to learn what makes outlier videos "
    "succeed and how to adapt those ideas to gaming + psychology content."
)

_SYSTEM = (
    "You analyze outlier YouTube videos for a content creator. "
    "Given a video that significantly outperformed its channel's typical views, "
    "explain why it likely succeeded and how the creator could apply the lesson "
    "to their niche. Respond ONLY with a JSON object with keys: "
    '"description" (1-2 sentences on what the video is), '
    '"why_outlier" (2-3 sentences on why it overperformed: hook, title, '
    'thumbnail, timing, emotion), '
    '"niche_application" (2-3 sentences applying the lesson to the creator).'
)


def _build_user_prompt(o: Outlier, niche: str) -> str:
    v = o.video
    return (
        f"Creator niche: {niche}\n\n"
        f"Video title: {v.title}\n"
        f"Channel: {v.channel_title}\n"
        f"Format: {o.video_format}\n"
        f"Views: {v.views:,}\n"
        f"Multiplier vs channel median: {o.multiplier}x\n"
        f"Age (days): {o.age_days}\n"
        f"Description: {v.description[:600]}\n"
    )


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in response")
    return json.loads(match.group(0))


def analyze_outlier(client, outlier: Outlier, niche: str) -> AnalyzedOutlier:
    """One Claude call per outlier. Retries once, then metadata-only fallback."""
    last_err = None
    for _ in range(2):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=600,
                system=[{
                    "type": "text", "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{
                    "role": "user",
                    "content": _build_user_prompt(outlier, niche),
                }],
            )
            data = _parse(resp.content[0].text)
            return AnalyzedOutlier(
                outlier=outlier,
                description=data["description"],
                why_outlier=data["why_outlier"],
                niche_application=data["niche_application"],
            )
        except Exception as e:  # noqa: BLE001 - degrade gracefully on any failure
            last_err = e
    return AnalyzedOutlier(
        outlier=outlier,
        description=outlier.video.title,
        why_outlier=f"Analysis unavailable ({last_err}).",
        niche_application="Review manually.",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_analyze.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add outlier_scout/analyze.py tests/fakes.py tests/test_analyze.py
git commit -m "feat: claude outlier analysis with retry and fallback"
```

---

### Task 9: Report rendering

**Files:**
- Create: `outlier_scout/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_report.py -v`
Expected: FAIL with "No module named 'outlier_scout.report'".

- [ ] **Step 3: Write `outlier_scout/report.py`**

```python
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import List

from outlier_scout.models import AnalyzedOutlier, Digest


def _entry_html(a: AnalyzedOutlier) -> str:
    o, v = a.outlier, a.outlier.video
    return (
        f'<div style="margin:0 0 24px;padding:16px;border:1px solid #eee;border-radius:8px">'
        f'<h3 style="margin:0 0 8px"><a href="{escape(v.url)}">{escape(v.title)}</a> '
        f'<span style="color:#c00">{o.multiplier}x</span></h3>'
        f'<p style="margin:0 0 8px;color:#555">{escape(v.channel_title)} &middot; '
        f'{v.views:,} views &middot; {o.age_days}d old &middot; {o.video_format}</p>'
        f'<img src="{escape(v.thumbnail_url)}" alt="" style="max-width:320px;border-radius:6px"><br>'
        f'<p><b>What:</b> {escape(a.description)}</p>'
        f'<p><b>Why it worked:</b> {escape(a.why_outlier)}</p>'
        f'<p><b>Apply to your niche:</b> {escape(a.niche_application)}</p>'
        f'</div>'
    )


def _entry_md(a: AnalyzedOutlier) -> str:
    o, v = a.outlier, a.outlier.video
    return (
        f"### [{v.title}]({v.url}) — {o.multiplier}x\n"
        f"{v.channel_title} · {v.views:,} views · {o.age_days}d · {o.video_format}\n\n"
        f"- **What:** {a.description}\n"
        f"- **Why it worked:** {a.why_outlier}\n"
        f"- **Apply to your niche:** {a.niche_application}\n"
    )


def render_digest(analyzed: List[AnalyzedOutlier], now: datetime) -> Digest:
    date = now.strftime("%Y-%m-%d")
    ordered = sorted(analyzed, key=lambda a: a.outlier.multiplier, reverse=True)

    if not ordered:
        subject = f"Outlier Scout — no new outliers ({date})"
        html = "<p>No new outliers this week. The scout ran successfully.</p>"
        markdown = "No new outliers this week. The scout ran successfully.\n"
        return Digest(subject=subject, html=html, markdown=markdown, new_count=0)

    subject = f"Outlier Scout — {len(ordered)} new outlier(s) ({date})"
    html = (
        f"<h2>Outlier Scout digest — {date}</h2>"
        + "".join(_entry_html(a) for a in ordered)
    )
    markdown = (
        f"# Outlier Scout digest — {date}\n\n"
        + "\n".join(_entry_md(a) for a in ordered)
    )
    return Digest(subject=subject, html=html, markdown=markdown,
                  new_count=len(ordered))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_report.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add outlier_scout/report.py tests/test_report.py
git commit -m "feat: html + markdown digest rendering"
```

---

### Task 10: Pipeline orchestration

**Files:**
- Create: `outlier_scout/run.py`
- Test: `tests/test_run.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_run.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/test_run.py -v`
Expected: FAIL with "No module named 'outlier_scout.run'".

- [ ] **Step 3: Write `outlier_scout/run.py`**

```python
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import List

from outlier_scout.config import Config, load_config
from outlier_scout.discover import discover_channels
from outlier_scout.fetch import fetch_channel_videos
from outlier_scout.outliers import score_channel
from outlier_scout.models import Outlier, AnalyzedOutlier, Digest
from outlier_scout.analyze import analyze_outlier, NICHE
from outlier_scout.report import render_digest
from outlier_scout.store import Store

DB_PATH = "data/reported.db"
DIGEST_PATH = "data/latest_digest.json"


def run_pipeline(config: Config, youtube_client, anthropic_client,
                 store: Store, now: datetime) -> Digest:
    channels = discover_channels(
        youtube_client, config.keywords, config.seed_channels,
        config.max_channels,
    )

    all_outliers: List[Outlier] = []
    for handle in channels:
        try:
            videos = fetch_channel_videos(
                youtube_client, handle, config.lookback_days, now,
            )
        except LookupError:
            continue  # channel not found / no uploads; skip gracefully
        all_outliers += score_channel(
            videos, config.outlier_threshold,
            config.min_videos_per_format, now,
        )

    new = [o for o in all_outliers if not store.is_reported(o.video.id)]

    analyzed: List[AnalyzedOutlier] = [
        analyze_outlier(anthropic_client, o, NICHE) for o in new
    ]

    digest = render_digest(analyzed, now)
    store.mark_reported([o.video.id for o in new], now)
    return digest


def main() -> None:
    import anthropic
    from outlier_scout.youtube import YouTubeClient

    config = load_config("config.yaml")
    now = datetime.now(timezone.utc)
    store = Store(DB_PATH)
    youtube_client = YouTubeClient(config.youtube_api_key)
    anthropic_client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    digest = run_pipeline(config, youtube_client, anthropic_client, store, now)

    os.makedirs("data", exist_ok=True)
    envelope = {
        "to": config.recipient_email,
        "subject": digest.subject,
        "html": digest.html,
        "markdown": digest.markdown,
        "new_count": digest.new_count,
    }
    with open(DIGEST_PATH, "w") as f:
        json.dump(envelope, f, indent=2)

    # The scheduled Claude agent reads this JSON from stdout and sends the email.
    json.dump(envelope, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/test_run.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `./venv/bin/python -m pytest`
Expected: PASS (all tests across all files).

- [ ] **Step 6: Commit**

```bash
git add outlier_scout/run.py tests/test_run.py
git commit -m "feat: orchestrate full outlier pipeline with dedup"
```

---

### Task 11: Scheduling + email delivery (scheduled Claude agent)

This task wires the weekly trigger. `run.py main()` already emits a JSON envelope (`{to, subject, html, markdown, new_count}`) on stdout and writes `data/latest_digest.json`. The scheduled agent runs the pipeline and sends that envelope as an email via the Gmail integration.

**Files:**
- Create: `docs/RUNBOOK.md`

- [ ] **Step 1: Write `docs/RUNBOOK.md`**

```markdown
# Outlier Scout — Runbook

## Manual run
```bash
./venv/bin/python -m outlier_scout.run
```
Prints a JSON envelope `{to, subject, html, markdown, new_count}` and writes
`data/latest_digest.json`. Requires `YOUTUBE_API_KEY` and `ANTHROPIC_API_KEY`
in `.env`.

## Weekly schedule (Sunday 08:00)
A scheduled Claude agent runs weekly and:
1. Executes `./venv/bin/python -m outlier_scout.run` from the repo root.
2. Parses the JSON envelope from stdout.
3. Sends an email to `to` with `subject` and `html` body via the Gmail
   integration.

The agent prompt is:
> Run `./venv/bin/python -m outlier_scout.run` in /Users/faisalkarnib/projects/outlier-scout.
> Parse the JSON it prints on stdout. Send an email to the `to` address with the
> `subject` and the `html` as the HTML body using the Gmail tool. If `new_count`
> is 0, still send it. Report the send result.
```

- [ ] **Step 2: Commit the runbook**

```bash
git add docs/RUNBOOK.md
git commit -m "docs: runbook for manual and scheduled runs"
```

- [ ] **Step 3: Register the schedule (operator action — uses the `schedule` skill)**

This step is performed by the operator in a Claude Code session, not by code. Invoke the `schedule` skill to create a routine:
- **Cadence:** weekly, Sunday 08:00 (operator's local timezone).
- **Prompt:** the agent prompt from `docs/RUNBOOK.md` Step 1.

Verify the routine appears in the schedule list after creation. No commit (external state).

---

### Task 12: Remove the superseded root script

**Files:**
- Delete: `outliers.py` (root)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Confirm nothing imports the root script**

Run: `grep -rn "import outliers" --include=*.py . || echo "no references"`
Expected: "no references" (the package uses `outlier_scout.outliers`).

- [ ] **Step 2: Delete the root script**

Run: `git rm outliers.py`

- [ ] **Step 3: Update `CLAUDE.md`**

Replace the `## Run` and `## How it works (outliers.py)` sections with:

```markdown
## Run
- Manual: `./venv/bin/python -m outlier_scout.run` (prints a JSON email envelope)
- Tests: `./venv/bin/python -m pytest`
- Requires `YOUTUBE_API_KEY` and `ANTHROPIC_API_KEY` in `.env`

## How it works
Weekly pipeline in `outlier_scout/`: discover channels (seed + keyword) →
fetch recent videos → score outliers per-channel by format median →
drop already-emailed IDs (sqlite) → analyze each with Claude →
render digest → a scheduled agent emails it. See
`docs/superpowers/specs/2026-06-03-youtube-outlier-research-tool-design.md`.
```

- [ ] **Step 4: Run the full suite (still green)**

Run: `./venv/bin/python -m pytest`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove superseded root outliers.py; update CLAUDE.md"
```

---

## Self-Review Notes

- **Spec coverage:** Discover (§6/Task 7), Fetch (§6/Task 6), per-channel outlier definition with min-baseline (§8/Task 3), dedup store (§10/Task 5), Claude analysis with retry/fallback (§11/Task 8), report HTML+MD incl. empty-week (§12/Task 9), scheduling + Gmail delivery (§13/Task 11), config/params (§9/Task 4), error handling — quota/thin-channel/claude-failure/empty-week (§14/Tasks 3,8,9,10). All covered.
- **Email mechanism:** §6 lists an `email.py`; the plan instead has `run.py` emit a JSON envelope the scheduled agent sends via the Gmail tool (Python cannot call the MCP Gmail tool). This is the intended reconciliation of §13.
- **Type consistency:** `Video`, `Outlier(video_format=...)`, `AnalyzedOutlier`, `Digest(new_count=...)` used identically across Tasks 2–10. `score_channel(videos, threshold, min_videos_per_format, now)` signature consistent in Tasks 3 and 10. `FakeYouTubeClient`/`FakeAnthropic` interfaces match `YouTubeClient`/`anthropic.Anthropic` usage.
- **YouTube quota note:** discovery `search.list` costs 100 units/call; with tight caps (≤ a few keywords × 5) the run stays well within the 10k/day free quota.
```
