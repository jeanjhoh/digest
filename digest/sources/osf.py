"""OSF preprints fetcher (SocArXiv and other OSF-hosted preprint providers) via the public OSF API v2."""
from __future__ import annotations

from typing import Any

from ..models import RawRecord
from ..normalize import strip_markup

API = "https://api.osf.io/v2/preprints/"
PROVIDER_NAMES = {"socarxiv": "SocArXiv", "psyarxiv": "PsyArXiv", "osf": "OSF Preprints"}


def _doi(p: dict[str, Any]) -> str | None:
    a = p.get("attributes", {})
    link = (p.get("links") or {}).get("preprint_doi") or ""
    if link.startswith("https://doi.org/"):
        return link[len("https://doi.org/"):]
    return a.get("doi") or None


def _authors(p: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    names, parts = [], []
    for c in ((p.get("embeds") or {}).get("contributors") or {}).get("data", []):
        if c.get("attributes", {}).get("bibliographic") is False:
            continue
        u = (((c.get("embeds") or {}).get("users") or {}).get("data") or {}).get("attributes") or {}
        full = u.get("full_name") or ""
        if not full:
            continue
        names.append(full)
        parts.append({"given": u.get("given_name") or " ".join(full.split()[:-1]), "family": u.get("family_name") or full.split()[-1]})
    return names, parts


def fetch(source: Any, window: Any, ctx: Any) -> list[RawRecord]:
    params = {
        "filter[provider]": source.provider, "filter[date_created][gte]": window.start_date,
        "embed": "contributors", "page[size]": "100",
    }
    venue = PROVIDER_NAMES.get(source.provider, source.name)
    out: list[RawRecord] = []
    url: str | None = API
    pages = 0
    while url and pages < 20:
        r = ctx.http.get(url, params=params if pages == 0 else None, timeout=60)
        data = r.json()
        for p in data.get("data", []):
            a = p.get("attributes", {})
            if not a.get("is_published") or a.get("date_withdrawn"):
                continue
            if a.get("reviews_state") not in (None, "accepted"):
                continue
            if a.get("is_latest_version") is False:
                continue
            names, parts = _authors(p)
            published = (a.get("date_published") or a.get("date_created") or "")[:10] or None
            out.append(RawRecord(
                source_slug=source.slug, title=strip_markup(a.get("title") or ""), authors=names, author_parts=parts,
                abstract=strip_markup(a.get("description") or "") or None, abstract_source="osf",
                doi=_doi(p), venue=venue, url=(p.get("links") or {}).get("html") or "",
                published_at=published, first_available_at=published, publication_status="preprint",
                crossref_type="posted-content",
            ))
        url = (data.get("links") or {}).get("next")
        pages += 1
    return [r for r in out if r.title]
