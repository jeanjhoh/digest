#!/usr/bin/env python3
"""
Academic Paper Pipeline CLI.

Usage:
    python cli.py discover [--days N]       Discover new papers from target journals
    python cli.py ingest                    Ingest papers from Google Sheet (Scholar/SSRN alerts)
    python cli.py capture <DOI>             Add a paper by DOI
    python cli.py capture --manual          Add a paper manually (interactive)
    python cli.py triage [--limit N]        Score pending papers with Claude
    python cli.py promote [--threshold N]   Promote scored papers to Zotero
    python cli.py digest                    Generate a markdown digest
    python cli.py status                    Show pipeline statistics
"""

import argparse
import sys


def cmd_discover(args):
    from discover import run_discovery
    run_discovery(lookback_days=args.days)


def cmd_ingest(args):
    from ingest import run_ingest
    run_ingest()


def cmd_capture(args):
    from capture import capture_by_doi, capture_manual

    if args.manual:
        title = input("Title: ").strip()
        if not title:
            print("Title is required.")
            return
        authors = input("Authors (semicolon-separated): ").strip()
        abstract = input("Abstract (or press Enter to skip): ").strip()
        journal = input("Journal: ").strip()
        doi = input("DOI (or press Enter to skip): ").strip()
        url = input("URL (or press Enter to skip): ").strip()

        result = capture_manual(
            title=title, authors=authors, abstract=abstract,
            journal=journal, doi=doi, url=url,
        )
    else:
        if not args.doi:
            print("Provide a DOI or use --manual. See: python cli.py capture --help")
            return
        result = capture_by_doi(args.doi)

    if result["added"]:
        print(f"Added: {result.get('title', args.doi)}")
    else:
        print(f"Not added: {result.get('reason', 'unknown')}")


def cmd_triage(args):
    from triage import run_triage
    run_triage(limit=args.limit, engine=args.engine)


def cmd_promote(args):
    from promote import run_promote
    run_promote(threshold=args.threshold, select=args.select, yes=args.yes)


def cmd_digest(args):
    from digest import generate_digest
    generate_digest(include_pending=True)


def cmd_status(args):
    import database
    from database import ALL_STATUSES
    stats = database.get_stats()
    total = sum(stats.values())

    print("Paper Pipeline Status")
    print("=" * 40)
    for status in ALL_STATUSES:
        count = stats.get(status, 0)
        bar = "█" * min(count, 50) + "░" * max(0, min(20, 20 - count))
        print(f"  {status:>10}: {bar} {count}")
    print(f"  {'total':>10}: {' ' * 20} {total}")


def main():
    parser = argparse.ArgumentParser(
        description="Academic Paper Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # discover
    p_discover = subparsers.add_parser("discover", help="Discover new papers from target journals")
    p_discover.add_argument("--days", type=int, default=7, help="Lookback days (default: 7)")
    p_discover.set_defaults(func=cmd_discover)

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest papers from Google Sheet (Scholar/SSRN alerts)")
    p_ingest.set_defaults(func=cmd_ingest)

    # capture
    p_capture = subparsers.add_parser("capture", help="Add a paper by DOI or manually")
    p_capture.add_argument("doi", nargs="?", help="DOI to look up")
    p_capture.add_argument("--manual", action="store_true", help="Enter metadata manually")
    p_capture.set_defaults(func=cmd_capture)

    # triage
    p_triage = subparsers.add_parser("triage", help="Score pending papers with Claude")
    p_triage.add_argument("--limit", type=int, help="Max papers to triage")
    p_triage.add_argument("--engine", choices=["cli", "api"], default="cli",
                          help="Scoring engine: 'cli' uses claude CLI (default), 'api' uses SDK")
    p_triage.set_defaults(func=cmd_triage)

    # promote
    p_promote = subparsers.add_parser("promote", help="Promote scored papers to Zotero")
    p_promote.add_argument("--threshold", type=float, help="Min composite score")
    p_promote.add_argument("--select", "-s", type=str, help="Paper numbers to promote (e.g., 1,3,5)")
    p_promote.add_argument("--yes", "-y", action="store_true", help="Promote all above threshold")
    p_promote.set_defaults(func=cmd_promote)

    # digest
    p_digest = subparsers.add_parser("digest", help="Generate a markdown digest")
    p_digest.set_defaults(func=cmd_digest)

    # status
    p_status = subparsers.add_parser("status", help="Show pipeline statistics")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
