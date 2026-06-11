#!/usr/bin/env python3
"""
Create Saintapedia wiki pages from a YouTube channel CSV (output of youtube_channel_videos.py).

Each video becomes a subpage under the channel name:
  {Channel Title}/{Video Title}

Page content:
  {{YTV|URL=...|Caption=...}}{{SaintMedia|Name=...|Type=Video|...}}

Usage:
  # Dry run — preview page titles and content without posting
  python youtube_to_wiki.py biographies_of_the_saints.csv --dry-run

  # Post all videos to the wiki
  python youtube_to_wiki.py biographies_of_the_saints.csv

  # Test with first 5 videos only
  python youtube_to_wiki.py biographies_of_the_saints.csv --limit 5

  # Resume from a specific row (e.g. if interrupted at row 120)
  python youtube_to_wiki.py biographies_of_the_saints.csv --start-row 120
"""

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from mwclient import Site

load_dotenv(os.path.expanduser('~/.bot_secrets'))

WIKI_BOT_USER = os.getenv('WIKI_BOT_USER')
WIKI_BOT_PASS = os.getenv('WIKI_BOT_PASS')


def duration_to_length(duration: str) -> str:
    """Map a M:SS or H:MM:SS duration string to a human length range."""
    if not duration:
        return ''
    parts = duration.split(':')
    try:
        if len(parts) == 3:
            total_min = int(parts[0]) * 60 + int(parts[1])
        else:
            total_min = int(parts[0])
    except ValueError:
        return ''
    if total_min < 5:
        return 'Under 5 minutes'
    if total_min < 15:
        return '5–15 minutes'
    if total_min < 30:
        return '15–30 minutes'
    if total_min < 60:
        return '30–60 minutes'
    return 'Over 60 minutes'


def sanitize_page_title(title: str) -> str:
    """Remove characters that break MediaWiki page titles."""
    title = re.sub(r'[#<>\[\]{}|\\]', '', title)
    title = title.replace('\n', ' ').replace('\r', '')
    return title.strip()


def build_page_content(row: dict) -> str:
    title = row.get('title', '').strip()
    url = row.get('url', '').strip()
    channel = row.get('channel_title', '').strip()
    length = duration_to_length(row.get('duration', ''))

    ytv = f"{{{{YTV|URL={url}|Caption={title}}}}}"

    saint_media_lines = [
        '{{SaintMedia',
        f'|Name={title}',
        '|Type=Video',
        f'|AuthorCreator={channel}',
        '|Saint=',
        '|SecondSaint=',
        '|SubscriptionRequired=Free',
        f'|Length={length}',
        '|Language=English',
        '|TargetAudience=Everyone',
        '|Tags=',
        '}}',
    ]

    return ytv + '\n' + '\n'.join(saint_media_lines)


def connect_to_wiki(verbose: bool = True) -> Site:
    for attempt in range(3):
        try:
            site = Site('saintapedia.org', scheme='https',
                        clients_useragent='Saintapedia-YouTubeBot/1.0',
                        retry_timeout=30)
            site.login(WIKI_BOT_USER, WIKI_BOT_PASS)
            if verbose:
                print("Connected to Saintapedia wiki.")
            return site
        except Exception as e:
            print(f"Login attempt {attempt + 1} failed: {e}")
            time.sleep(8)
    print("Could not connect to wiki after 3 attempts.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Create Saintapedia wiki pages from a YouTube channel CSV.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'csv_file', type=Path,
        help='CSV file produced by youtube_channel_videos.py',
    )
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help='Print what would be posted without actually editing the wiki',
    )
    parser.add_argument(
        '--limit', type=int, default=None,
        help='Stop after processing this many videos (useful for testing)',
    )
    parser.add_argument(
        '--start-row', type=int, default=1,
        help='Skip ahead to this row number (1 = first video row, for resuming)',
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress per-page progress output',
    )
    args = parser.parse_args()

    if not args.csv_file.exists():
        print(f"File not found: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    if not WIKI_BOT_USER or not WIKI_BOT_PASS:
        print("Missing WIKI_BOT_USER or WIKI_BOT_PASS in ~/.bot_secrets", file=sys.stderr)
        sys.exit(1)

    verbose = not args.quiet

    rows = []
    with open(args.csv_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Apply --start-row (1-indexed)
    start = max(0, args.start_row - 1)
    rows = rows[start:]

    # Apply --limit
    if args.limit is not None:
        rows = rows[:args.limit]

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Processing {len(rows)} video(s)...")

    site = None if args.dry_run else connect_to_wiki(verbose)

    posted = 0
    skipped = 0
    errors = 0

    for i, row in enumerate(rows, start=args.start_row):
        channel = row.get('channel_title', '').strip()
        title = row.get('title', '').strip()

        if not title or not channel:
            print(f"  Row {i}: missing title or channel, skipping.", file=sys.stderr)
            skipped += 1
            continue

        page_title = f"{sanitize_page_title(channel)}/{sanitize_page_title(title)}"
        content = build_page_content(row)

        if args.dry_run:
            print(f"\n--- Row {i}: {page_title} ---")
            print(content)
            posted += 1
            continue

        try:
            page = site.pages[page_title]
            page.edit(content, summary='YouTube video page (YouTubeBot)')
            if verbose:
                print(f"  [{i}] Posted: {page_title}")
            posted += 1
            time.sleep(0.5)  # be polite to the wiki
        except Exception as e:
            print(f"  [{i}] ERROR posting {page_title!r}: {e}", file=sys.stderr)
            errors += 1

    label = 'previewed' if args.dry_run else 'posted'
    print(f"\nDone. {posted} {label}, {skipped} skipped, {errors} errors.")
    sys.exit(1 if errors and posted == 0 else 0)


if __name__ == '__main__':
    main()
