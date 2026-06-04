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
