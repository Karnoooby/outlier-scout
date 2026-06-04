# Niche-Anchor Video-Search Outlier Hunt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor outlier-scout to anchor on the creator's recent videos, derive core + adjacent niches (agent), hunt recent breakout videos via YouTube video-search, confirm each against its own channel's format-median baseline, and emit outliers as JSON for the agent to analyze and email — with no Anthropic API key.

**Architecture:** Agent orchestrates; Python computes. Python exposes three CLI subcommands (`anchor-profile`, `hunt`, `mark-reported`) that read/write JSON. The agent does niche expansion, relevance filtering, analysis, and Gmail-draft composition. This removes the old channel-discovery + API-analysis + HTML-render path.

**Tech Stack:** Python 3.9, `google-api-python-client`, `python-dotenv`, `PyYAML`, stdlib `sqlite3`/`argparse`/`json`, `pytest`.

---

## File Structure

```
outlier_scout/
  models.py       # Video; Outlier (+niche_label, +niche_type). AnalyzedOutlier/Digest removed.
  outliers.py     # parse_duration, classify_format, median, format_median. score_channel removed.
  youtube.py      # YouTubeClient: +search_videos, +get_videos; search_channels removed.
  fetch.py        # fetch_channel_videos (unchanged)
  anchor.py       # build_anchor_profile (new)
  hunt.py         # hunt() — video-search → per-channel baseline → tagged outliers (new)
  store.py        # SQLite dedup (unchanged)
  config.py       # new fields; ANTHROPIC_API_KEY no longer required
  cli.py          # argparse subcommands: anchor-profile, hunt, mark-reported (replaces run.py)
tests/
  fakes.py        # FakeYouTubeClient (search_videos + get_videos); FakeAnthropic removed
  test_outliers.py, test_config.py, test_store.py, test_fetch.py
  test_anchor.py, test_hunt.py, test_cli.py
config.yaml, .env.example, docs/RUNBOOK.md, CLAUDE.md   # updated
REMOVED: analyze.py, report.py, discover.py, run.py + test_analyze.py, test_report.py, test_discover.py, test_run.py
```

---

### Task 1: Remove the superseded modules

We start by clearing the old channel-discovery / API-analysis / HTML-render / orchestration path so later changes don't fight dead code.

**Files:**
- Delete: `outlier_scout/analyze.py`, `outlier_scout/report.py`, `outlier_scout/discover.py`, `outlier_scout/run.py`
- Delete: `tests/test_analyze.py`, `tests/test_report.py`, `tests/test_discover.py`, `tests/test_run.py`

- [ ] **Step 1: Confirm what imports these (should be only each other + tests)**

Run: `cd /Users/faisalkarnib/projects/outlier-scout && grep -rn "import analyze\|import report\|import discover\|import run\|from outlier_scout.analyze\|from outlier_scout.report\|from outlier_scout.discover\|from outlier_scout.run" outlier_scout tests`
Expected: matches only inside the files being deleted and their test files.

- [ ] **Step 2: Delete the modules and their tests**

Run:
```bash
git rm outlier_scout/analyze.py outlier_scout/report.py outlier_scout/discover.py outlier_scout/run.py \
       tests/test_analyze.py tests/test_report.py tests/test_discover.py tests/test_run.py
```

- [ ] **Step 3: Run the suite (remaining tests must still pass)**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS. Remaining test files: `test_outliers.py`, `test_config.py`, `test_store.py`, `test_fetch.py`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove channel-discovery/API-analysis/render path for video-search redesign"
```

---

### Task 2: Models — add niche fields, drop unused dataclasses

**Files:**
- Modify: `outlier_scout/models.py`
- Test: `tests/test_outliers.py` (the model tests live here)

- [ ] **Step 1: Update the model test**

In `tests/test_outliers.py`, replace the existing `test_outlier_holds_fields` with:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_outliers.py -q`
Expected: FAIL (Outlier has no `niche_label`).

- [ ] **Step 3: Update `outlier_scout/models.py`**

