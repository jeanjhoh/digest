"""Post-build assertions. ``python -m sitebuilder check site``."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .config import BUDGETS


class CheckError(Exception):
    pass


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.h1 = 0
        self.coins = 0
        self.lang = False
        self.viewport = False
        self.canonical = False
        self.details_open = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = True
        if tag == "h1":
            self.h1 += 1
        if tag == "span" and "Z3988" in (a.get("class") or "").split():
            self.coins += 1
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = True
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = True
        for k in ("href", "src"):
            v = a.get(k)
            if v:
                self.links.append(v)
        if tag == "details":
            self.details_open += 1

    def handle_endtag(self, tag):
        if tag == "details":
            self.details_open -= 1


def _is_internal(href: str) -> bool:
    if not href or href.startswith(("#", "mailto:", "javascript:", "data:")):
        return False
    u = urlsplit(href)
    return not u.scheme and not u.netloc


def run_checks(site_dir: Path) -> list[str]:
    """Return a list of problems (empty = pass)."""
    problems: list[str] = []
    html_files = sorted(site_dir.rglob("*.html"))
    if not html_files:
        return [f"no HTML files in {site_dir}"]
    issues_dir = site_dir / "data" / "issues"
    issue_counts = {}
    for f in sorted(issues_dir.glob("*.json")) if issues_dir.is_dir() else []:
        d = json.loads(f.read_text(encoding="utf-8"))
        issue_counts[int(d["number"])] = len(d.get("articles") or [])
    index_html = (site_dir / "index.html").read_text(encoding="utf-8")
    m = re.search(r'data-issue-number="(\d+)"', index_html)
    latest = int(m.group(1)) if m else None

    for f in html_files:
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(site_dir).as_posix()
        p = _LinkParser()
        p.feed(text)
        if p.h1 != 1:
            problems.append(f"{rel}: expected one <h1>, found {p.h1}")
        if not p.lang:
            problems.append(f"{rel}: <html> has no lang")
        if not p.viewport:
            problems.append(f"{rel}: no viewport meta")
        if not p.canonical:
            problems.append(f"{rel}: no canonical link")
        if p.details_open != 0:
            problems.append(f"{rel}: unbalanced <details>")
        if "{{" in text or "}}" in text:
            problems.append(f"{rel}: template delimiter leaked")
        if re.search(r">\s*None\s*<", text):
            problems.append(f"{rel}: literal None leaked")
        # COinS count on issue pages
        mi = re.search(r'data-page="issue"[^>]*data-issue-number="(\d+)"', text)
        if mi:
            n = int(mi.group(1))
            expected = issue_counts.get(n)
            if expected is not None and p.coins != expected:
                problems.append(f"{rel}: {p.coins} COinS spans but issue {n} has {expected} articles")
        # internal links
        for href in p.links:
            if not _is_internal(href):
                continue
            path = unquote(urlsplit(href).path)
            if not path:
                continue
            target = (f.parent / path).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                problems.append(f"{rel}: broken link {href}")
    for name in ("rss.xml", "feed-papers.xml", "sitemap.xml"):
        fp = site_dir / name
        if not fp.exists():
            problems.append(f"missing {name}")
            continue
        try:
            ET.parse(fp)
        except ET.ParseError as e:
            problems.append(f"{name}: XML parse error: {e}")
    for name, budget in BUDGETS.items():
        fp = site_dir / name
        if fp.exists() and fp.stat().st_size > budget:
            problems.append(f"{name}: {fp.stat().st_size} bytes exceeds budget {budget}")
    for name in ("llms.html", "llms.txt", "details.html", "about.html", "404.html", "robots.txt", ".nojekyll"):
        if not (site_dir / name).exists():
            problems.append(f"missing {name}")
    if latest is None:
        problems.append("index.html has no data-issue-number")
    return problems
