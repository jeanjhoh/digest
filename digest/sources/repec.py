"""RePEc NEP report fetcher (RSS 1.0 feed of the latest report issue)."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import feedparser

from ..models import RawRecord
from ..normalize import strip_markup

FEED = "http://nep.repec.org/rss/{report}.rss.xml"
NBER_RE = re.compile(r"^RePEc:nbr:nberwo:(\d+)$", re.I)
ARXIV_RE = re.compile(r"^RePEc:arx:papers:(\d{4}\.\d{4,5})$", re.I)


def _handle(link: str) -> str | None:
    q = parse_qs(urlparse(link).query)
    u = q.get("u", [None])[0]
    return u


def fetch(source: Any, window: Any, ctx: Any) -> list[RawRecord]:
    r = ctx.http.get(FEED.format(report=source.report), timeout=60)
    feed = feedparser.parse(r.text)
    issue_date = (feed.feed.get("date") or feed.feed.get("updated") or "")[:10] or None
    if issue_date and issue_date < window.start_date:
        return []
    out: list[RawRecord] = []
    for e in feed.entries:
        link = e.get("link") or ""
        handle = _handle(link)
        authors = []
        creator = e.get("author") or e.get("dc_creator")
        if creator:
            authors = [strip_markup(a) for a in re.split(r";|,\s*(?=[A-Z])|\band\b", creator) if a.strip()]
        rec = RawRecord(
            source_slug=source.slug, title=strip_markup(e.get("title")), authors=authors,
            author_parts=[{"given": " ".join(a.split()[:-1]), "family": a.split()[-1]} for a in authors if a.split()],
            abstract=strip_markup(e.get("summary") or e.get("description")) or None, abstract_source="repec",
            repec_handle=handle, venue=f"RePEc NEP: {source.name.split(':', 1)[-1].strip()}", url=link,
            published_at=issue_date, first_available_at=issue_date, publication_status="working_paper",
            crossref_type="report",
        )
        if handle:
            m = NBER_RE.match(handle)
            if m:
                rec.nber_id = f"w{m.group(1)}"
                rec.doi = f"10.3386/w{m.group(1)}"
                rec.venue = "NBER Working Papers"
                rec.url = f"https://www.nber.org/papers/w{m.group(1)}"
            m = ARXIV_RE.match(handle)
            if m:
                rec.arxiv_id = m.group(1)
                rec.url = f"https://arxiv.org/abs/{m.group(1)}"
                rec.publication_status = "preprint"
        if rec.title:
            out.append(rec)
    return out