Replace the entire file with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
    niche_label: str = ""
    niche_type: str = ""       # "core" or "adjacent"
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_outliers.py -q`
Expected: FAIL — `test_outliers.py` still imports/uses `score_channel`, which we remove in Task 3. The two new model tests pass; `score_channel` tests/imports now error. That's expected; proceed to Task 3 immediately (do NOT commit a red suite).

> Note: Tasks 2 and 3 form one green checkpoint. Implement both, then run the suite and commit once at the end of Task 3.

---

### Task 3: outliers.py — add `format_median`, remove `score_channel`

**Files:**
- Modify: `outlier_scout/outliers.py`
- Test: `tests/test_outliers.py`

- [ ] **Step 1: Update `tests/test_outliers.py`**

Remove the import of `score_channel` and the two tests `test_score_channel_flags_outliers_per_format` and `test_score_channel_skips_thin_format`. Change the outliers import line to:

```python
from outlier_scout.outliers import (
    parse_duration, classify_format, median, format_median,
)
```

Then append these tests:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_outliers.py -q`
Expected: FAIL (`format_median` not defined).

- [ ] **Step 3: Replace `outlier_scout/outliers.py`**

```python
from __future__ import annotations

import re
import statistics
from typing import List, Optional

from outlier_scout.models import Video

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


def format_median(videos: List[Video], fmt: str, min_videos: int) -> Optional[float]:
    """Median view count of a channel's videos in one format.

    Returns None when fewer than `min_videos` exist for that format
    (baseline too thin to trust).
    """
    counts = [v.views for v in videos if classify_format(v.duration_s) == fmt]
    if len(counts) < min_videos:
        return None
    return median(counts)
```

- [ ] **Step 4: Run to verify pass (full suite — Tasks 2+3 checkpoint)**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS (all remaining tests green).

- [ ] **Step 5: Commit**

```bash
git add outlier_scout/models.py outlier_scout/outliers.py tests/test_outliers.py
git commit -m "feat: niche fields on Outlier; format_median baseline helper"
```

---

### Task 4: youtube.py — add `search_videos` + `get_videos`, remove `search_channels`

**Files:**
- Modify: `outlier_scout/youtube.py`

This module is a thin live-API wrapper (not unit-tested; verified by import + the live trial). No test step; verify it imports.

- [ ] **Step 1: In `outlier_scout/youtube.py`, rename `_hydrate` to a public `get_videos` and add `search_videos`; delete `search_channels`.**

Replace the `_hydrate` method definition line `def _hydrate(self, video_ids: List[str]) -> List[Video]:` with `def get_videos(self, video_ids: List[str]) -> List[Video]:` and update its internal docstring/usage. Update the caller inside `get_recent_videos` (the final `return self._hydrate(ids)`) to `return self.get_videos(ids)`.

Then delete the entire `search_channels` method, and add this method:

```python
    def search_videos(self, query: str, max_results: int,
                      published_after: str, relevance_language: str = "en") -> List[str]:
        """Recent, high-view video IDs for a query (RFC3339 published_after, e.g.
        '2026-05-28T00:00:00Z'). Returns video IDs in id.videoId."""
        resp = self._yt.search().list(
            part="snippet", q=query, type="video", order="viewCount",
            maxResults=min(50, max_results), publishedAfter=published_after,
            relevanceLanguage=relevance_language,
        ).execute()
        return [it["id"]["videoId"] for it in resp.get("items", [])]
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `./venv/bin/python -c "import outlier_scout.youtube; c=outlier_scout.youtube.YouTubeClient; assert hasattr(c,'search_videos') and hasattr(c,'get_videos') and not hasattr(c,'search_channels'); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Run the suite (no regressions)**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add outlier_scout/youtube.py
git commit -m "feat: youtube search_videos + public get_videos; drop search_channels"
```

---

### Task 5: Extend the test fake

**Files:**
- Modify: `tests/fakes.py`

- [ ] **Step 1: Replace `tests/fakes.py` entirely**

```python
from __future__ import annotations

from typing import Dict, List

from outlier_scout.models import Video


class FakeYouTubeClient:
    """In-memory stand-in for YouTubeClient used in tests."""

    def __init__(self, channels: Dict[str, dict], videos: Dict[str, List[Video]],
                 search_results: Dict[str, List[str]] = None,
                 video_index: Dict[str, Video] = None):
        # channels: handle OR channel_id -> {"channel_id","title","uploads_playlist_id"}
        self._channels = channels
        # videos: uploads_playlist_id -> [Video, ...]  (used for baselines/anchor)
        self._videos = videos
        # search_results: query -> [video_id, ...]
        self._search = search_results or {}
        # video_index: video_id -> Video  (used by get_videos)
        self._video_index = video_index or {}

    def get_channel(self, handle: str) -> dict:
        return self._channels[handle]

    def get_recent_videos(self, uploads_playlist_id: str, max_items: int) -> List[Video]:
        return self._videos.get(uploads_playlist_id, [])[:max_items]

    def get_videos(self, video_ids: List[str]) -> List[Video]:
        return [self._video_index[v] for v in video_ids if v in self._video_index]

    def search_videos(self, query: str, max_results: int,
                      published_after: str, relevance_language: str = "en") -> List[str]:
        return self._search.get(query, [])[:max_results]
