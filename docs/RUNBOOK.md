# Outlier Scout — Runbook

## Manual run
```bash
./venv/bin/python -m outlier_scout.run
```
Prints a JSON envelope `{to, subject, html, markdown, new_count}` and writes
`data/latest_digest.json`. Requires `YOUTUBE_API_KEY` and `ANTHROPIC_API_KEY`
in `.env`.

## Weekly schedule (Sunday 08:00)
A scheduled Claude agent runs weekly and:
1. Executes `./venv/bin/python -m outlier_scout.run` from the repo root.
2. Parses the JSON envelope from stdout.
3. Sends an email to `to` with `subject` and `html` body via the Gmail
   integration.

The agent prompt is:
> Run `./venv/bin/python -m outlier_scout.run` in /Users/faisalkarnib/projects/outlier-scout.
> Parse the JSON it prints on stdout. Send an email to the `to` address with the
> `subject` and the `html` as the HTML body using the Gmail tool. If `new_count`
> is 0, still send it. Report the send result.
