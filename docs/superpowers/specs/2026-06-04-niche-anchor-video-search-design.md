# Niche-Anchor Outlier Hunt (Video-Search) — Design Spec

**Date:** 2026-06-04
**Status:** Approved design, pre-implementation
**Supersedes:** major parts of `2026-06-03-youtube-outlier-research-tool-design.md` (the per-channel, channel-discovery MVP). Builds on its validated core (per-channel format-median scoring, SQLite dedup, config/secrets split).

---

## 1. Overview

Evolve outlier-scout from *"scan a fixed list of channels for per-channel outliers"* into a **niche-anchored hunt**: anchor on the creator's own recent videos, derive their **core niche** plus several **adjacent niches**, then find **recent breakout videos** across all of them via YouTube **video search**, and email a digest grouped by niche.

The pipeline is **agent-driven** (no Anthropic API key): the weekly scheduled Claude agent does the niche expansion, relevance filtering, analysis, and email composition. Python does the deterministic, quota-sensitive work (fetch, search, per-channel baseline math, dedup).

This design was validated end-to-end by a live manual trial against the real anchor channel `@karnooby` (2026-06-04): channel-search produced thin, dead-channel results; **video-search lit up all five niches with 23 outliers in 30 days**, confirming the approach below.

## 2. Goals

