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
