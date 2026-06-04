# outlier-scout

YouTube outlier-finder: flags videos that beat their format's median view count.

## Run
- Manual: `./venv/bin/python -m outlier_scout.run` (prints a JSON email envelope)
- Tests: `./venv/bin/python -m pytest`
- Requires `YOUTUBE_API_KEY` and `ANTHROPIC_API_KEY` in `.env`

## How it works
Weekly pipeline in `outlier_scout/`: discover channels (seed + keyword) →
fetch recent videos → score outliers per-channel by format median →
drop already-emailed IDs (sqlite) → analyze each with Claude →
render digest → a scheduled agent emails it. See
`docs/superpowers/specs/2026-06-03-youtube-outlier-research-tool-design.md`.

## Notes
- Never hardcode the API key — read from `.env`
- Never read `.env` or other secret files; use `.env.example` as the reference for what vars exist
- System Python is 3.9 (Google libs emit EOL FutureWarnings; harmless)
