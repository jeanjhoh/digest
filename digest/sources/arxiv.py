"""arXiv export API fetcher."""
from __future__ import annotations

import re
from typing import Any

import feedparser

from ..models import RawRecord
from ..normalize import strip_markup

API = "http://export.arxiv.org/api/query"
ID_RE = re.compile(r"arxiv\.org/abs/([^v\s]+)(?:v\d+)?", re.I)


def _entry_to_record(e: Any, source: Any) -> RawRecord | None:
    m = ID_RE.search(e.get("id", ""))
    if not m:
        return None
    aid = m.group(1)
    authors = [strip_markup(a.get("name")) for a in e.get("authors", []) if a.get("name")]
    parts = []
    for a in authors:
        bits = a.split()
        parts.append({"given": " ".join(bits[:-1]), "family": bits[-1] if bits else ""})
    primary = None
    for t in e.get("tags", []) or []:
        primary = t.get("term")
        break
    pdf = None
    for link in e.get("links", []) or []:
        if link.get("title") == "pdf" or "/pdf/" in link.get("href", ""):
            pdf = link.get("href")
    doi = e.get("arxiv_doi")
    return RawRecord(
        source_slug=source.slug, title=strip_markup(e.get("title")), authors=authors, author_parts=parts,
        abstract=strip_markup(e.get("summary")) or None, abstract_source="arxiv",
        doi=doi.lower() if doi else None, arxiv_id=aid,
        venue=f"arXiv {primary}" if primary else "arXiv", url=f"https://arxiv.org/abs/{aid}",
        pdf_url=pdf or f"https://arxiv.org/pdf/{aid}",
        published_at=(e.get("published") or "")[:10] or None, first_available_at=(e.get("published") or "")[:10] or None,
        publication_status="preprint", crossref_type="posted-content",
    )


def fetch(source: Any, window: Any, ctx: Any) -> list[RawRecord]:
    out: list[RawRecord] = []
    start, page = 0, 100
    since = window.start_date
    for _ in range(5):
        r = ctx.http.get(API, params={"search_query": source.query, "sortBy": "submittedDate", "sortOrder": "descending",
                                      "start": start, "max_results": page}, timeout=90)
        feed = feedparser.parse(r.text)
        entries = feed.entries
        if not entries:
            break
        stop = False
        for e in entries:
            pub = (e.get("published") or "")[:10]
            if pub and pub < since:
                stop = True
                break
            rec = _entry_to_record(e, source)
            if rec:
                out.append(rec)
        if stop or len(entries) < page:
            break
        start += page
    return out
