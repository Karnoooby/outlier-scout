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
