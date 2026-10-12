"""Jinja2 environment and page renderers."""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import cite
from .config import BOOTSTRAP_ICONS_CSS, BuildOptions, PAPER_FEED_LIMIT, PICKS_CAP
from .model import Article, Issue, Meta, Source, for_you, group_issue, slugify_key


def _date_long(v):
    if not v:
        return ""
    try:
        d = dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return str(v)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _date_short(v):
    return str(v)[:10] if v else ""


def _rfc822(v):
    if not v:
        v = dt.datetime.now(dt.timezone.utc).isoformat()
    s = str(v)
    try:
        if len(s) == 10:
            d = dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    return d.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _authors_inline(names):
    return ", ".join(names)


def _jsonify(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def _truncate(s, n=400):
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def make_env(templates_dir: Path) -> Environment:
    env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update({"date_long": _date_long, "date_short": _date_short, "rfc822": _rfc822,
                        "authors_inline": _authors_inline, "jsonify": _jsonify, "truncate_text": _truncate})
    return env


class Renderer:
    def __init__(self, opts: BuildOptions, meta: Meta, sources: dict[str, Source], issues: list[Issue],
                 versions: dict[str, str]):
        self.opts = opts
        self.meta = meta
        self.sources = sources
        self.issues = issues
        self.versions = versions
        self.env = make_env(opts.templates_dir)
        self.site_url = (opts.site_url or meta.site.get("url") or "./").rstrip("/") + "/"
        self.meta.site["url"] = self.site_url
        self.all_articles: list[Article] = []
        self._enrich()

    # ------------------------------------------------------------------ data
    def _enrich(self) -> None:
        slugs: set[str] = set()
        for issue in self.issues:
            for a in issue.articles:
                a.slug = slugify_key(a.canonical_key)
                if a.slug in slugs:
                    a.slug = f"{a.slug}-{issue.number}"
                slugs.add(a.slug)
                a.set_labels = [self.meta.set_label(s, short=True) for s in a.sets]
                a.status_label = self.meta.status_label(a.publication_status)
                a.link = a.paper_url or a.primary_url or (f"https://doi.org/{a.doi}" if a.doi else "")
                src = self.sources.get(a.source_slug)
                a.issn = src.issn[0] if src and src.issn else None
                if a.year is None and a.published_at:
                    try:
                        a.year = int(str(a.published_at)[:4])
                    except ValueError:
                        pass
                a.coins = cite.coins_kev(a)
                a.bibtex = cite.bibtex(a)
                a.plain_citation = cite.plain_citation(a)
                self.all_articles.append(a)
            # ordinals follow display order: category (meta order) -> source (name) -> score
            n = 0
            for g in group_issue(issue, self.sources, self.meta):
                for s in g["sources"]:
                    for a in s["articles"]:
                        n += 1
                        a.ordinal = n

    # --------------------------------------------------------------- helpers
    def _ctx(self, depth: int, **extra) -> dict:
        rel = "../" * depth
        return {
            "site": self.meta.site, "meta": self.meta, "sources": self.sources, "issues": self.issues,
            "latest": self.issues[-1], "rel": rel, "site_url": self.site_url, "versions": self.versions,
            "icons_css": BOOTSTRAP_ICONS_CSS, "now_year": dt.datetime.now().year,
            "generated_at": self.meta.generated_at, **extra,
        }

    def _write(self, rel_path: str, template: str, ctx: dict) -> None:
        out = self.opts.out_dir / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.env.get_template(template).render(**ctx), encoding="utf-8")

    def _issue_ctx(self, issue: Issue, depth: int, is_index: bool) -> dict:
        groups = group_issue(issue, self.sources, self.meta)
        picks = for_you(issue, PICKS_CAP)
        set_counts = {s: sum(1 for a in issue.articles if s in a.sets) for s in self.meta.set_ids}
        idx = next(i for i, x in enumerate(self.issues) if x.number == issue.number)
        prev_issue = self.issues[idx - 1] if idx > 0 else None
        next_issue = self.issues[idx + 1] if idx + 1 < len(self.issues) else None
        embedded = [a.to_public_dict() for a in issue.articles]
        return self._ctx(depth, page="issue", issue=issue, groups=groups, picks=picks, set_counts=set_counts,
                         prev_issue=prev_issue, next_issue=next_issue, is_index=is_index, embedded=embedded,
                         canonical=self.site_url + ("" if is_index else f"issues/{issue.number:03d}.html"),
                         title=f"Issue {issue.label} · {self.meta.site['title']}")

    # ----------------------------------------------------------------- pages
    def render_all(self) -> None:
        latest = self.issues[-1]
        self._write("index.html", "issue.html", self._issue_ctx(latest, 0, True))
        for issue in self.issues:
            self._write(f"issues/{issue.number:03d}.html", "issue.html", self._issue_ctx(issue, 1, False))
        self._write("issues/index.html", "issues_index.html",
                    self._ctx(1, page="issues", canonical=self.site_url + "issues/", title=f"Issues · {self.meta.site['title']}"))
        for issue in self.issues:
            for a in issue.articles:
                self._write(f"p/{a.slug}.html", "paper.html",
                            self._ctx(1, page="paper", article=a, issue=issue, highwire=cite.highwire_meta(a),
                                      canonical=f"{self.site_url}p/{a.slug}.html", title=f"{a.title} · {self.meta.site['title']}"))
        by_cat: dict[str, list[Source]] = {}
        for s in sorted(self.sources.values(), key=lambda s: s.name.lower()):
            by_cat.setdefault(s.category, []).append(s)
        cat_order = {c["id"]: i for i, c in enumerate(self.meta.categories)}
        source_groups = [{"id": c, "label": self.meta.category_label(c), "sources": by_cat[c]}
                         for c in sorted(by_cat, key=lambda c: (cat_order.get(c, 999), c))]
        self._write("details.html", "details.html",
                    self._ctx(0, page="details", source_groups=source_groups, canonical=self.site_url + "details.html",
                              title=f"Sources · {self.meta.site['title']}"))
        self._write("about.html", "about.html",
                    self._ctx(0, page="about", canonical=self.site_url + "about.html", title=f"About · {self.meta.site['title']}"))
        self._write("llms.html", "llms.html",
                    self._ctx(0, page="llms", issue=latest, canonical=self.site_url + "llms.html",
                              title=f"Guide for AI assistants · {self.meta.site['title']}"))
        self._write("llms.txt", "llms.txt", self._ctx(0, page="llms", issue=latest))
        self._write("404.html", "404.html", self._ctx(0, page="404", canonical=self.site_url + "404.html", title=f"Not found · {self.meta.site['title']}"))
        self._write("rss.xml", "rss_issues.xml", self._ctx(0, page="rss"))
        newest = sorted(self.all_articles, key=lambda a: (a.issue_number, a.relevance_score), reverse=True)[:PAPER_FEED_LIMIT]
        self._write("feed-papers.xml", "rss_papers.xml", self._ctx(0, page="rss", papers=newest))
        self._write("sitemap.xml", "sitemap.xml", self._ctx(0, page="sitemap", papers=self.all_articles))
        robots = f"User-agent: *\nAllow: /\nSitemap: {self.site_url}sitemap.xml\n"
        (self.opts.out_dir / "robots.txt").write_text(robots, encoding="utf-8")
        self._copy_data()

    def _copy_data(self) -> None:
        dst = self.opts.out_dir / "data"
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("meta.json", "sources.json"):
            shutil.copyfile(self.opts.data_dir / name, dst / name)
        (dst / "issues").mkdir(exist_ok=True)
        for f in (self.opts.data_dir / "issues").glob("*.json"):
            shutil.copyfile(f, dst / "issues" / f.name)
        (dst / "latest.json").write_text((self.opts.data_dir / "issues" / f"{self.issues[-1].number:03d}.json").read_text(encoding="utf-8")
                                         if (self.opts.data_dir / "issues" / f"{self.issues[-1].number:03d}.json").exists()
                                         else json.dumps({"number": self.issues[-1].number, "articles": [a.to_public_dict() for a in self.issues[-1].articles]}),
                                         encoding="utf-8")
