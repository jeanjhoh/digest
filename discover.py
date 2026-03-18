"""
OpenAlex-based paper discovery.
Queries target journals for recent papers and adds them to the staging database.
"""

import re
import time
from datetime import datetime, timedelta

import requests

import database
from config import (
    DISCOVERY_LOOKBACK_DAYS,
    OPENALEX_EMAIL,
    OPENALEX_RATE_LIMIT,
    TARGET_JOURNALS,
)


def _openalex_headers() -> dict:
    """Headers for polite pool access."""
    headers = {"Accept": "application/json"}
    if OPENALEX_EMAIL:
        headers["User-Agent"] = f"mailto:{OPENALEX_EMAIL}"
    return headers


def _parse_authors(authorships: list) -> str:
    """Extract author names from OpenAlex authorships."""
    names = []
    for a in authorships:
        name = a.get("author", {}).get("display_name", "")
        if name:
            names.append(name)
    return "; ".join(names)


def discover_from_journal(source_id: str, journal_name: str, from_date: str) -> int:
    """
    Query OpenAlex for recent papers from a specific journal.
    Returns the number of new papers added.
    """
    source_filter = f"https://openalex.org/{source_id}"

    url = "https://api.openalex.org/works"
    params = {
        "filter": f"primary_location.source.id:{source_filter},from_publication_date:{from_date}",
        "per_page": 50,
        "sort": "publication_date:desc",
    }

    try:
        resp = requests.get(url, params=params, headers=_openalex_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  Error querying {journal_name}: {e}")
        return 0

    papers_to_add = []
    for work in data.get("results", []):
        doi = work.get("doi", "")
        if doi:
            doi = database.normalize_doi(doi)

        title = work.get("title", "")
        if not title:
            continue

        abstract = ""
        inv_index = work.get("abstract_inverted_index")
        if inv_index:
            abstract = _reconstruct_abstract(inv_index)

        authors = _parse_authors(work.get("authorships", []))
        pub_date = work.get("publication_date", "")

        papers_to_add.append({
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "journal": journal_name,
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else work.get("id", ""),
            "published_date": pub_date,
            "source_channel": "openalex",
        })

    return database.add_papers_bulk(papers_to_add)


def _reconstruct_abstract(inverted_index: dict) -> str:
    """Reconstruct abstract text from OpenAlex's inverted index format."""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(word for _, word in word_positions)


def run_discovery(lookback_days: int = None) -> dict:
    """
    Run discovery across all target journals.
    Returns a dict of journal_name -> papers_added.
    """
    if lookback_days is None:
        lookback_days = DISCOVERY_LOOKBACK_DAYS

    from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    results = {}

    print(f"Discovering papers published since {from_date}...")
    print(f"Querying {len(TARGET_JOURNALS)} journals...\n")

    for journal_name, source_id in TARGET_JOURNALS:
        print(f"  {journal_name}...", end=" ", flush=True)
        added = discover_from_journal(source_id, journal_name, from_date)
        results[journal_name] = added
        print(f"{added} new papers")
        time.sleep(OPENALEX_RATE_LIMIT)

    total = sum(results.values())
    print(f"\nTotal: {total} new papers added to staging database.")
    return results


if __name__ == "__main__":
    run_discovery()
