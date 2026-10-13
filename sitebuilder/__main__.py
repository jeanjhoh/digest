"""CLI: python -m sitebuilder build|check|serve."""
from __future__ import annotations

import argparse
import http.server
import shutil
import sys
from pathlib import Path

from .assets import copy_static
from .checks import run_checks
from .config import BuildOptions, STATIC_DIR, TEMPLATES_DIR
from .load import load_issues, load_meta, load_sources, validate
from .model import BuildError
from .render import Renderer
from .search_index import write_search_index


def build(opts: BuildOptions) -> dict:
    meta = load_meta(opts.data_dir)
    sources = load_sources(opts.data_dir)
    issues = load_issues(opts.data_dir, meta)
    warnings = validate(meta, sources, issues, strict=opts.strict)
    if opts.out_dir.exists():
        for child in opts.out_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    versions = copy_static(opts.static_dir, opts.out_dir)
    r = Renderer(opts, meta, sources, issues, versions)
    r.render_all()
    shards = write_search_index(opts.out_dir, issues, meta.generated_at)
    n_articles = sum(i.count for i in issues)
    summary = {"issues": len(issues), "articles": n_articles, "picks": sum(len(i.picks) for i in issues),
               "pages": len(list(opts.out_dir.rglob("*.html"))), "search_files": shards, "warnings": warnings}
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sitebuilder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render the site")
    b.add_argument("--data", default="data/published")
    b.add_argument("--out", default="site")
    b.add_argument("--site-url", default=None)
    b.add_argument("--strict", action="store_true")
    b.add_argument("--check", action="store_true", help="run checks after building")
    c = sub.add_parser("check", help="run post-build checks")
    c.add_argument("site", nargs="?", default="site")
    s = sub.add_parser("serve", help="serve the built site")
    s.add_argument("site", nargs="?", default="site")
    s.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    if args.cmd == "build":
        opts = BuildOptions(data_dir=Path(args.data), out_dir=Path(args.out), site_url=args.site_url, strict=args.strict,
                            templates_dir=TEMPLATES_DIR, static_dir=STATIC_DIR)
        try:
            summary = build(opts)
        except BuildError as e:
            print(f"build failed: {e}", file=sys.stderr)
            return 2
        for w in summary["warnings"]:
            print(f"warning: {w}", file=sys.stderr)
        print(f"built {summary['pages']} pages: {summary['issues']} issues, {summary['articles']} articles, "
              f"{summary['picks']} picks -> {opts.out_dir}")
        if args.check:
            problems = run_checks(opts.out_dir)
            for p in problems:
                print(f"check: {p}", file=sys.stderr)
            return 1 if problems else 0
        return 0
    if args.cmd == "check":
        problems = run_checks(Path(args.site))
        for p in problems:
            print(f"check: {p}", file=sys.stderr)
        print("checks passed" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if args.cmd == "serve":
        root = Path(args.site).resolve()
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(root), **k)  # noqa: E731
        print(f"serving {root} at http://localhost:{args.port}/")
        http.server.ThreadingHTTPServer(("", args.port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
