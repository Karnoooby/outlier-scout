# outlier-scout

YouTube outlier-finder: flags videos that beat their format's median view count.

## Run
- Always use the venv: `./venv/bin/python outliers.py @ChannelHandle`
- Requires `YOUTUBE_API_KEY` in `.env` (copy from `.env.example`)

## How it works (outliers.py)
- Resolves @handle → uploads playlist → 50 most recent videos
- Splits into Shorts (≤180s) vs Long-form (>180s)
- Baseline = MEDIAN views per group (not mean)
- Score = views ÷ group median; prints videos ≥ 2.5×, sorted desc

## Notes
- Never hardcode the API key — read from `.env`
- Never read `.env` or other secret files; use `.env.example` as the reference for what vars exist
- System Python is 3.9 (Google libs emit EOL FutureWarnings; harmless)
