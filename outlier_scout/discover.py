from __future__ import annotations

from typing import List

from googleapiclient.errors import HttpError

# Channels to request per keyword before merging/capping.
RESULTS_PER_KEYWORD = 5


def discover_channels(client, keywords: List[str], seed_channels: List[str],
                      max_channels: int) -> List[str]:
    """Seed channels first, then keyword-discovered channels, deduped and capped."""
    ordered: List[str] = []
    seen = set()

    def add(handle: str):
        if handle not in seen:
            seen.add(handle)
            ordered.append(handle)

    for h in seed_channels:
        add(h)
    for kw in keywords:
        try:
            results = client.search_channels(kw, RESULTS_PER_KEYWORD)
        except HttpError:
            break  # quota exhausted / API error: stop discovery, keep what we have
        for h in results:
            add(h)

    return ordered[:max_channels]
