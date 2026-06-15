#!/usr/bin/env python3
"""
Filter a YouTube CSV (from youtube_channel_videos.py) to saint-related videos
and attempt to extract the saint name from the title.

Adds a 'saint' column which youtube_to_wiki.py will use to pre-fill Saint=.

Usage:
  # Preview matches in the terminal
  python filter_saint_videos.py sensus_fidelium.csv

  # Save matched rows to a new CSV (ready for youtube_to_wiki.py)
  python filter_saint_videos.py sensus_fidelium.csv --output sensus_saints.csv

  # Include ALL rows but annotate matches (non-matches get empty saint column)
  python filter_saint_videos.py sensus_fidelium.csv --all-rows --output annotated.csv
"""

import argparse
import csv
import re
import sys
from pathlib import Path


# Ordered from most specific to least — first match wins for name extraction
# Stop words are case-insensitive ((?i:...)) so they catch "The", "You", "Became", etc.
_STOP = (
    r"(?:\s*[-–:|,.(!'?]"
    r"|(?i:\s+(?:and|the|of|in|for|by|from|on|at|was|his|her|a|an|they|who|how|what"
    r"|why|when|we|you|is|are|she|he|it|to|so|got|not|need|have|had|did|made|went"
    r"|just|but|if|has|been|will|were|about|chose|offered|became|prayed|lived|died"
    r"|told|said|called|reveals|inspires|shows|proves|changed)\b)"
    r"|$)"
)

# Word chars allowed in a name (letters, accented chars, spaces, hyphens)
_NAME = r'[A-Za-zÀ-ÿ\s\-]{1,40}?'

SAINT_PATTERNS = [
    # "Our Lady of Guadalupe" / "Our Lady's Assumption"
    (r'\bOur Lady(?:\s+of\s+|\s*\'s?\s*)(' + _NAME + r')' + _STOP, 'Our Lady of \\1'),
    # "Saint Anthony" / "St. John" / "St.John" (no space after period)
    (r'\b(?:Saint|St\.?)\s*([A-Z]' + _NAME + r')' + _STOP, '\\1'),
    # "Blessed Margaret" / "Bl. Sandra" / "Bl.Solanus" — skip "Blessed Mother"
    (r'\b(?:Blessed\s+|Bl\.\s*)(?!Mother\b)([A-Z]' + _NAME + r')' + _STOP, 'Blessed \\1'),
    # "Venerable Matt Talbot"
    (r'\bVenerable\s+([A-Z]' + _NAME + r')' + _STOP, 'Venerable \\1'),
    # "Feast of Saint X" / "Feast of the Assumption"
    (r'\bFeast\s+of\s+(?:the\s+)?([A-Z]' + _NAME + r')' + _STOP, '\\1'),
]

SAINT_KEYWORDS = re.compile(
    r'\b(?:Saint|St\.|Bl\.|Blessed|Venerable|Our Lady|Feast of|Patroness|Patron Saint|'
    r'Holy Martyr|Confessor|Doctor of the Church|Virgin Martyr|Apostle)\b',
    re.IGNORECASE,
)


# Common English words that are never saint names — block false extractions
_NOT_A_NAME = re.compile(
    r'^(?:became|you|story|marathon|inspiration|worldwide|forgotten|need|the|a|an|'
    r'this|that|his|her|its|our|their|your|my|he|she|it|we|they|who|what|how|why|'
    r'when|where|just|so|but|and|or|not|if|as|by|in|on|at|to|up|out|off)\b',
    re.IGNORECASE,
)


def extract_saint(title: str) -> str:
    """Try to extract a saint name from the video title. Returns '' if not found."""
    # Convert titles that are mostly uppercase to title case
    alpha = [c for c in title if c.isalpha()]
    mostly_upper = alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.6
    work = title.title() if mostly_upper else title

    for pattern, replacement in SAINT_PATTERNS:
        m = re.search(pattern, work)
        if m:
            if '\\1' in replacement:
                name = m.group(1).strip().rstrip('-–,').strip()
                result = replacement.replace('\\1', name)
            else:
                result = replacement
            result = re.sub(r'\s+', ' ', result).strip()
            # Discard if too long (sentence fragment) or starts with a common word
            if len(result.split()) > 5 or _NOT_A_NAME.match(result):
                continue
            return result
    return ''


def is_saint_video(title: str) -> bool:
    return bool(SAINT_KEYWORDS.search(title))


def main():
    parser = argparse.ArgumentParser(
        description='Filter YouTube CSV to saint-related videos and extract saint names.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('csv_file', type=Path, help='CSV from youtube_channel_videos.py')
    parser.add_argument(
        '--output', '-o', type=Path, default=None,
        help='Save results to this CSV file (default: print to terminal only)',
    )
    parser.add_argument(
        '--all-rows', action='store_true',
        help='Include all rows in output, not just matches (non-matches get empty saint column)',
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress terminal summary',
    )
    args = parser.parse_args()

    if not args.csv_file.exists():
        print(f"File not found: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    rows = []
    with open(args.csv_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            rows.append(row)

    # Add 'saint' column if not already present
    out_fields = list(fieldnames)
    if 'saint' not in out_fields:
        # Insert after 'title'
        try:
            idx = out_fields.index('title') + 1
            out_fields.insert(idx, 'saint')
        except ValueError:
            out_fields.append('saint')

    matched = []
    for row in rows:
        title = row.get('title', '')
        if is_saint_video(title):
            row['saint'] = extract_saint(title)
            matched.append(row)
        else:
            row['saint'] = ''

    if not args.quiet:
        print(f"Total videos: {len(rows)}")
        print(f"Saint matches: {len(matched)}\n")
        for row in matched:
            print(f"  [{row.get('saint') or '?':40s}]  {row.get('title', '')}")

    if args.output:
        out_rows = rows if args.all_rows else matched
        with open(args.output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=out_fields)
            writer.writeheader()
            writer.writerows(out_rows)
        if not args.quiet:
            print(f"\nSaved {len(out_rows)} row(s) to {args.output}")


if __name__ == '__main__':
    main()
