# Saintapedia Media Scripts

Python scripts for fetching YouTube video metadata and creating Saintapedia wiki pages.

---

## Scripts

| Script | Purpose |
|---|---|
| `youtube_channel_videos.py` | Fetch all videos from a YouTube channel or playlist → CSV |
| `youtube_to_wiki.py` | Read that CSV → create Saintapedia wiki pages |

The typical workflow is to run script 1 first, then script 2.

---

## Setup

### 1. Prerequisites

- Python 3.10 or higher
- A [YouTube Data API v3 key](https://console.cloud.google.com/) (free, 10,000 quota units/day)
- Saintapedia bot credentials (`WIKI_BOT_USER` / `WIKI_BOT_PASS`) — required only for script 2

### 2. Create a virtual environment

```bash
git clone https://github.com/Saintapedia/media-scripts
cd media-scripts
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Add credentials to `~/.bot_secrets`

All secrets are read from `~/.bot_secrets` at runtime — nothing is hardcoded in the scripts. Add the following lines to that file (create it if it doesn't exist):

```
YOUTUBE_API_KEY=AIzaSy...
WIKI_BOT_USER=Tom@SaintapediaBot1
WIKI_BOT_PASS=your_bot_password
```

> `~/.bot_secrets` uses standard `.env` format (`KEY=value`, one per line). Never commit this file — it is listed in `.gitignore`.

---

## Script 1 — `youtube_channel_videos.py`

Fetches every video from a YouTube channel or playlist and saves metadata to a CSV file.

### Usage

```bash
# Full channel (all uploaded videos) — saves to biographies_of_the_saints.csv
venv/bin/python youtube_channel_videos.py https://www.youtube.com/channel/UCxxxxxx

# Channel by @handle
venv/bin/python youtube_channel_videos.py @BiographiesOfTheSaints

# Specific playlist URL
venv/bin/python youtube_channel_videos.py "https://www.youtube.com/watch?v=xxx&list=PLxxxxxx"

# Bare playlist ID
venv/bin/python youtube_channel_videos.py PLQn8extGJkx2GRw5qwWdRTIl3hCyxBHyc

# Multiple targets — one CSV per channel/playlist, named automatically
venv/bin/python youtube_channel_videos.py @handle1 PLxxxxxx

# Force a single combined output file
venv/bin/python youtube_channel_videos.py @handle1 @handle2 --output combined.csv

# Read targets from a text file (one per line, # = comment)
venv/bin/python youtube_channel_videos.py --file channels.txt
```

### Output

When no `--output` is specified, each channel or playlist saves to its own CSV named after the channel/playlist title (e.g. `biographies_of_the_saints.csv`). This prevents overwriting previous runs.

### CSV columns

| Column | Description |
|---|---|
| `channel_title` | Channel or playlist name |
| `channel_id` | Channel ID or playlist ID |
| `video_id` | YouTube video ID |
| `title` | Video title |
| `url` | Full YouTube watch URL |
| `published_at` | ISO 8601 publish timestamp |
| `duration` | Human-readable duration (e.g. `15:23` or `1:02:34`) |
| `view_count` | Total views |
| `like_count` | Total likes |
| `comment_count` | Total comments |
| `tags` | Pipe-separated tags (`tag1\|tag2\|...`) |
| `category_id` | YouTube category number (28 = Science & Technology, 29 = Nonprofits, etc.) |
| `description` | Full video description |

### Quota cost

Each channel/playlist fetch costs approximately `1 + ceil(videos/50)` quota units for the playlist, plus `ceil(videos/50)` units for video details. A 500-video channel uses ~20 units. The default daily quota is 10,000 units.

---

## Script 2 — `youtube_to_wiki.py`

Reads a CSV from script 1 and creates a Saintapedia wiki page for each video.

### Page format

Each video becomes a subpage titled `{Channel or Playlist Name}/{Video Title}`, with this content:

```mediawiki
{{YTV|URL=https://www.youtube.com/watch?v=xxxxx|Caption=Video Title Here}}
{{SaintMedia
|Name=Video Title Here
|Type=Video
|AuthorCreator=Biographies of the Saints
|Saint=
|SecondSaint=
|SubscriptionRequired=Free
|Length=15–30 minutes
|Language=English
|TargetAudience=Everyone
|Tags=
}}
```

`Saint=`, `SecondSaint=`, and `Tags=` are left blank and filled in manually on the wiki. `Length` is automatically bucketed from the video duration:

| Duration | Length value |
|---|---|
| Under 5 min | `Under 5 minutes` |
| 5–14 min | `5–15 minutes` |
| 15–29 min | `15–30 minutes` |
| 30–59 min | `30–60 minutes` |
| 60 min+ | `Over 60 minutes` |

### Usage

```bash
# Always dry-run a few rows first to verify output
venv/bin/python youtube_to_wiki.py biographies_of_the_saints.csv --dry-run --limit 3

# Post all videos to the wiki
venv/bin/python youtube_to_wiki.py biographies_of_the_saints.csv

# Test with a live post of just the first video
venv/bin/python youtube_to_wiki.py biographies_of_the_saints.csv --limit 1

# Resume from row 120 if the script was interrupted
venv/bin/python youtube_to_wiki.py biographies_of_the_saints.csv --start-row 120
```

### Options

| Flag | Description |
|---|---|
| `--dry-run` / `-n` | Print page titles and content without posting to the wiki |
| `--limit N` | Stop after N videos (useful for testing) |
| `--start-row N` | Skip to row N, 1-indexed (for resuming after an interruption) |
| `--quiet` / `-q` | Suppress per-page progress output |

---

## Full workflow example

```bash
# 1. Fetch all videos from a channel
venv/bin/python youtube_channel_videos.py https://www.youtube.com/channel/UCB6MR9YojquzeBvXYjiowHQ

# 2. Preview a few pages before posting
venv/bin/python youtube_to_wiki.py biographies_of_the_saints.csv --dry-run --limit 3

# 3. Post everything to Saintapedia
venv/bin/python youtube_to_wiki.py biographies_of_the_saints.csv
```
