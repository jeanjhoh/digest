"""Google Sheet (published CSV) of SSRN and Google Scholar alert emails."""
from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

from ..models import RawRecord
from ..normalize import (extract_arxiv_id, extract_doi, extract_ssrn_id, normalize_doi, parse_iso_datetime,
                         strip_markup)
from . import crossref

JUNK_TITLES = {"see all recommendations", "see all", "view all", "new results", "recommended articles"}


def fetch(source: Any, window: Any, ctx: Any) -> list[RawRecord]:
    url = ctx.settings.gsheet_csv_url
    if not url:
        raise RuntimeError("GSHEET_CSV_URL not set")
    r = ctx.http.get(url, timeout=60)
    rows = list(csv.DictReader(io.StringIO(r.text)))
    since = window.start - timedelta(days=2)
    out: list[RawRecord] = []
    for row in rows:
        title = strip_markup(row.get("title", ""))
        link = (row.get("url") or "").strip()
        found = parse_iso_datetime((row.get("date_found") or "").strip())
        if not title or title.lower() in JUNK_TITLES or "scholar.google.com" in link:
            continue
        if found is None or found < since:
            continue
        channel = (row.get("source") or "email_alert").strip()
        doi = normalize_doi(row.get("doi")) or extract_doi(link)
        ssrn = extract_ssrn_id(link) if "ssrn" in link.lower() else None
        if ssrn and not doi:
            doi = f"10.2139/ssrn.{ssrn}"
        arxiv_id = extract_arxiv_id(link)
        rec: RawRecord | None = None
        if doi:
            rec = crossref.resolve_doi(ctx.http, doi, source)
        elif not arxiv_id and len(title.split()) >= 4:
            rec = crossref.lookup_title(ctx.http, title, source)
        if rec is None:
            rec = RawRecord(source_slug=source.slug, title=title, doi=doi, ssrn_id=ssrn, arxiv_id=arxiv_id,
                            venue="SSRN" if ssrn else ("arXiv" if arxiv_id else "Google Scholar alert"),
                            url=link or (f"https://doi.org/{doi}" if doi else ""),
                            publication_status="working_paper" if (ssrn or arxiv_id) else "published",
                            published_at=found.date().isoformat(), first_available_at=found.date().isoformat())
            auth = (row.get("authors") or "").strip()
            if auth:
                rec.authors = [a.strip() for a in auth.replace(";", ",").split(",") if a.strip()]
        else:
            rec.source_slug = source.slug
            if ssrn:
                rec.ssrn_id = ssrn
                rec.publication_status = "working_paper"
                rec.venue = rec.venue or "SSRN"
            if not rec.url:
                rec.url = link
        rec.crossref_type = rec.crossref_type or "posted-content"
        out.append(rec)
    return out
