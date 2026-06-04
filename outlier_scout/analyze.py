from __future__ import annotations

import json

from outlier_scout.models import Outlier, AnalyzedOutlier

MODEL = "claude-sonnet-4-6"

NICHE = (
    "The reader runs a small YouTube channel (~1,100 subscribers) making videos "
    "about gaming and psychology. They want to learn what makes outlier videos "
    "succeed and how to adapt those ideas to gaming + psychology content."
)

_SYSTEM = (
    "You analyze outlier YouTube videos for a content creator. "
    "Given a video that significantly outperformed its channel's typical views, "
    "explain why it likely succeeded and how the creator could apply the lesson "
    "to their niche. Respond ONLY with a JSON object with keys: "
    '"description" (1-2 sentences on what the video is), '
    '"why_outlier" (2-3 sentences on why it overperformed: hook, title, '
    'thumbnail, timing, emotion), '
    '"niche_application" (2-3 sentences applying the lesson to the creator).'
)


def _build_user_prompt(o: Outlier, niche: str) -> str:
    v = o.video
    return (
        f"Creator niche: {niche}\n\n"
        f"Video title: {v.title}\n"
        f"Channel: {v.channel_title}\n"
        f"Format: {o.video_format}\n"
        f"Views: {v.views:,}\n"
        f"Multiplier vs channel median: {o.multiplier}x\n"
        f"Age (days): {o.age_days}\n"
        f"Description: {v.description[:600]}\n"
    )


def _parse(text: str) -> dict:
    """Extract the first JSON object from the response, ignoring trailing prose."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in response")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def analyze_outlier(client, outlier: Outlier, niche: str) -> AnalyzedOutlier:
    """One Claude call per outlier. Retries once, then metadata-only fallback."""
    last_err = None
    for _ in range(2):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=600,
                system=[{
                    "type": "text", "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{
                    "role": "user",
                    "content": _build_user_prompt(outlier, niche),
                }],
            )
            data = _parse(resp.content[0].text)
            fields = {
                k: data.get(k)
                for k in ("description", "why_outlier", "niche_application")
            }
            if not all(isinstance(v, str) and v.strip() for v in fields.values()):
                raise ValueError("incomplete analysis fields")
            return AnalyzedOutlier(outlier=outlier, **fields)
        except Exception as e:  # noqa: BLE001 - degrade gracefully on any failure
            last_err = e
    return AnalyzedOutlier(
        outlier=outlier,
        description=outlier.video.title,
        why_outlier=f"Analysis unavailable ({last_err}).",
        niche_application="Review manually.",
    )