- Anchor on the creator's **last N (~12) videos** to derive their *current* niche (niche drifts; recent videos define present direction).
- Surface **recent breakout videos** (≥ threshold vs their own channel's format median) across the **core niche and agent-discovered adjacent niches**.
- Deliver a weekly email digest **grouped by niche**, with each outlier analyzed for "what / why it worked / how to apply to your channel."
- Require **no Anthropic API key** — analysis and niche expansion run on the creator's Claude subscription via the scheduled agent.
- Stay inside YouTube's free quota; only report genuinely new outliers (dedup across weeks).

## 3. Non-Goals (out of scope for this iteration)

- Auto-send email (Gmail connector is **draft-only**; the agent creates a draft the user sends).
- Transcript / "heavy" content analysis.
- Platforms other than YouTube.
- A persistent/learned niche model (each run **re-derives** the niche from the latest anchor videos — intentional).
- Web UI, Notion delivery.

## 4. Architecture — agent orchestrates, Python computes

The weekly scheduled Claude agent runs this loop; Python exposes two subcommands:

```
1. [Python] anchor-profile        → JSON: anchor channel's last N videos (title, desc, tags, format, views)
2. [Agent]  read profile          → name CORE niche, brainstorm ADJACENT niches, emit labeled search queries (JSON)
3. [Python] hunt --queries <json> → per query: video-search (recent, high-view, English) → trace each video to its
                                     channel → per-channel format-median baseline → keep new outliers in the sanity
                                     band & report window → JSON, each tagged with its niche bucket
4. [Agent]  relevance-filter (drop foreign-language slip-through & faceless viral-slop), write analysis per kept
            outlier, group by niche, compose HTML, create Gmail draft
5. [Python] mark-reported <ids>   → record emailed video IDs so they never repeat
```

Determinism (quota, search, baseline math, dedup) lives in Python; judgment (niche expansion, relevance, analysis, composition) lives in the agent.

## 5. Components

All in the `outlier_scout/` package.

| Module | Responsibility | Status |
|---|---|---|
| `models.py` | dataclasses. `Outlier` gains `niche_label: str` and `niche_type: str` ("core"/"adjacent"). | modified |
| `outliers.py` | `parse_duration`, `classify_format`, `median`. Per-channel scoring helpers reused. | mostly unchanged |
| `youtube.py` | add `search_videos(query, max_results, published_after, relevance_language)`; keep `get_channel`, `get_recent_videos`, `_hydrate`. Remove `search_channels`. | modified |
| `anchor.py` | `fetch_anchor_videos(client, handle, count)` — the channel's most recent N uploads (by count, not date). | new |
| `hunt.py` | `hunt(client, niche_queries, config, now, is_reported)` — video-search → per-channel baseline (cached) → outlier decision (threshold ≤ mult ≤ ceiling, within report window, format has ≥ min videos, not already reported) → list of `Outlier` tagged by niche. | new |
| `store.py` | SQLite dedup by video ID. `is_reported`, `mark_reported`. | unchanged |
| `config.py` | new fields (see §7); **drop `ANTHROPIC_API_KEY` requirement**. | modified |
| `cli.py` (`run.py` replaced) | subcommands: `anchor-profile`, `hunt`, `mark-reported`. Each reads/writes JSON on stdout. | replaced |
| ~~`discover.py`~~ | channel-search discovery — **removed** (superseded by `hunt` video-search). | removed |
| ~~`analyze.py`~~ | API analysis — **removed** (agent does analysis). | removed |
| ~~`report.py`~~ | HTML rendering — **removed** (agent composes the email). | removed |

## 6. Outlier definition (refined)

A candidate video is an outlier when **all** hold:
- It was found by a niche query's **video search** (recent, ordered by view count, `relevanceLanguage="en"`).
- Its **channel** is not the anchor channel.
- Its **format** ("Short" ≤180s / "Long" >180s) has ≥ `min_videos_per_format` videos in the channel's recent sample (else the baseline is untrustworthy → skip).
- `multiplier = views ÷ channel's format median`, and **`outlier_threshold ≤ multiplier ≤ outlier_ceiling`** (the ceiling is a sanity band that drops faceless lottery channels whose near-zero baselines produce 300×+ flukes).
- Published within `report_window_days`.
- Not already reported (dedup store).

Each outlier carries the `niche_label` / `niche_type` of the query that surfaced it. The agent applies a final relevance pass (judgment) before anything reaches the digest.

## 7. Configuration

```yaml
anchor_channel: "@karnooby"      # the creator's channel — defines the niche
anchor_video_count: 12           # last N uploads used to derive the niche
adjacent_hints: []               # optional: nudge specific adjacent niches (agent may add its own)
report_window_days: 7            # only report videos newer than this
lookback_days: 90                # window used to build each channel's baseline
max_videos_per_query: 8          # video-search results requested per query
relevance_language: "en"         # filter search to this language
outlier_threshold: 2.5           # min multiplier vs channel format median
outlier_ceiling: 80              # max multiplier (drops lottery/faceless slop)
min_videos_per_format: 3         # skip a format with fewer recent videos
recipient_email: "f.karnib1996@gmail.com"
```

Secrets: only `YOUTUBE_API_KEY` in `.env`. **No `ANTHROPIC_API_KEY`.**

## 8. Quota

YouTube `search.list` costs **100 units/call**. A run with ~8–12 niche queries ≈ 800–1,200 units for discovery, plus ~1 unit per video-hydration batch and ~3–4 units per unique channel baseline fetch — comfortably within the 10,000 units/day free quota. `hunt` caches each channel's baseline so a channel reached by multiple queries is fetched once.

## 9. Error handling

- `HttpError` (quota 403 / 5xx) during search → stop that niche's search gracefully, keep what was gathered (carry over existing behavior).
- A candidate video whose channel baseline can't be fetched, or whose format is too thin → skip that video, never crash.
- Foreign-language results that slip past `relevanceLanguage` → the agent drops them in the relevance pass.
- Empty result (no new outliers) → the agent still composes a short "nothing new this week" draft.

## 10. The agent runbook

`docs/RUNBOOK.md` documents the exact weekly agent procedure, including:
- The niche-query JSON schema the agent emits (core + adjacent, each with label + queries).
- Relevance-filter rules (drop non-English, faceless motivation/repost slop, and off-topic results; keep instructive, on-niche videos).
- Compose HTML digest grouped by niche; create a Gmail **draft** to `recipient_email`; then call `mark-reported` with the included video IDs.

## 11. Testing (TDD)

- `anchor.py`: returns the most recent N videos (mocked client).
- `youtube.search_videos`: thin wrapper — smoke/light coverage (real API exercised live, like the rest of `youtube.py`).
- `hunt.py` (core logic, with an extended `FakeYouTubeClient` providing `search_videos` + `_hydrate`):
  - keeps a video at/above threshold; drops one below.
  - drops a video **above the ceiling** (lottery guard).
  - drops a video **outside the report window**.
  - skips a format with **< min_videos_per_format**.
  - excludes the **anchor channel**.
  - filters **already-reported** videos.
  - caches a channel baseline fetched via two queries (fetched once).
  - tags each outlier with the correct niche label/type.
- `store.py`: dedup unchanged (existing tests).
- `config.py`: loads new fields; no longer requires `ANTHROPIC_API_KEY` (existing tests updated).

## 12. Migration & removals

- Delete `outlier_scout/analyze.py`, `outlier_scout/report.py`, `outlier_scout/discover.py` and their tests.
- Replace `outlier_scout/run.py` with a subcommand CLI (`anchor-profile`, `hunt`, `mark-reported`).
- Update `config.py` (new fields, drop Anthropic key), `models.py` (niche fields), `youtube.py` (add `search_videos`, drop `search_channels`).
- Update `CLAUDE.md`, `config.yaml`, `.env.example` (remove `ANTHROPIC_API_KEY`), and `docs/RUNBOOK.md`.
- Update the schedule registration to the new agent runbook (operator action).

## 13. Future phases

- Auto-send (standalone SMTP path) if the user wants zero-touch delivery.
- Transcript-based "heavy" analysis tier.
- Notion delivery; broader discovery breadth; multi-anchor niche definition.
