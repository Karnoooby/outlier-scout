# Outlier Scout — Runbook (agent-driven, no API key)

## Manual commands
```bash
./venv/bin/python -m outlier_scout.cli anchor-profile          # -> anchor profile JSON
./venv/bin/python -m outlier_scout.cli hunt --queries q.json   # -> new outliers JSON
./venv/bin/python -m outlier_scout.cli mark-reported --ids a,b # record emailed video IDs
```
Requires only `YOUTUBE_API_KEY` in `.env`.

## Weekly schedule (Sunday 08:00) — what the scheduled Claude agent does
1. Run `anchor-profile`. Read the creator's last ~12 videos.
2. Name the CORE niche; brainstorm several genuinely ADJACENT niches. Emit niche-query JSON:
   ```json
   {
     "core": {"label": "gaming psychology", "queries": ["psychology of gaming", "gaming burnout"]},
     "adjacent": [
       {"label": "digital wellness", "queries": ["dopamine detox", "phone addiction focus"]},
       {"label": "gaming video essays", "queries": ["gaming video essay"]}
     ]
   }
   ```
3. Run `hunt --queries <that json>` to get new outliers (each tagged with niche_label/niche_type).
4. RELEVANCE FILTER (judgment): drop non-English slip-throughs, faceless motivation/repost slop,
   and off-topic results. Keep instructive, on-niche videos.
5. Compose an HTML digest grouped by niche (core first, then each adjacent), each entry with:
   what it is, why it broke out, how to apply it to the creator's channel.
6. Create a Gmail DRAFT to the configured recipient (the connector cannot auto-send).
7. Run `mark-reported --ids <ids of videos you included>` so they never repeat.
8. If no outliers survive, still create a short "nothing new this week" draft.
