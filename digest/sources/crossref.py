"""Crossref fetchers: journals by ISSN, DOI prefixes, single-DOI resolution, title lookup."""
from __future__ import annotations

import difflib
from typing import Any

from ..models import RawRecord
from ..normalize import (author_display, date_parts_to_iso, extract_ssrn_id, nber_id_from_doi, normalize_doi,
                         normalize_title, strip_jats, strip_markup)

API = "https://api.crossref.org"
SELECT = ("DOI,title,subtitle,author,abstract,container-title,ISSN,type,created,issued,published-online,"
          "published-print,URL,link,volume,issue,page,update-to,publisher")


def _min_date(*vals: str | None) -> str | None:
    xs = [v for v in vals if v]
    return min(xs) if xs else None


def parse_item(item: dict[str, Any], source: Any) -> RawRecord:
    titles = item.get("title") or []
    title = strip_markup(titles[0]) if titles else ""
    sub = item.get("subtitle") or []
    if sub and sub[0] and sub[0].strip() and sub[0].strip().lower() not in title.lower():
        title = f"{title}: {strip_markup(sub[0])}"
    authors, parts = [], []
    for a in item.get("author") or []:
        given, family, name = a.get("given"), a.get("family"), a.get("name")
        disp = author_display(given, family, name)
        if disp:
            authors.append(disp)
            parts.append({"given": given or "", "family": family or name or ""})
    doi = normalize_doi(item.get("DOI"))
    created = (item.get("created") or {}).get("date-time")
    created_d = created[:10] if created else None
    online = date_parts_to_iso((item.get("published-online") or {}).get("date-parts"))
    issued = date_parts_to_iso((item.get("issued") or {}).get("date-parts"))
    printed = date_parts_to_iso((item.get("published-print") or {}).get("date-parts"))
    pdf = None
    for link in item.get("link") or []:
        if link.get("content-type") == "application/pdf":
            pdf = link.get("URL")
            break
    container = (item.get("container-title") or [None])[0]
    ctype = item.get("type")
    status = "published" if ctype in ("journal-article", "proceedings-article") else "working_paper"
    venue = strip_markup(container) if container else source.name
    nber = nber_id_from_doi(doi)
    if nber:
        venue = "NBER Working Papers"
    return RawRecord(
        source_slug=source.slug, title=title, authors=authors, author_parts=parts,
        abstract=strip_jats(item.get("abstract")), abstract_source="crossref" if item.get("abstract") else None,
        doi=doi, nber_id=nber, ssrn_id=extract_ssrn_id(doi) if doi and doi.startswith("10.2139/") else None,
        venue=venue, url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""), pdf_url=pdf,
        published_at=online or issued or printed, first_available_at=_min_date(created_d, online, issued, printed),
        publication_status=status, crossref_type=ctype,
        volume=item.get("volume"), issue=item.get("issue"), pages=item.get("page"),
    )


def _paged(http: Any, url: str, params: dict[str, Any], max_pages: int = 10) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = "*"
    for _ in range(max_pages):
        data = http.get_json(url, params={**params, "cursor": cursor, "mailto": http.mailto})
        msg = data.get("message") or {}
        batch = msg.get("items") or []
        items.extend(batch)
        if len(batch) < int(params.get("rows", 200)):
            break
        cursor = msg.get("next-cursor")
        if not cursor:
            break
    return items


def fetch_journal(source: Any, window: Any, ctx: Any) -> list[RawRecord]:
    by_doi: dict[str, RawRecord] = {}
    for issn in source.issn:
        params = {
            "filter": f"from-created-date:{window.start_date},until-created-date:{window.end_date},type:journal-article",
            "rows": 200, "select": SELECT,
        }
        for item in _paged(ctx.http, f"{API}/journals/{issn}/works", params):
            rec = parse_item(item, source)
            k = rec.doi or rec.title
            if k not in by_doi:
                by_doi[k] = rec
    return list(by_doi.values())


def fetch_prefix(source: Any, window: Any, ctx: Any) -> list[RawRecord]:
    params = {
        "filter": f"from-created-date:{window.start_date},until-created-date:{window.end_date}",
        "rows": 200, "select": SELECT,
    }
    out = []
    for item in _paged(ctx.http, f"{API}/prefixes/{source.prefix}/works", params):
        out.append(parse_item(item, source))
    return out


def resolve_doi(http: Any, doi: str, source: Any) -> RawRecord | None:
    doi = normalize_doi(doi)
    if not doi:
        return None
    try:
        data = http.get_json(f"{API}/works/{doi}", params={"mailto": http.mailto})
    except Exception:
        return None
    item = data.get("message")
    if not item:
        return None
    return parse_item(item, source)


def lookup_title(http: Any, title: str, source: Any, min_ratio: float = 0.92) -> RawRecord | None:
    try:
        data = http.get_json(f"{API}/works", params={"query.bibliographic": title, "rows": 2, "select": SELECT,
                                                     "mailto": http.mailto})
    except Exception:
        return None
    want = normalize_title(title)
    for item in (data.get("message") or {}).get("items") or []:
        rec = parse_item(item, source)
        got = normalize_title(rec.title)
        if want and got and difflib.SequenceMatcher(None, want, got).ratio() >= min_ratio:
            return rec
    return None


def check_journal(http: Any, issn: str) -> dict[str, Any] | None:
    try:
        data = http.get_json(f"{API}/journals/{issn}", params={"mailto": http.mailto})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}
    msg = data.get("message") or {}
    return {"ok": True, "title": msg.get("title"), "issn": msg.get("ISSN"), "publisher": msg.get("publisher")}
