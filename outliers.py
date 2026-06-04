"""
YouTube Outlier Finder
----------------------
Finds videos that significantly outperform the channel median for their format
(Shorts vs Long-form). Run with: python outliers.py @ChannelHandle
"""

import sys
import re
import statistics
from datetime import datetime, timezone

from dotenv import load_dotenv
import os
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# 1. Load API key from .env — never hardcode
# ---------------------------------------------------------------------------
load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")
if not API_KEY:
    sys.exit("Error: YOUTUBE_API_KEY not found. Copy .env.example to .env and add your key.")

# ---------------------------------------------------------------------------
# 2. Parse command-line argument
# ---------------------------------------------------------------------------
if len(sys.argv) < 2:
    sys.exit("Usage: python outliers.py @ChannelHandle")

handle = sys.argv[1]
if not handle.startswith("@"):
    sys.exit("Channel handle must start with @, e.g. @GirlfriendReviews")

# ---------------------------------------------------------------------------
# Build the YouTube Data API v3 client
# ---------------------------------------------------------------------------
youtube = build("youtube", "v3", developerKey=API_KEY)

# ---------------------------------------------------------------------------
# 3. Resolve the channel handle → uploads playlist ID
# ---------------------------------------------------------------------------
print(f"Looking up channel: {handle}")
search_resp = youtube.channels().list(
    part="contentDetails,snippet",
    forHandle=handle.lstrip("@"),   # API wants handle without the @
).execute()

items = search_resp.get("items", [])
if not items:
    sys.exit(f"Channel '{handle}' not found. Check the handle and try again.")

channel_title = items[0]["snippet"]["title"]
uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
print(f"Channel : {channel_title}")
print(f"Playlist: {uploads_playlist_id}")

# ---------------------------------------------------------------------------
# 4. Fetch the 50 most-recent video IDs from the uploads playlist
# ---------------------------------------------------------------------------
MAX_VIDEOS = 50
video_ids = []
next_page = None

while len(video_ids) < MAX_VIDEOS:
    playlist_resp = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=min(50, MAX_VIDEOS - len(video_ids)),
        pageToken=next_page,
    ).execute()

    for item in playlist_resp["items"]:
        video_ids.append(item["contentDetails"]["videoId"])

    next_page = playlist_resp.get("nextPageToken")
    if not next_page:
        break

print(f"Fetched {len(video_ids)} video IDs")

# ---------------------------------------------------------------------------
# Helper: parse ISO 8601 duration (e.g. PT4M13S) → total seconds
# ---------------------------------------------------------------------------
def parse_duration(iso: str) -> int:
    """Convert ISO 8601 duration string to total seconds."""
    match = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso
    )
    if not match:
        return 0
    hours   = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds

# ---------------------------------------------------------------------------
# 4 (cont.). Fetch view counts, publish dates, and durations in batches of 50
# ---------------------------------------------------------------------------
videos = []
now = datetime.now(timezone.utc)

for batch_start in range(0, len(video_ids), 50):
    batch = video_ids[batch_start : batch_start + 50]
    details_resp = youtube.videos().list(
        part="statistics,contentDetails,snippet",
        id=",".join(batch),
    ).execute()

    for item in details_resp.get("items", []):
        vid_id    = item["id"]
        title     = item["snippet"]["title"]
        published = datetime.fromisoformat(
            item["snippet"]["publishedAt"].replace("Z", "+00:00")
        )
        age_days  = (now - published).days
        views     = int(item["statistics"].get("viewCount", 0))
        duration_s = parse_duration(item["contentDetails"]["duration"])

        videos.append({
            "id":         vid_id,
            "title":      title,
            "views":      views,
            "age_days":   age_days,
            "duration_s": duration_s,
        })

print(f"Retrieved details for {len(videos)} videos\n")

# ---------------------------------------------------------------------------
# 5. Classify each video as Short (≤ 180 s) or Long-form (> 180 s)
# ---------------------------------------------------------------------------
SHORTS_THRESHOLD = 180  # seconds

shorts    = [v for v in videos if v["duration_s"] <= SHORTS_THRESHOLD]
long_form = [v for v in videos if v["duration_s"] >  SHORTS_THRESHOLD]

# ---------------------------------------------------------------------------
# 6. Compute the MEDIAN view count for each group
# ---------------------------------------------------------------------------
def safe_median(group):
    """Return median views, or None if the group is empty."""
    counts = [v["views"] for v in group]
    return statistics.median(counts) if counts else None

shorts_median    = safe_median(shorts)
long_form_median = safe_median(long_form)

# ---------------------------------------------------------------------------
# 7. Score each video: views ÷ group median
# ---------------------------------------------------------------------------
OUTLIER_THRESHOLD = 2.5  # show videos at 2.5× or above

def score_group(group, median):
    if median is None or median == 0:
        return []
    for v in group:
        v["score"] = v["views"] / median
    return group

score_group(shorts,    shorts_median)
score_group(long_form, long_form_median)

# ---------------------------------------------------------------------------
# 8. Collect outliers (score ≥ 2.5) and sort highest first
# ---------------------------------------------------------------------------
outliers = [
    v for v in shorts + long_form
    if v.get("score", 0) >= OUTLIER_THRESHOLD
]
outliers.sort(key=lambda v: v["score"], reverse=True)

# ---------------------------------------------------------------------------
# 9. Print results
# ---------------------------------------------------------------------------
print("=" * 70)
print(f"BASELINES for {channel_title}")
print("-" * 70)
if long_form_median is not None:
    print(f"  Long-form ({len(long_form)} videos)  median views: {long_form_median:,.0f}")
else:
    print("  Long-form: no videos found")

if shorts_median is not None:
    print(f"  Shorts    ({len(shorts)} videos)  median views: {shorts_median:,.0f}")
else:
    print("  Shorts: no videos found")

print(f"\nVideos scanned : {len(videos)}")
print(f"Outliers (≥{OUTLIER_THRESHOLD}×): {len(outliers)}")
print("=" * 70)

if not outliers:
    print("No outliers found at this threshold.")
else:
    print(f"\n{'MULT':>6}  {'VIEWS':>10}  {'AGE':>6}  TITLE")
    print("-" * 70)
    for v in outliers:
        fmt = "Short" if v["duration_s"] <= SHORTS_THRESHOLD else "Long "
        print(
            f"  {v['score']:>4.1f}×  {v['views']:>10,}  {v['age_days']:>5}d  "
            f"[{fmt}] {v['title']}"
        )

print()
