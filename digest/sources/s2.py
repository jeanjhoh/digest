"""Semantic Scholar Graph API batch lookup for abstracts and open-access PDFs."""
from __future__ import annotations

from typing import Any

API = "https://api.semanticscholar.org/graph/v1/paper/batch"


def lookup(http: Any, ids: list[str], api_key: str = "") -> dict[str, dict[str, Any]]:
    """ids like 'DOI:10.x/y' or 'ARXIV:2410.01234'. Returns {id: {"abstract", "pdf_url"}}."""
    out: dict[str, dict[str, Any]] = {}
    headers = {"x-api-key": api_key} if api_key else {}
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        data = http.post_json(API, params={"fields": "abstract,openAccessPdf"}, json={"ids": chunk}, headers=headers)
        for ident, item in zip(chunk, data or []):
            if not item:
                continue
            pdf = (item.get("openAccessPdf") or {}).get("url")
            out[ident] = {"abstract": item.get("abstract"), "pdf_url": pdf}
    return out
