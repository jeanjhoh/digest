"""Abstract acquisition chain: native/Crossref (already on the record) → OpenAlex → Semantic Scholar."""
from __future__ import annotations

from typing import Any

from .models import Article
from .sources import openalex, s2


def enrich(articles: list[Article], http: Any, s2_api_key: str = "", stats: dict[str, int] | None = None) -> int:
    """Fill missing abstracts (and OA pdf links) in place. Returns the number of abstracts added."""
    stats = stats if stats is not None else {}
    pending = [a for a in articles if not a.abstract]
    added = 0
    # OpenAlex by DOI
    with_doi = [a for a in pending if a.doi]
    if with_doi:
        try:
            found = openalex.lookup_by_doi(http, [a.doi for a in with_doi])
        except Exception as e:  # noqa: BLE001
            stats["openalex_error"] = stats.get("openalex_error", 0) + 1
            print(f"  warning: OpenAlex lookup failed: {e}")
            found = {}
        for a in with_doi:
            hit = found.get(a.doi)
            if not hit:
                continue
            if hit.get("abstract"):
                a.abstract, a.abstract_source, a.abstract_dropped = hit["abstract"], "openalex", False
                added += 1
            if not a.pdf_url and hit.get("pdf_url"):
                a.pdf_url = hit["pdf_url"]
    # Semantic Scholar for the rest
    rest = [a for a in pending if not a.abstract and (a.doi or a.arxiv_id)]
    if rest:
        ids = [f"DOI:{a.doi}" if a.doi else f"ARXIV:{a.arxiv_id}" for a in rest]
        try:
            found = s2.lookup(http, ids, api_key=s2_api_key)
        except Exception as e:  # noqa: BLE001
            stats["s2_error"] = stats.get("s2_error", 0) + 1
            print(f"  warning: Semantic Scholar lookup failed: {e}")
            found = {}
        for a, ident in zip(rest, ids):
            hit = found.get(ident)
            if not hit:
                continue
            if hit.get("abstract"):
                a.abstract, a.abstract_source, a.abstract_dropped = hit["abstract"], "semantic_scholar", False
                added += 1
            if not a.pdf_url and hit.get("pdf_url"):
                a.pdf_url = hit["pdf_url"]
    for a in pending:
        a.abstract_attempts += 1
    for a in articles:
        if a.abstract:
            src = a.abstract_source or "native"
            stats[src] = stats.get(src, 0) + 1
        else:
            stats["none"] = stats.get("none", 0) + 1
    return added