```

- [ ] **Step 2: Run the suite (test_fetch uses this fake — must stay green)**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/fakes.py
git commit -m "test: fake youtube client with search_videos + get_videos"
```

---

### Task 6: anchor.py — build the anchor profile

**Files:**
- Create: `outlier_scout/anchor.py`
- Test: `tests/test_anchor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anchor.py`:

```python
from datetime import datetime, timezone
from outlier_scout.anchor import build_anchor_profile
from outlier_scout.models import Video
from tests.fakes import FakeYouTubeClient


def vid(id, dur, views, desc=""):
    return Video(id=id, title=id, channel_id="anchor", channel_title="Me",
                 views=views, published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                 duration_s=dur, description=desc, thumbnail_url="", url=f"http://yt/{id}")


def test_build_anchor_profile_returns_recent_videos():
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me",
                          "uploads_playlist_id": "UP"}},
        videos={"UP": [vid("a", 30, 100, "short desc"), vid("b", 300, 50)]},
    )
    profile = build_anchor_profile(client, "@me", count=12)
    assert profile["channel"] == "Me"
    assert [v["format"] for v in profile["videos"]] == ["Short", "Long"]
    assert profile["videos"][0]["title"] == "a"
    assert profile["videos"][0]["views"] == 100


def test_build_anchor_profile_respects_count():
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me",
                          "uploads_playlist_id": "UP"}},
        videos={"UP": [vid(str(i), 300, i) for i in range(20)]},
    )
    profile = build_anchor_profile(client, "@me", count=5)
    assert len(profile["videos"]) == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_anchor.py -q`
Expected: FAIL (no module `outlier_scout.anchor`).

- [ ] **Step 3: Write `outlier_scout/anchor.py`**

```python
from __future__ import annotations

from outlier_scout.outliers import classify_format


def build_anchor_profile(client, handle: str, count: int) -> dict:
    """The anchor channel's most recent `count` uploads, as a JSON-friendly dict
    the agent reads to derive the niche."""
    channel = client.get_channel(handle)
    videos = client.get_recent_videos(channel["uploads_playlist_id"], count)
    return {
        "channel": channel["title"],
        "videos": [
            {
                "title": v.title,
                "format": classify_format(v.duration_s),
                "views": v.views,
                "description": (v.description or "")[:500],
            }
            for v in videos
        ],
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_anchor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outlier_scout/anchor.py tests/test_anchor.py
git commit -m "feat: anchor profile from creator's recent uploads"
```

---

### Task 7: hunt.py — the video-search outlier hunt

**Files:**
- Create: `outlier_scout/hunt.py`
- Test: `tests/test_hunt.py`

This is the core of the redesign. `hunt` takes a normalized list of niche dicts, searches videos per niche, traces each to its channel for a baseline, and returns tagged `Outlier`s inside the sanity band and report window, excluding the anchor and already-reported videos.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hunt.py`:

```python
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from outlier_scout.hunt import hunt
from outlier_scout.models import Video
from tests.fakes import FakeYouTubeClient


NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


@dataclass
class Cfg:
    anchor_channel: str = "@me"
    report_window_days: int = 7
    lookback_days: int = 90
    max_videos_per_query: int = 8
    relevance_language: str = "en"
    outlier_threshold: float = 2.5
    outlier_ceiling: float = 80.0
    min_videos_per_format: int = 3


def vid(id, channel_id, views, dur=300, days_old=2):
    return Video(id=id, title=id, channel_id=channel_id, channel_title=channel_id,
                 views=views, published_at=NOW - timedelta(days=days_old),
                 duration_s=dur, description="", thumbnail_url="",
                 url=f"http://yt/{id}")


def baseline_videos(channel_id, median_views, n=5, dur=300):
    # n videos all at median_views so the channel's format median == median_views
    return [vid(f"{channel_id}_b{i}", channel_id, median_views, dur, days_old=40)
            for i in range(n)]


