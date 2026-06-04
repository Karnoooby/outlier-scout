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
