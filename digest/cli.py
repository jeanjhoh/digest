"""python -m digest <command>"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .settings import load_settings


def cmd_run(args: argparse.Namespace) -> int:
    from .pipeline import run
    s = load_settings()
    sources = [x.strip() for x in args.sources.split(",")] if args.sources else None
    stats = run(s, days=args.days, dry_run=args.dry_run, no_llm=args.no_llm, llm_limit=args.llm_limit,
                sources=sources, bootstrap=args.bootstrap)
    if stats.seen == 0 and not sources:
        print("error: no records seen from any source", file=sys.stderr)
        return 2
    enabled = [x for x in s.sources if x.enabled and (not sources or x.slug in sources)]
    if enabled and len(stats.errors) > len(enabled) / 2:
        print("error: more than half of the sources failed", file=sys.stderr)
        return 2
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from datetime import timedelta
    from .models import utcnow
    from .normalize import is_front_matter
    from .pipeline import Context, Window
    from .sources import REGISTRY
    from .sources.http import build_http
    s = load_settings()
    ctx = Context(settings=s, http=build_http(s))
    now = utcnow()
    window = Window(start=now - timedelta(days=args.days), end=now)
    for slug in args.sources.split(","):
        src = s.source(slug.strip())
        if not src:
            print(f"unknown source {slug}", file=sys.stderr)
            continue
        recs = REGISTRY[src.kind](src, window, ctx)
        print(f"== {src.slug}: {len(recs)} records")
        for r in recs:
            fm, reason = is_front_matter(r)
            flag = f"[FILTERED {reason}]" if fm else ""
            print(f"  {r.published_at or '----------'}  {(r.doi or r.arxiv_id or r.repec_handle or '-'):40s} "
                  f"{r.title[:80]} {flag}  abstract={'yes' if r.abstract else 'no'}")
    return 0


def cmd_sources_check(args: argparse.Namespace) -> int:
    from .sources.crossref import check_journal
    from .sources.http import build_http
    s = load_settings()
    http = build_http(s)
    bad = 0
    for src in s.sources:
        if src.kind != "crossref_journal":
            print(f"  {src.slug:14s} {src.kind:16s} (not a journal; skipped)")
            continue
        for issn in src.issn:
            info = check_journal(http, issn)
            if info and info.get("ok"):
                title = info.get("title") or ""
                ok = "ok " if title.lower()[:12] == src.name.lower()[:12] or src.name.lower() in title.lower() else "ok?"
                print(f"  {src.slug:14s} {issn}  {ok} {title}")
            else:
                bad += 1
                print(f"  {src.slug:14s} {issn}  FAIL {info.get('error') if info else ''}")
    print(f"{bad} failing ISSNs")
    return 1 if bad else 0


def cmd_status(args: argparse.Namespace) -> int:
    from .issues import Issues
    from .store import Store
    s = load_settings()
    store = Store.load(s.data_dir)
    issues = Issues.load(s.data_dir)
    if args.latest_issue:
        print(issues.latest.number if issues.latest else 0)
        return 0
    print(f"{len(store)} articles; {sum(1 for a in store if a.candidate)} candidates; "
          f"{sum(1 for a in store if a.classification)} classified; {sum(1 for a in store if a.in_scope)} in scope")
    for i in issues.items:
        print(f"  Issue {i.number:3d} {i.key} cutoff {i.cutoff_at[:10]}  {i.counts}")
    runs = Path(s.data_dir) / "runs.jsonl"
    if runs.exists():
        last = [json.loads(l) for l in runs.read_text().splitlines() if l.strip()][-1]
        print(f"last run {last['run_id']}: seen {sum(v['seen'] for v in last['sources'].values())}, "
              f"errors {len(last['errors'])}, llm {last.get('llm')}")
    return 0


def cmd_add_doi(args: argparse.Namespace) -> int:
    from .models import iso, utcnow
    from .normalize import is_front_matter
    from .settings import Source
    from .sources.crossref import resolve_doi
    from .sources.http import build_http
    from .store import Store
    s = load_settings()
    src = Source(slug="manual", name="Manual capture", kind="manual", category="alert", tier="A", always_candidate=True)
    rec = resolve_doi(build_http(s), args.doi, src)
    if rec is None:
        print("DOI not found on Crossref", file=sys.stderr)
        return 1
    fm, reason = is_front_matter(rec)
    if fm:
        print(f"Looks like front matter ({reason}); not added", file=sys.stderr)
        return 1
    store = Store.load(s.data_dir)
    a, how = store.upsert(rec, "alert", iso(utcnow()))
    a.keyword = {"scores": {}, "reasons": {}, "max": 0, "candidate": True, "basis": "manual"}
    store.save()
    print(f"{how}: {a.key} — {a.title}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from .publish import publish
    s = load_settings()
    out = publish(s, out_dir=Path(args.out) if args.out else None)
    print(f"published to {out}")
    return 0


def cmd_commit_message(args: argparse.Namespace) -> int:
    s = load_settings()
    runs = Path(s.data_dir) / "runs.jsonl"
    if not runs.exists():
        print("Pipeline run")
        return 0
    last = [json.loads(l) for l in runs.read_text().splitlines() if l.strip()][-1]
    seen = sum(v["seen"] for v in last["sources"].values())
    print(f"Issue {last.get('issue_number')}: {last.get('in_scope')} in scope / {seen} seen ({last['run_id'][:10]})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="digest")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch, classify, assign issue, persist")
    r.add_argument("--days", type=int)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--no-llm", action="store_true")
    r.add_argument("--llm-limit", type=int, help="max LLM batches")
    r.add_argument("--sources", help="comma-separated slugs")
    r.add_argument("--bootstrap", action="store_true", help="first run: 14-day window")
    r.set_defaults(func=cmd_run)
    f = sub.add_parser("fetch", help="fetch sources and print records (no writes)")
    f.add_argument("--sources", required=True)
    f.add_argument("--days", type=int, default=8)
    f.set_defaults(func=cmd_fetch)
    sc = sub.add_parser("sources", help="source utilities")
    scs = sc.add_subparsers(dest="sub", required=True)
    scc = scs.add_parser("check", help="resolve every ISSN on Crossref")
    scc.set_defaults(func=cmd_sources_check)
    st = sub.add_parser("status")
    st.add_argument("--latest-issue", action="store_true")
    st.set_defaults(func=cmd_status)
    ad = sub.add_parser("add-doi")
    ad.add_argument("doi")
    ad.set_defaults(func=cmd_add_doi)
    pb = sub.add_parser("publish", help="write data/published/*")
    pb.add_argument("--out")
    pb.set_defaults(func=cmd_publish)
    cm = sub.add_parser("commit-message")
    cm.set_defaults(func=cmd_commit_message)
    args = p.parse_args(argv)
    return args.func(args)
