# YouTube Outlier Research Tool — Design Spec

**Date:** 2026-06-03
**Status:** Approved design, pre-implementation
**Owner:** Faisal Karnib (channel: gaming + psychology, ~1,100 subs)

---

## 1. Overview

A scheduled content-research tool that scouts YouTube each week for **outlier videos** — uploads that significantly overperform their own channel's typical view count — and emails the owner a digest. Each outlier is analyzed by Claude for *what made it work* and *how it applies to the owner's gaming + psychology niche*.

It is the first concrete build toward a broader "content outlier research" vision. This spec covers the **MVP only**.

## 2. Goals

- Surface genuinely notable outlier videos (Shorts and Long-form) the owner hasn't seen before.
- For each outlier, provide a short description, an analysis of *why* it outperformed, and a "how to apply to gaming + psychology" note.
- Deliver this automatically as an email digest **every Sunday at 08:00**.
- Stay inside YouTube's free API quota and modest Claude API spend.
- Be reliable and unattended — a scheduled job that just works.

## 3. Non-Goals (explicitly out of scope for MVP)

- Notion delivery (phase 2).
- Transcript / "heavy" content analysis (phase 2).
- Web UI or dashboard.
- Platforms other than YouTube.
- Multi-agent orchestration (Approach B) or a single autonomous tool-using agent (Approach C).
- Automatic tuning of thresholds or learned niche modeling.

## 4. Users & Success Criteria

**User:** a small-channel creator (gaming + psychology) using outlier research to decide what to make next.

**Success:** Each Sunday the owner receives an email containing only *new* outliers, each with a useful "why it worked / how to apply" note, with no manual effort and no duplicate reporting week-to-week.

## 5. Architecture

A single Python package run by one entrypoint (`run.py`), invoked weekly by a **scheduled Claude agent** that executes the pipeline and sends the resulting digest via the owner's connected Gmail integration.

Linear pipeline:

```
Config → Discover → Fetch → Detect outliers → Dedup → Analyze (Claude) → Assemble report → Email → Persist
```

Each stage is an isolated, independently testable module. Determinism lives in Python (quota use, math, dedup, scheduling); judgment lives in a single Claude analysis stage (Approach A).

## 6. Components

All modules live in an `outlier_scout/` package. The existing root-level `outliers.py` script is refactored into `outlier_scout/outliers.py` (the per-channel scoring module) and removed from the root, so there is a single source of truth for the math.

| Module | Responsibility | Depends on |
|---|---|---|
| `config.py` | Load `config.yaml` + API keys from `.env`. | `.env`, `config.yaml` |
| `discover.py` | Keywords → candidate channels via YouTube Search API; merge with seed list; cap at `max_channels`. | YouTube API |
| `fetch.py` | Channel → uploads playlist → recent videos within `lookback_days`; views, duration, publish date; description + thumbnail for qualifiers. | YouTube API |
| `outliers.py` | Per-channel median-per-format scoring (reuses existing logic). | — |
| `store.py` | Persistent record of already-emailed video IDs (SQLite). | local file |
| `analyze.py` | One Claude API call per new outlier (prompt caching) → description, why-outlier, niche application. | Claude API |
| `report.py` | Render digest as HTML (email) + Markdown. | — |
| `email.py` | Send digest via Gmail integration. | Gmail integration |
| `run.py` | Orchestrate all stages; entrypoint for the weekly schedule. | all of the above |

## 7. Data Flow

Keywords + seed list → candidate channels → recent videos per channel → per-channel outlier scoring → drop already-seen IDs → Claude analysis on remaining outliers → assembled digest → email → record IDs so they never repeat.

## 8. Outlier Definition

Each video is scored **against its own channel's median**, split by format:

- **Short:** duration ≤ 180s
- **Long-form:** duration > 180s
- **Baseline:** the median view count of that channel's recent videos in the same format (median, not mean).
- **Score:** `views ÷ group median`.
- **Outlier:** score ≥ `outlier_threshold` (default **2.5**).