def build_client(candidate, base_median=1000, base_dur=300):
    """One discovered channel 'C' with a baseline; one search query 'q' that
    returns the candidate video id."""
    return FakeYouTubeClient(
        channels={
            "@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"},
            "C": {"channel_id": "C", "title": "C", "uploads_playlist_id": "UPc"},
        },
        videos={"UPc": baseline_videos("C", base_median, dur=base_dur)},
        search_results={"q": [candidate.id]},
        video_index={candidate.id: candidate},
    )


def niches(label="core niche", ntype="core", queries=("q",)):
    return [{"label": label, "type": ntype, "queries": list(queries)}]


def test_hunt_flags_video_above_threshold():
    cand = vid("HIT", "C", 4000)  # 4x the 1000 baseline
    client = build_client(cand)
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda vid_id: False)
    assert [o.video.id for o in out] == ["HIT"]
    assert out[0].multiplier == 4.0
    assert out[0].niche_label == "core niche"
    assert out[0].niche_type == "core"


def test_hunt_drops_below_threshold():
    client = build_client(vid("LOW", "C", 2000))  # 2x < 2.5
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_drops_above_ceiling():
    client = build_client(vid("LOTTERY", "C", 200000))  # 200x > 80 ceiling
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_drops_outside_report_window():
    client = build_client(vid("OLD", "C", 4000, days_old=30))  # > 7d window
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_skips_thin_format_baseline():
    # channel has only 2 long videos -> baseline None -> skip
    cand = vid("HIT", "C", 4000)
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"},
                  "C": {"channel_id": "C", "title": "C", "uploads_playlist_id": "UPc"}},
        videos={"UPc": baseline_videos("C", 1000, n=2)},
        search_results={"q": ["HIT"]},
        video_index={"HIT": cand},
    )
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_excludes_anchor_channel():
    cand = vid("MINE", "anchor", 4000)
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"}},
        videos={"UPme": baseline_videos("anchor", 1000)},
        search_results={"q": ["MINE"]},
        video_index={"MINE": cand},
    )
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda v: False)
    assert out == []


def test_hunt_filters_already_reported():
    client = build_client(vid("HIT", "C", 4000))
    out = hunt(client, niches(), Cfg(), NOW, is_reported=lambda vid_id: vid_id == "HIT")
    assert out == []


def test_hunt_caches_channel_baseline_across_queries():
    cand = vid("HIT", "C", 4000)
    client = FakeYouTubeClient(
        channels={"@me": {"channel_id": "anchor", "title": "Me", "uploads_playlist_id": "UPme"},
                  "C": {"channel_id": "C", "title": "C", "uploads_playlist_id": "UPc"}},
        videos={"UPc": baseline_videos("C", 1000)},
        search_results={"q1": ["HIT"], "q2": ["HIT"]},
        video_index={"HIT": cand},
    )
    calls = {"n": 0}
    orig = client.get_recent_videos
    def counting(pid, n):
        if pid == "UPc":
            calls["n"] += 1
        return orig(pid, n)
    client.get_recent_videos = counting
    out = hunt(client, niches(queries=("q1", "q2")), Cfg(), NOW, is_reported=lambda v: False)
    assert [o.video.id for o in out] == ["HIT"]   # seen-video dedup keeps it once
    assert calls["n"] == 1                          # baseline fetched once (cached)
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_hunt.py -q`
Expected: FAIL (no module `outlier_scout.hunt`).

- [ ] **Step 3: Write `outlier_scout/hunt.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, List

from googleapiclient.errors import HttpError

from outlier_scout.fetch import fetch_channel_videos
from outlier_scout.models import Outlier
from outlier_scout.outliers import classify_format, format_median


