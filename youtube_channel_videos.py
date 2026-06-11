#!/usr/bin/env python3
"""
Fetch all videos from YouTube channels or playlists and save to CSV.

Usage:
  # Full channel — all uploaded videos
  python youtube_channel_videos.py https://www.youtube.com/channel/UCxxxxxx
  python youtube_channel_videos.py @handle

  # Specific playlist URL
  python youtube_channel_videos.py "https://www.youtube.com/watch?v=xxx&list=PLxxxxxx"

  # Bare playlist ID
  python youtube_channel_videos.py PLQn8extGJkx2GRw5qwWdRTIl3hCyxBHyc

  # Multiple targets — one CSV per channel/playlist, named automatically
  python youtube_channel_videos.py @handle1 PLxxxxxx

  # Force a single combined output file
  python youtube_channel_videos.py @handle --output all.csv

  # Read targets from a file (one per line, # = comment)
  python youtube_channel_videos.py --file channels.txt
"""

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/.bot_secrets'))


def parse_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT1H2M3S) to H:MM:SS or M:SS string."""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration or '')
    if not match:
        return iso_duration
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def sanitize_filename(name: str) -> str:
    """Turn a title into a safe filename (no extension)."""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name.lower()


def is_playlist(identifier: str) -> bool:
    """Return True if identifier is a playlist URL or a bare PL... ID."""
    if re.search(r'[?&]list=(PL[\w-]+)', identifier):
        return True
    if re.match(r'^PL[\w-]{10,}$', identifier):
        return True
    return False


def resolve_playlist(identifier: str, api_key: str) -> tuple[str, str]:
    """
    Extract playlist ID from a URL or bare ID, then fetch the playlist title.
    Returns (playlist_id, playlist_title).
    """
    m = re.search(r'[?&]list=(PL[\w-]+)', identifier)
    playlist_id = m.group(1) if m else identifier

    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/playlists',
        params={'part': 'snippet', 'id': playlist_id, 'key': api_key},
    )
    resp.raise_for_status()
    data = resp.json()

    items = data.get('items', [])
    if not items:
        raise ValueError(f"Playlist not found: {playlist_id!r}")

    title = items[0]['snippet']['title']
    return playlist_id, title


def resolve_channel_id(identifier: str, api_key: str) -> tuple[str, str]:
    """
    Resolve a channel identifier to (channel_id, channel_title).
    Accepts: channel ID (UCxxx), @handle, /c/name URL, or /channel/UCxxx URL.
    """
    if 'youtube.com' in identifier:
        m = re.search(r'youtube\.com/channel/(UC[\w-]+)', identifier)
        if m:
            identifier = m.group(1)
        else:
            m = re.search(r'youtube\.com/@([\w.-]+)', identifier)
            if m:
                identifier = '@' + m.group(1)
            else:
                m = re.search(r'youtube\.com/c/([\w.-]+)', identifier)
                if m:
                    identifier = m.group(1)

    params = {'part': 'snippet', 'key': api_key}

    if re.match(r'^UC[\w-]{22}$', identifier):
        params['id'] = identifier
    elif identifier.startswith('@'):
        params['forHandle'] = identifier[1:]
    else:
        params['forUsername'] = identifier

    resp = requests.get('https://www.googleapis.com/youtube/v3/channels', params=params)
    resp.raise_for_status()
    data = resp.json()

    items = data.get('items', [])
    if not items:
        raise ValueError(f"Channel not found: {identifier!r}")

    item = items[0]
    return item['id'], item['snippet']['title']


def get_uploads_playlist_id(channel_id: str, api_key: str) -> str:
    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/channels',
        params={'part': 'contentDetails', 'id': channel_id, 'key': api_key},
    )
    resp.raise_for_status()
    data = resp.json()
    return data['items'][0]['contentDetails']['relatedPlaylists']['uploads']


def fetch_playlist_items(playlist_id: str, api_key: str) -> list[dict]:
    """Return [{video_id, published_at}] for every video in the playlist."""
    videos = []
    page_token = None

    while True:
        params = {
            'part': 'contentDetails,snippet',
            'playlistId': playlist_id,
            'maxResults': 50,
            'key': api_key,
        }
        if page_token:
            params['pageToken'] = page_token

        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/playlistItems', params=params
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get('items', []):
            videos.append({
                'video_id': item['contentDetails']['videoId'],
                'published_at': item['snippet'].get('publishedAt', ''),
            })

        page_token = data.get('nextPageToken')
        if not page_token:
            break

    return videos


def fetch_video_details(video_ids: list[str], api_key: str) -> dict[str, dict]:
    """Fetch full metadata for video IDs, batched in groups of 50."""
    details = {}

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params={
                'part': 'snippet,contentDetails,statistics',
                'id': ','.join(batch),
                'key': api_key,
            },
        )
        resp.raise_for_status()

        for item in resp.json().get('items', []):
            snippet = item.get('snippet', {})
            content = item.get('contentDetails', {})
            stats = item.get('statistics', {})
            details[item['id']] = {
                'title': snippet.get('title', ''),
                'description': snippet.get('description', ''),
                'published_at': snippet.get('publishedAt', ''),
                'tags': '|'.join(snippet.get('tags', [])),
                'category_id': snippet.get('categoryId', ''),
                'duration': parse_duration(content.get('duration', '')),
                'view_count': stats.get('viewCount', ''),
                'like_count': stats.get('likeCount', ''),
                'comment_count': stats.get('commentCount', ''),
            }

        if i + 50 < len(video_ids):
            time.sleep(0.05)

    return details


FIELDNAMES = [
    'channel_title', 'channel_id',
    'video_id', 'title', 'url', 'published_at', 'duration',
    'view_count', 'like_count', 'comment_count',
    'tags', 'category_id', 'description',
]


def write_videos_to_csv(
    playlist_id: str,
    label: str,
    label_id: str,
    api_key: str,
    writer: csv.DictWriter,
    verbose: bool = True,
) -> int:
    """Fetch all videos from playlist_id and write rows. label/label_id go in the CSV."""
    playlist_items = fetch_playlist_items(playlist_id, api_key)
    if verbose:
        print(f"  {len(playlist_items)} videos found, fetching details...")

    video_ids = [v['video_id'] for v in playlist_items]
    details = fetch_video_details(video_ids, api_key)

    for item in playlist_items:
        vid_id = item['video_id']
        d = details.get(vid_id, {})
        writer.writerow({
            'channel_title': label,
            'channel_id': label_id,
            'video_id': vid_id,
            'title': d.get('title', ''),
            'url': f'https://www.youtube.com/watch?v={vid_id}',
            'published_at': d.get('published_at') or item['published_at'],
            'duration': d.get('duration', ''),
            'view_count': d.get('view_count', ''),
            'like_count': d.get('like_count', ''),
            'comment_count': d.get('comment_count', ''),
            'tags': d.get('tags', ''),
            'category_id': d.get('category_id', ''),
            'description': d.get('description', ''),
        })

    if verbose:
        print(f"  Done. {len(playlist_items)} rows written.")

    return len(playlist_items)


def resolve_target(identifier: str, api_key: str) -> tuple[str, str, str]:
    """
    Resolve any identifier to (playlist_id, label, label_id).
    For channels: label = channel title, label_id = channel ID.
    For playlists: label = playlist title, label_id = playlist ID.
    """
    if is_playlist(identifier):
        playlist_id, title = resolve_playlist(identifier, api_key)
        return playlist_id, title, playlist_id
    else:
        channel_id, channel_title = resolve_channel_id(identifier, api_key)
        uploads_id = get_uploads_playlist_id(channel_id, api_key)
        return uploads_id, channel_title, channel_id


def process_target(identifier: str, api_key: str, writer: csv.DictWriter, verbose: bool) -> int:
    kind = 'Playlist' if is_playlist(identifier) else 'Channel'
    if verbose:
        print(f"\n{kind}: {identifier}")
    playlist_id, label, label_id = resolve_target(identifier, api_key)
    if verbose:
        print(f"  Resolved: {label!r}")
    return write_videos_to_csv(playlist_id, label, label_id, api_key, writer, verbose)


def main():
    parser = argparse.ArgumentParser(
        description='Fetch all videos from YouTube channels or playlists and save to CSV.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'targets', nargs='*',
        help='Channel IDs/handles/URLs or playlist IDs/URLs',
    )
    parser.add_argument(
        '--file', '-f', type=Path,
        help='Text file with one channel or playlist identifier per line (# = comment)',
    )
    parser.add_argument(
        '--api-key', '-k',
        default=os.environ.get('YOUTUBE_API_KEY'),
        help='YouTube Data API v3 key (or set YOUTUBE_API_KEY in ~/.bot_secrets)',
    )
    parser.add_argument(
        '--output', '-o', type=Path, default=None,
        help=(
            'Output CSV path. If omitted, each target saves to its own '
            '{title}.csv file in the current directory.'
        ),
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress progress output',
    )
    args = parser.parse_args()

    targets = list(args.targets)
    if args.file:
        lines = args.file.read_text(encoding='utf-8').splitlines()
        targets.extend(
            line.strip() for line in lines
            if line.strip() and not line.startswith('#')
        )

    if not args.api_key:
        parser.error('Provide --api-key or set YOUTUBE_API_KEY in ~/.bot_secrets.')
    if not targets:
        parser.error('Provide at least one channel or playlist via arguments or --file.')

    verbose = not args.quiet
    total = 0
    errors = 0

    if args.output:
        # All targets combined into one file
        with open(args.output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for identifier in targets:
                try:
                    total += process_target(identifier, args.api_key, writer, verbose)
                except requests.HTTPError as e:
                    print(f"HTTP error for {identifier!r}: {e}", file=sys.stderr)
                    errors += 1
                except ValueError as e:
                    print(f"Error for {identifier!r}: {e}", file=sys.stderr)
                    errors += 1
        if verbose:
            print(f"\nTotal: {total} videos written to {args.output}")
    else:
        # One CSV per target, named after the channel/playlist title
        for identifier in targets:
            try:
                kind = 'Playlist' if is_playlist(identifier) else 'Channel'
                if verbose:
                    print(f"\n{kind}: {identifier}")
                playlist_id, label, label_id = resolve_target(identifier, args.api_key)
                output_path = Path(sanitize_filename(label) + '.csv')
                if verbose:
                    print(f"  Resolved: {label!r}")
                    print(f"  Output:   {output_path}")
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                    writer.writeheader()
                    count = write_videos_to_csv(playlist_id, label, label_id, args.api_key, writer, verbose)
                total += count
            except requests.HTTPError as e:
                print(f"HTTP error for {identifier!r}: {e}", file=sys.stderr)
                errors += 1
            except ValueError as e:
                print(f"Error for {identifier!r}: {e}", file=sys.stderr)
                errors += 1

        if verbose:
            print(f"\nTotal: {total} videos written across {len(targets) - errors} file(s).")

    if errors:
        print(f"  {errors} target(s) failed — see errors above.", file=sys.stderr)

    sys.exit(1 if errors and total == 0 else 0)


if __name__ == '__main__':
    main()
