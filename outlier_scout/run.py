from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import List

from googleapiclient.errors import HttpError

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
    seen_channels = set()  # canonical channel_ids, to dedup seed/discovery overlap
    for handle in channels:
        try:
            videos = fetch_channel_videos(
                youtube_client, handle, config.lookback_days, now,
            )
        except (LookupError, HttpError):
            continue  # channel not found OR API error → skip gracefully
        if not videos:
            continue
        channel_id = videos[0].channel_id
        if channel_id in seen_channels:
            continue  # same channel reached via both a seed handle and discovery
        seen_channels.add(channel_id)
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
