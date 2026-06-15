#!/usr/bin/env python3
"""
Move all subpages from one parent to another on Saintapedia.

Only the parent prefix changes — the subpage name stays identical.

Examples:
  # Dry run — see what would move without touching the wiki
  python wiki_move_pages.py "Saints" "Young Catholics" --dry-run

  # Move for real
  python wiki_move_pages.py "Saints" "Young Catholics"

  # Move without leaving redirects at the old titles
  python wiki_move_pages.py "Saints" "Young Catholics" --no-redirect
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv
from mwclient import Site

load_dotenv(os.path.expanduser('~/.bot_secrets'))

WIKI_BOT_USER = os.getenv('WIKI_BOT_USER')
WIKI_BOT_PASS = os.getenv('WIKI_BOT_PASS')


def connect_to_wiki(verbose: bool = True) -> Site:
    for attempt in range(3):
        try:
            site = Site('saintapedia.org', scheme='https',
                        clients_useragent='Saintapedia-MoveBot/1.0',
                        retry_timeout=30)
            site.login(WIKI_BOT_USER, WIKI_BOT_PASS)
            if verbose:
                print("Connected to Saintapedia wiki.")
            return site
        except Exception as e:
            print(f"Login attempt {attempt + 1} failed: {e}")
            time.sleep(8)
    print("Could not connect after 3 attempts.", file=sys.stderr)
    sys.exit(1)


def get_subpages(site: Site, parent: str) -> list[str]:
    """Return all page titles that start with parent + '/'."""
    prefix = parent + '/'
    pages = []
    for page in site.allpages(prefix=prefix):
        pages.append(page.name)
    return pages


def main():
    parser = argparse.ArgumentParser(
        description='Move all subpages from one parent to another on Saintapedia.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('from_parent', help='Current parent page (e.g. "Saints")')
    parser.add_argument('to_parent', help='New parent page (e.g. "Young Catholics")')
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help='Print moves without actually doing them',
    )
    parser.add_argument(
        '--no-redirect', action='store_true',
        help='Delete the redirect left at the old title after moving (requires suppressredirect right)',
    )
    parser.add_argument(
        '--reason', default='',
        help='Edit summary / move reason (optional)',
    )
    args = parser.parse_args()

    if not WIKI_BOT_USER or not WIKI_BOT_PASS:
        print("Missing WIKI_BOT_USER or WIKI_BOT_PASS in ~/.bot_secrets", file=sys.stderr)
        sys.exit(1)

    reason = args.reason or f'Moving subpages from "{args.from_parent}" to "{args.to_parent}"'
    prefix = args.from_parent + '/'

    site = None if args.dry_run else connect_to_wiki()

    if args.dry_run:
        # Still need to connect to list pages, but no writes happen
        site = connect_to_wiki()

    pages = get_subpages(site, args.from_parent)

    if not pages:
        print(f'No subpages found under "{args.from_parent}/".')
        sys.exit(0)

    print(f'\n{"[DRY RUN] " if args.dry_run else ""}{len(pages)} page(s) to move:\n')

    moved = 0
    errors = 0

    for old_title in pages:
        subpage = old_title[len(prefix):]          # everything after "Saints/"
        new_title = args.to_parent + '/' + subpage

        print(f'  {old_title}')
        print(f'    → {new_title}')

        if args.dry_run:
            moved += 1
            continue

        try:
            page = site.pages[old_title]
            page.move(
                new_title,
                reason=reason,
                no_redirect=args.no_redirect,
            )
            moved += 1
            time.sleep(0.5)  # be polite to the wiki
        except Exception as e:
            print(f'    ERROR: {e}', file=sys.stderr)
            errors += 1

    label = 'would move' if args.dry_run else 'moved'
    print(f'\nDone. {moved} {label}, {errors} errors.')
    sys.exit(1 if errors and moved == 0 else 0)


if __name__ == '__main__':
    main()
