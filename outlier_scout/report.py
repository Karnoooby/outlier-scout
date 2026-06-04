from __future__ import annotations

from datetime import datetime
from html import escape
from typing import List

from outlier_scout.models import AnalyzedOutlier, Digest


def _safe_url(url: str) -> str:
    """Only allow http(s) links in the rendered HTML; neutralize anything else."""
    return url if url.startswith(("https://", "http://")) else "#"


def _entry_html(a: AnalyzedOutlier) -> str:
    o, v = a.outlier, a.outlier.video
    return (
        f'<div style="margin:0 0 24px;padding:16px;border:1px solid #eee;border-radius:8px">'
        f'<h3 style="margin:0 0 8px"><a href="{escape(_safe_url(v.url))}">{escape(v.title)}</a> '
        f'<span style="color:#c00">{o.multiplier}x</span></h3>'
        f'<p style="margin:0 0 8px;color:#555">{escape(v.channel_title)} &middot; '
        f'{v.views:,} views &middot; {o.age_days}d old &middot; {o.video_format}</p>'
        f'<img src="{escape(v.thumbnail_url)}" alt="" style="max-width:320px;border-radius:6px"><br>'
        f'<p><b>What:</b> {escape(a.description)}</p>'
        f'<p><b>Why it worked:</b> {escape(a.why_outlier)}</p>'
        f'<p><b>Apply to your niche:</b> {escape(a.niche_application)}</p>'
        f'</div>'
    )


def _entry_md(a: AnalyzedOutlier) -> str:
    o, v = a.outlier, a.outlier.video
    return (
        f"### [{v.title}]({v.url}) — {o.multiplier}x\n"
        f"{v.channel_title} · {v.views:,} views · {o.age_days}d · {o.video_format}\n\n"
        f"- **What:** {a.description}\n"
        f"- **Why it worked:** {a.why_outlier}\n"
        f"- **Apply to your niche:** {a.niche_application}\n"
    )


def render_digest(analyzed: List[AnalyzedOutlier], now: datetime) -> Digest:
    date = now.strftime("%Y-%m-%d")
    ordered = sorted(analyzed, key=lambda a: a.outlier.multiplier, reverse=True)

    if not ordered:
        subject = f"Outlier Scout — no new outliers ({date})"
        html = "<p>No new outliers this week. The scout ran successfully.</p>"
        markdown = "No new outliers this week. The scout ran successfully.\n"
        return Digest(subject=subject, html=html, markdown=markdown, new_count=0)

    subject = f"Outlier Scout — {len(ordered)} new outlier(s) ({date})"
    html = (
        f"<h2>Outlier Scout digest — {date}</h2>"
        + "".join(_entry_html(a) for a in ordered)
    )
    markdown = (
        f"# Outlier Scout digest — {date}\n\n"
        + "\n".join(_entry_md(a) for a in ordered)
    )
    return Digest(subject=subject, html=html, markdown=markdown,
                  new_count=len(ordered))
