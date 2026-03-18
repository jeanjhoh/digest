"""
Manual paper capture.
Add papers to the staging database by DOI (auto-resolves metadata via CrossRef)
or by manually providing title/authors/abstract.
"""

import re

import requests

import database


def capture_by_doi(doi: str) -> dict:
    """
    Look up a DOI via CrossRef and add the paper to the staging database.
    Returns a dict with paper info and whether it was added.
    """
    doi = database.normalize_doi(doi)

    metadata = _resolve_doi(doi)
    if metadata is None:
        return {"added": False, "reason": "not_found", "doi": doi}

    paper_id = database.add_paper(
        title=metadata["title"],
        authors=metadata["authors"],
        abstract=metadata["abstract"],
        journal=metadata["journal"],
        doi=doi,
        url=f"https://doi.org/{doi}",
        published_date=metadata["published_date"],
        source_channel="manual_doi",
    )

    if paper_id is None:
        return {"added": False, "reason": "duplicate", "doi": doi}

    return {
        "added": True,
        "paper_id": paper_id,
        "title": metadata["title"],
        "authors": metadata["authors"],
        "journal": metadata["journal"],
    }


def capture_manual(
    title: str,
    authors: str = "",
    abstract: str = "",
    journal: str = "",
    doi: str = "",
    url: str = "",
) -> dict:
    """Add a paper manually with provided metadata."""
    if doi:
        doi = database.normalize_doi(doi)

    paper_id = database.add_paper(
        title=title,
        authors=authors,
        abstract=abstract,
        journal=journal,
        doi=doi,
        url=url,
        source_channel="manual_entry",
    )

    if paper_id is None:
        return {"added": False, "reason": "duplicate", "doi": doi}

    return {"added": True, "paper_id": paper_id, "title": title}


def _resolve_doi(doi: str) -> dict | None:
    """Resolve a DOI to metadata via CrossRef API."""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        resp = requests.get(url, timeout=15, headers={"Accept": "application/json"})
        resp.raise_for_status()
        item = resp.json().get("message", {})
    except requests.RequestException:
        return None

    titles = item.get("title", [])
    title = titles[0] if titles else ""

    authors_list = item.get("author", [])
    authors = "; ".join(
        f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list
    )

    abstract = item.get("abstract", "")
    if abstract:
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()

    container = item.get("container-title", [])
    journal = container[0] if container else ""

    date_parts = item.get("published-print", item.get("published-online", {}))
    pub_date = ""
    if date_parts and "date-parts" in date_parts:
        parts = date_parts["date-parts"][0]
        pub_date = "-".join(str(p) for p in parts if p)

    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "journal": journal,
        "published_date": pub_date,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = capture_by_doi(sys.argv[1])
        if result["added"]:
            print(f"Added: {result['title']}")
            print(f"Authors: {result['authors']}")
            print(f"Journal: {result['journal']}")
        else:
            print(f"Not added: {result['reason']}")
    else:
        print("Usage: python capture.py <DOI>")
