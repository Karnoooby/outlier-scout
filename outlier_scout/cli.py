from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List

from outlier_scout.config import load_config
from outlier_scout.models import Outlier
from outlier_scout.store import Store

DB_PATH = "data/reported.db"
CONFIG_PATH = "config.yaml"


def normalize_niche_queries(agent_json: dict) -> List[dict]:
    """Agent JSON {core:{label,queries}, adjacent:[{label,queries}]} -> flat list."""
    out: List[dict] = []
    core = agent_json["core"]
    out.append({"label": core["label"], "type": "core",
                "queries": list(core["queries"])})
    for adj in agent_json.get("adjacent", []):
        out.append({"label": adj["label"], "type": "adjacent",
                    "queries": list(adj["queries"])})
    return out


def outliers_to_json(outliers: List[Outlier]) -> List[dict]:
    rows = []
    for o in outliers:
        v = o.video
        rows.append({
            "id": v.id,
            "title": v.title,
            "channel_title": v.channel_title,
            "url": v.url,
            "thumbnail_url": v.thumbnail_url,
            "views": v.views,
            "video_format": o.video_format,
            "multiplier": o.multiplier,
            "age_days": o.age_days,
            "niche_label": o.niche_label,
            "niche_type": o.niche_type,
            "description": (v.description or "")[:500],
        })
    return rows


def _client(config):
    from outlier_scout.youtube import YouTubeClient
    return YouTubeClient(config.youtube_api_key)


def _cmd_anchor_profile(args):
    from outlier_scout.anchor import build_anchor_profile
    config = load_config(CONFIG_PATH)
    profile = build_anchor_profile(_client(config), config.anchor_channel,
                                   config.anchor_video_count)
    json.dump(profile, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _cmd_hunt(args):
    from outlier_scout.hunt import hunt
    config = load_config(CONFIG_PATH)
    agent_json = json.load(open(args.queries)) if args.queries else json.load(sys.stdin)
    niche_queries = normalize_niche_queries(agent_json)
    store = Store(DB_PATH)
    now = datetime.now(timezone.utc)
    outliers = hunt(_client(config), niche_queries, config, now, store.is_reported)
    json.dump(outliers_to_json(outliers), sys.stdout, indent=2)
    sys.stdout.write("\n")


def _cmd_mark_reported(args):
    ids = [s for s in (args.ids or sys.stdin.read()).replace(",", " ").split() if s]
    store = Store(DB_PATH)
    store.mark_reported(ids, datetime.now(timezone.utc))
    sys.stdout.write(f"marked {len(ids)} reported\n")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="outlier_scout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("anchor-profile").set_defaults(func=_cmd_anchor_profile)

    p_hunt = sub.add_parser("hunt")
    p_hunt.add_argument("--queries", help="path to niche-queries JSON (else stdin)")
    p_hunt.set_defaults(func=_cmd_hunt)

    p_mark = sub.add_parser("mark-reported")
    p_mark.add_argument("--ids", help="comma/space separated video IDs (else stdin)")
    p_mark.set_defaults(func=_cmd_mark_reported)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