def hunt(client, niche_queries: List[dict], config, now: datetime,
         is_reported: Callable[[str], bool]) -> List[Outlier]:
    """Find recent breakout videos across the given niches.

    niche_queries: [{"label": str, "type": "core"|"adjacent", "queries": [str]}]
    Each candidate video (from video-search) is kept when it beats its own
    channel's format median by >= threshold and <= ceiling, is within the
    report window, isn't from the anchor channel, and isn't already reported.
    """
    published_after = (now - timedelta(days=config.report_window_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    anchor_id = client.get_channel(config.anchor_channel)["channel_id"]
    baseline_cache: dict = {}

    def channel_baseline(channel_id: str) -> dict:
        if channel_id not in baseline_cache:
            try:
                vids = fetch_channel_videos(client, channel_id, config.lookback_days, now)
            except HttpError:
                vids = []
            baseline_cache[channel_id] = {
                fmt: format_median(vids, fmt, config.min_videos_per_format)
                for fmt in ("Short", "Long")
            }
        return baseline_cache[channel_id]

    outliers: List[Outlier] = []
    seen_videos: set = set()
    for niche in niche_queries:
        ids: List[str] = []
        for query in niche["queries"]:
            try:
                ids += client.search_videos(
                    query, config.max_videos_per_query,
                    published_after, config.relevance_language,
                )
            except HttpError:
                break  # quota/API error: stop this niche, keep what we have
        ids = [i for i in dict.fromkeys(ids) if i not in seen_videos]
        seen_videos.update(ids)

        for v in client.get_videos(ids):
            if v.channel_id == anchor_id or is_reported(v.id):
                continue
            age_days = (now - v.published_at).days
            if age_days > config.report_window_days:
                continue
            fmt = classify_format(v.duration_s)
            base = channel_baseline(v.channel_id).get(fmt)
            if not base:
                continue
            mult = round(v.views / base, 2)
            if not (config.outlier_threshold <= mult <= config.outlier_ceiling):
                continue
            outliers.append(Outlier(
                video=v, multiplier=mult, video_format=fmt,
                baseline_median=base, age_days=age_days,
                niche_label=niche["label"], niche_type=niche["type"],
            ))

    outliers.sort(key=lambda o: o.multiplier, reverse=True)
    return outliers
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_hunt.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add outlier_scout/hunt.py tests/test_hunt.py
git commit -m "feat: video-search niche outlier hunt with per-channel baseline"
```

---

### Task 8: config.py — new fields, drop the Anthropic requirement

**Files:**
- Modify: `outlier_scout/config.py`, `config.yaml`, `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Replace `tests/test_config.py`**

```python
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
    assert cfg.adjacent_hints == []
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL (Config lacks the new fields).

- [ ] **Step 3: Replace `outlier_scout/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    anchor_channel: str
    recipient_email: str
    youtube_api_key: str
    anchor_video_count: int = 12
    adjacent_hints: List[str] = None
    report_window_days: int = 7
    lookback_days: int = 90
    max_videos_per_query: int = 8
    relevance_language: str = "en"
    outlier_threshold: float = 2.5
    outlier_ceiling: float = 80.0
    min_videos_per_format: int = 3


def load_config(path: str) -> Config:
    load_dotenv()
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    if not youtube_api_key:
        raise ValueError("YOUTUBE_API_KEY not found in environment (.env)")

    return Config(
        anchor_channel=data["anchor_channel"],
        recipient_email=data["recipient_email"],
        youtube_api_key=youtube_api_key,
        anchor_video_count=int(data.get("anchor_video_count", 12)),
        adjacent_hints=list(data.get("adjacent_hints", []) or []),
        report_window_days=int(data.get("report_window_days", 7)),
        lookback_days=int(data.get("lookback_days", 90)),
        max_videos_per_query=int(data.get("max_videos_per_query", 8)),
        relevance_language=str(data.get("relevance_language", "en")),
        outlier_threshold=float(data.get("outlier_threshold", 2.5)),
        outlier_ceiling=float(data.get("outlier_ceiling", 80)),
        min_videos_per_format=int(data.get("min_videos_per_format", 3)),
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Rewrite `config.yaml`**

```yaml
anchor_channel: "@karnooby"      # your channel — defines the niche
anchor_video_count: 12           # last N uploads used to derive the niche
adjacent_hints: []               # optional: nudge specific adjacent niches
report_window_days: 7            # only report videos newer than this
lookback_days: 90                # window used to build each channel's baseline
max_videos_per_query: 8          # video-search results requested per query
relevance_language: "en"         # filter search to this language
outlier_threshold: 2.5           # min multiplier vs channel format median
outlier_ceiling: 80              # max multiplier (drops lottery/faceless slop)
min_videos_per_format: 3         # skip a format with fewer recent videos
recipient_email: "f.karnib1996@gmail.com"
```

- [ ] **Step 6: Rewrite `.env.example`** (drop the Anthropic line)

```
YOUTUBE_API_KEY=your_key_here
```

- [ ] **Step 7: Commit**

```bash
git add outlier_scout/config.py config.yaml .env.example tests/test_config.py
git commit -m "feat: niche-anchor config; drop Anthropic key requirement"
```

---

### Task 9: cli.py — `anchor-profile`, `hunt`, `mark-reported`

**Files:**
- Create: `outlier_scout/cli.py`
- Test: `tests/test_cli.py`

The CLI is thin glue plus two pure helpers we unit-test directly: `normalize_niche_queries` (agent JSON → flat list) and `outliers_to_json`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `./venv/bin/python -m pytest tests/test_cli.py -q`
Expected: FAIL (no module `outlier_scout.cli`).

- [ ] **Step 3: Write `outlier_scout/cli.py`**

```python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List

from outlier_scout.config import load_config
from outlier_scout.models import Outlier
from outlier_scout.store import Store

DB_PATH = "data/reported.db"
CONFIG_PATH = "config.yaml"


def normalize_niche_queries(agent_json: dict) -> List[dict]:
    """Agent JSON {core:{label,queries}, adjacent:[{label,queries}]} -> flat list."""
    out: List[dict] = []
    core = agent_json["core"]
    out.append({"label": core["label"], "type": "core",
                "queries": list(core["queries"])})
    for adj in agent_json.get("adjacent", []):
        out.append({"label": adj["label"], "type": "adjacent",
                    "queries": list(adj["queries"])})
    return out


def outliers_to_json(outliers: List[Outlier]) -> List[dict]:
    rows = []
    for o in outliers:
        v = o.video
        rows.append({
            "id": v.id,
            "title": v.title,
            "channel_title": v.channel_title,
            "url": v.url,
            "thumbnail_url": v.thumbnail_url,
            "views": v.views,
            "video_format": o.video_format,
            "multiplier": o.multiplier,
            "age_days": o.age_days,
            "niche_label": o.niche_label,
            "niche_type": o.niche_type,
            "description": (v.description or "")[:500],
        })
    return rows


def _client(config):
    from outlier_scout.youtube import YouTubeClient
    return YouTubeClient(config.youtube_api_key)


def _cmd_anchor_profile(args):
    from outlier_scout.anchor import build_anchor_profile
    config = load_config(CONFIG_PATH)
    profile = build_anchor_profile(_client(config), config.anchor_channel,
                                   config.anchor_video_count)
    json.dump(profile, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _cmd_hunt(args):
    from outlier_scout.hunt import hunt
    config = load_config(CONFIG_PATH)
    agent_json = json.load(open(args.queries)) if args.queries else json.load(sys.stdin)
    niche_queries = normalize_niche_queries(agent_json)
    store = Store(DB_PATH)
    now = datetime.now(timezone.utc)
    outliers = hunt(_client(config), niche_queries, config, now, store.is_reported)
    json.dump(outliers_to_json(outliers), sys.stdout, indent=2)
    sys.stdout.write("\n")


def _cmd_mark_reported(args):
    ids = [s for s in (args.ids or sys.stdin.read()).replace(",", " ").split() if s]
    store = Store(DB_PATH)
    store.mark_reported(ids, datetime.now(timezone.utc))
    sys.stdout.write(f"marked {len(ids)} reported\n")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="outlier_scout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("anchor-profile").set_defaults(func=_cmd_anchor_profile)

    p_hunt = sub.add_parser("hunt")
    p_hunt.add_argument("--queries", help="path to niche-queries JSON (else stdin)")
    p_hunt.set_defaults(func=_cmd_hunt)

    p_mark = sub.add_parser("mark-reported")
    p_mark.add_argument("--ids", help="comma/space separated video IDs (else stdin)")
    p_mark.set_defaults(func=_cmd_mark_reported)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/python -m pytest tests/test_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify the CLI wires up (no network: just the help/subcommands)**

Run: `./venv/bin/python -m outlier_scout.cli --help 2>&1 | grep -E "anchor-profile|hunt|mark-reported"`
Expected: all three subcommands listed.

- [ ] **Step 6: Run the full suite**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add outlier_scout/cli.py tests/test_cli.py
git commit -m "feat: cli subcommands anchor-profile, hunt, mark-reported"
```

---

### Task 10: Docs — agent runbook + CLAUDE.md

**Files:**
- Modify: `docs/RUNBOOK.md`, `CLAUDE.md`

- [ ] **Step 1: Replace `docs/RUNBOOK.md`**

```markdown
# Outlier Scout — Runbook (agent-driven, no API key)

## Manual commands
```bash
./venv/bin/python -m outlier_scout.cli anchor-profile          # -> anchor profile JSON
./venv/bin/python -m outlier_scout.cli hunt --queries q.json   # -> new outliers JSON
./venv/bin/python -m outlier_scout.cli mark-reported --ids a,b # record emailed video IDs
```
Requires only `YOUTUBE_API_KEY` in `.env`.

## Weekly schedule (Sunday 08:00) — what the scheduled Claude agent does
1. Run `anchor-profile`. Read the creator's last ~12 videos.
2. Name the CORE niche; brainstorm several genuinely ADJACENT niches. Emit niche-query JSON:
   ```json
   {
     "core": {"label": "gaming psychology", "queries": ["psychology of gaming", "gaming burnout"]},
     "adjacent": [
       {"label": "digital wellness", "queries": ["dopamine detox", "phone addiction focus"]},
       {"label": "gaming video essays", "queries": ["gaming video essay"]}
     ]
   }
   ```
3. Run `hunt --queries <that json>` to get new outliers (each tagged with niche_label/niche_type).
4. RELEVANCE FILTER (judgment): drop non-English slip-throughs, faceless motivation/repost slop,
   and off-topic results. Keep instructive, on-niche videos.
5. Compose an HTML digest grouped by niche (core first, then each adjacent), each entry with:
   what it is, why it broke out, how to apply it to the creator's channel.
6. Create a Gmail DRAFT to the configured recipient (the connector cannot auto-send).
7. Run `mark-reported --ids <ids of videos you included>` so they never repeat.
8. If no outliers survive, still create a short "nothing new this week" draft.
```

- [ ] **Step 2: Update `CLAUDE.md`** — replace the `## Run` and `## How it works` sections with:

```markdown
## Run
- Anchor profile: `./venv/bin/python -m outlier_scout.cli anchor-profile`
- Hunt: `./venv/bin/python -m outlier_scout.cli hunt --queries q.json`
- Mark reported: `./venv/bin/python -m outlier_scout.cli mark-reported --ids a,b`
- Tests: `./venv/bin/python -m pytest`
- Requires only `YOUTUBE_API_KEY` in `.env` (no Anthropic key — analysis is agent-driven)

## How it works
Agent-driven niche-anchor hunt: Python returns the creator's recent videos
(`anchor-profile`); the scheduled Claude agent derives core + adjacent niches and
emits search queries; `hunt` video-searches recent breakouts, confirms each against
its own channel's format-median baseline (within a sanity band + report window),
dedups, and returns tagged outliers; the agent relevance-filters, analyzes, and
emails a Gmail draft, then calls `mark-reported`. See
`docs/superpowers/specs/2026-06-04-niche-anchor-video-search-design.md` and `docs/RUNBOOK.md`.
```

- [ ] **Step 3: Run the full suite (docs change shouldn't affect it)**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/RUNBOOK.md CLAUDE.md
git commit -m "docs: agent runbook + CLAUDE.md for video-search redesign"
```

---

## Self-Review Notes

- **Spec coverage:** anchor (§5/Task 6), video-search + get_videos (§5/Task 4), niche fields (§5/Task 2), format_median baseline (§6/Task 3), hunt with sanity band + report window + anchor-exclude + dedup + baseline cache (§4,§6/Task 7), config incl. ceiling/relevance_language and dropped Anthropic key (§7/Task 8), CLI subcommands + JSON contracts (§4/Task 9), removals (§12/Task 1), agent runbook + relevance filter + draft-only (§3,§10/Task 10), quota/HttpError graceful stop (§8,§9/Task 7). Covered.
- **Type consistency:** `Outlier(..., niche_label, niche_type)` constructed in Task 7 matches Task 2's dataclass. `format_median(videos, fmt, min_videos)` used identically in Tasks 3 and 7. `hunt(client, niche_queries, config, now, is_reported)` signature matches its test and the CLI call in Task 9. `Config` field names used in Task 7's `Cfg` test stub and in Task 8's real dataclass match (`report_window_days`, `outlier_ceiling`, `max_videos_per_query`, `relevance_language`, `min_videos_per_format`). `search_videos`/`get_videos` defined in Task 4, faked in Task 5, called in Task 7.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Note on Tasks 2+3:** intentionally a single green checkpoint (Task 2 leaves the suite red until Task 3 removes `score_channel`); commit only after Task 3 Step 4.
```