**Minimum baseline:** a channel needs ≥ 5 recent videos in a format for its median to be trustworthy. Channels/formats below that are skipped (and noted), never scored against an unreliable baseline.

Rationale: discovery scans channels of very different sizes, so a global median would be meaningless. Per-channel scoring surfaces the true signal — "something unusual worked on *this* channel."

## 9. Configuration

`config.yaml` (committed; no secrets) holds tunable parameters:

```yaml
seed_channels:        # handles the owner already follows/competes with
  - "@SomeChannel"
keywords:             # discovery seeds
  - "gaming psychology"
  - "video game addiction"
outlier_threshold: 2.5
lookback_days: 14     # how recent a video must be to be considered
max_channels: 15      # tight MVP cap
min_videos_per_format: 5
recipient_email: "f.karnib1996@gmail.com"
```

Secrets stay in `.env` (never committed): `YOUTUBE_API_KEY`, `ANTHROPIC_API_KEY`.

## 10. Persistence

A local SQLite file (e.g., `data/reported.db`) with a table of reported video IDs + first-reported date + run timestamp. Used to (a) dedup across weeks and (b) keep a simple audit trail of what was sent.

## 11. Claude Analysis Stage

For each *new* outlier, one Claude API call (latest Sonnet/Opus, prompt caching on the shared system prompt that describes the owner's niche). Input: title, channel, views, multiplier, age, format, description, thumbnail URL. Output (structured): `description`, `why_outlier`, `niche_application`. Batched/parallelized within reason; failures retried once, then the outlier is included metadata-only.

## 12. Report & Email

`report.py` renders an HTML digest grouped by format (Long-form, then Shorts), sorted by multiplier descending. Each entry: multiplier, title (linked), channel, views, age, thumbnail, and the three Claude fields. `email.py` sends it via the Gmail integration to `recipient_email`. A week with zero new outliers still sends a short "no new outliers this week" email so the owner knows the job ran.

## 13. Scheduling

A **scheduled Claude agent** runs weekly, **Sunday 08:00**. It executes `run.py` (which produces the digest payload) and sends the email through the Gmail integration. This assumes the weekly job runs in a Claude environment with the Gmail integration connected.

*Fallback (not MVP):* fully-standalone Python email via Gmail SMTP + app password, removing the Claude-environment dependency at send time.

## 14. Error Handling

- **YouTube quota exhaustion:** stop discovery gracefully; report on what was gathered.
- **Too few videos for a channel/format:** skip with a note; never crash.
- **Claude call failure on one outlier:** retry once, then include metadata-only.
- **Zero new outliers:** send the short "ran, nothing new" email.
- **Partial-stage failures must not abort the whole run** — degrade to a smaller digest.

## 15. Testing (TDD)

- Unit tests (no network) for: median, duration parsing, per-channel scoring, minimum-baseline skipping, dedup.
- Pipeline tests with **mocked** YouTube + Claude responses covering: normal run, empty week, quota exhaustion, thin channel, Claude failure path.
- Live API calls are only exercised behind mocks in tests.

## 16. Implementation Phases (high-level)

1. **Core math, tested** — refactor existing `outliers.py` logic into a tested `outliers.py` module with per-channel scoring + minimum baseline.
2. **Fetch + config** — `config.py`, `fetch.py` (reusing current channel/playlist/video logic), `config.yaml`.
3. **Discovery** — `discover.py` (YouTube Search), capped, merged with seed list.
4. **Persistence + dedup** — `store.py` (SQLite).
5. **Claude analysis** — `analyze.py` with prompt caching + retry.
6. **Report + email** — `report.py`, `email.py` via Gmail integration.
7. **Orchestration** — `run.py` wiring all stages with error handling.
8. **Scheduling** — register the weekly Sunday 08:00 scheduled agent.

## 17. Future Phases (post-MVP)

- Notion delivery as a second output target.
- Heavy (transcript-based) analysis tier.
- Wider discovery breadth (medium/wide scale).
- Multi-agent orchestration for richer, more autonomous analysis.
- Multi-platform (TikTok, Shorts cross-posting sources, etc.).
