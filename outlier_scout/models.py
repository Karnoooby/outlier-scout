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
