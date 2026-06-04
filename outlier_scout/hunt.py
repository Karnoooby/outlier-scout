from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, List

from googleapiclient.errors import HttpError

from outlier_scout.models import Outlier
from outlier_scout.outliers import classify_format, format_median

# How many recent uploads to sample when building a channel's baseline.
_MAX_BASELINE_UPLOADS = 50


def hunt(client, niche_queries: List[dict], config, now: datetime,
         is_reported: Callable[[str], bool]) -> List[Outlier]:
    """Find recent breakout videos across the given niches.

    niche_queries: [{"label": str, "type": "core"|"adjacent", "queries": [str]}]
    Each candidate video (from video-search) is kept when it beats its own
    channel's format median by >= threshold and <= ceiling, is within the
    report window, its channel's subscriber count is within the configured band,
    isn't from the anchor channel, and isn't already reported.
    """
    published_after = (now - timedelta(days=config.report_window_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    anchor_id = client.get_channel(config.anchor_channel)["channel_id"]
    info_cache: dict = {}
    baseline_cache: dict = {}

    def channel_info(channel_id: str):
        if channel_id not in info_cache:
            try:
                info_cache[channel_id] = client.get_channel(channel_id)
            except (HttpError, LookupError):
                info_cache[channel_id] = None
        return info_cache[channel_id]

    def subs_in_band(info: dict) -> bool:
        subs = info.get("subscriber_count")
        if subs is None:
            return True  # hidden subscriber count: can't judge, keep it
        return config.min_subscribers <= subs <= config.max_subscribers

    def channel_baseline(info: dict) -> dict:
        cid = info["channel_id"]
        if cid not in baseline_cache:
            try:
                raw = client.get_recent_videos(
                    info["uploads_playlist_id"], _MAX_BASELINE_UPLOADS
                )
            except HttpError:
                raw = []
            cutoff = now - timedelta(days=config.lookback_days)
            vids = [v for v in raw if v.published_at >= cutoff]
            baseline_cache[cid] = {
                fmt: format_median(vids, fmt, config.min_videos_per_format)
                for fmt in ("Short", "Long")
            }
        return baseline_cache[cid]

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
            info = channel_info(v.channel_id)
            if info is None or not subs_in_band(info):
                continue
            fmt = classify_format(v.duration_s)
            base = channel_baseline(info).get(fmt)
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
