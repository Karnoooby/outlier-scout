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
