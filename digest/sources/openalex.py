"""OpenAlex enrichment: abstracts (inverted index) and OA PDF links by DOI batch."""
from __future__ import annotations

from typing import Any

API = "https://api.openalex.org/works"


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    positions = []
    for word, idxs in inverted_index.items():
        for pos in idxs:
            positions.append((pos, word))
    positions.sort()
    text = " ".join(w for _, w in positions).strip()
    return text or None


def lookup_by_doi(http: Any, dois: list[str]) -> dict[str, dict[str, Any]]:
    """Return {doi: {"abstract": str|None, "pdf_url": str|None}} for up to 50 DOIs per request."""
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(dois), 50):
        chunk = dois[i:i + 50]
        data = http.get_json(API, params={"filter": "doi:" + "|".join(chunk),
                                          "select": "doi,abstract_inverted_index,open_access,best_oa_location",
                                          "per-page": 50, "mailto": http.mailto})
        for w in data.get("results") or []:
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            if not doi:
                continue
            loc = w.get("best_oa_location") or {}
            out[doi] = {"abstract": reconstruct_abstract(w.get("abstract_inverted_index")),
                        "pdf_url": loc.get("pdf_url")}
    return out
