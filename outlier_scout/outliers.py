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
