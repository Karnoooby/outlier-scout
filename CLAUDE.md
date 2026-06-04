# outlier-scout

YouTube outlier-finder: flags videos that beat their format's median view count.

## Run
- Anchor profile: `./venv/bin/python -m outlier_scout.cli anchor-profile`
- Hunt: `./venv/bin/python -m outlier_scout.cli hunt --queries q.json`
- Mark reported: `./venv/bin/python -m outlier_scout.cli mark-reported --ids a,b`
- Tests: `./venv/bin/python -m pytest`
- Requires only `YOUTUBE_API_KEY` in `.env` (no Anthropic key — analysis is agent-driven)

## How it works
Agent-driven niche-anchor hunt: Python returns the creator's recent videos
(`anchor-profile`); the scheduled Claude agent derives core + adjacent niches and
emits search queries; `hunt` video-searches recent breakouts, confirms each against
its own channel's format-median baseline (within a sanity band + report window),
dedups, and returns tagged outliers; the agent relevance-filters, analyzes, and
emails a Gmail draft, then calls `mark-reported`. See
`docs/superpowers/specs/2026-06-04-niche-anchor-video-search-design.md` and `docs/RUNBOOK.md`.

## Notes
- Never hardcode the API key — read from `.env`
- Never read `.env` or other secret files; use `.env.example` as the reference for what vars exist
- System Python is 3.9 (Google libs emit EOL FutureWarnings; harmless)
