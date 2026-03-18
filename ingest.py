"""
Ingest papers from the Google Sheet populated by the Google Apps Script.
Fetches the published CSV, resolves metadata via CrossRef where possible,
and adds papers to the staging database.
"""

import csv
import io

import requests

import database
from capture import _resolve_doi
from config import GSHEET_CSV_URL


def fetch_sheet_papers() -> list[dict]:
    """Fetch papers from the published Google Sheet CSV."""
    if not GSHEET_CSV_URL:
        raise ValueError(
            "GSHEET_CSV_URL not set in .env. "
            "Publish your Google Sheet as CSV and paste the URL."
        )

    resp = requests.get(GSHEET_CSV_URL, timeout=30)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))
    return list(reader)


def run_ingest() -> dict:
    """
    Fetch papers from Google Sheet and add them to the staging database.
    Attempts CrossRef metadata resolution for papers with DOIs.
    Returns counts of added, skipped (duplicate), and failed papers.
    """
    sheet_papers = fetch_sheet_papers()
    if not sheet_papers:
        print("No papers found in Google Sheet.")
        return {"added": 0, "skipped": 0, "failed": 0}

    print(f"Found {len(sheet_papers)} papers in Google Sheet.\n")

    added = 0
    skipped = 0
    failed = 0

    for paper in sheet_papers:
        title = paper.get("title", "").strip()
        doi = paper.get("doi", "").strip()
        url = paper.get("url", "").strip()
        source = paper.get("source", "email_alert")

        if not title and not doi:
            failed += 1
            continue

        # Normalize DOI if present
        if doi:
            doi = database.normalize_doi(doi)

        # Try to enrich via CrossRef if we have a DOI
        metadata = None
        if doi:
            metadata = _resolve_doi(doi)

        if metadata:
            paper_id = database.add_paper(
                title=metadata["title"] or title,
                authors=metadata["authors"],
                abstract=metadata["abstract"],
                journal=metadata["journal"],
                doi=doi,
                url=url or f"https://doi.org/{doi}",
                published_date=metadata["published_date"],
                source_channel=source,
            )
        else:
            # No DOI or CrossRef lookup failed — add with what we have
            paper_id = database.add_paper(
                title=title,
                authors=paper.get("authors", ""),
                abstract="",
                journal="",
                doi=doi,
                url=url,
                source_channel=source,
            )

        if paper_id is not None:
            title_short = title[:60] + "..." if len(title) > 60 else title
            print(f"  + {title_short}")
            added += 1
        else:
            skipped += 1

    print(f"\nIngested: {added} added, {skipped} duplicates skipped, {failed} failed.")
    return {"added": added, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    run_ingest()
