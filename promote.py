"""
Promote scored papers to Zotero.
Only papers above the configured threshold get promoted.
Uses pyzotero to create items in the Zotero library.
Downloads open access PDFs when available.
"""

import os
import sys
import tempfile

import requests
from pyzotero import zotero

import database
from database import STATUS_PROMOTED
from config import (
    PROMOTE_THRESHOLD,
    READING_QUEUE_CAP,
    ZOTERO_API_KEY,
    ZOTERO_LIBRARY_ID,
    ZOTERO_LIBRARY_TYPE,
)


def _get_zotero_client() -> zotero.Zotero:
    """Initialize pyzotero client. Raises ValueError if not configured."""
    if not ZOTERO_API_KEY or not ZOTERO_LIBRARY_ID:
        raise ValueError(
            "ZOTERO_API_KEY and ZOTERO_LIBRARY_ID must be set in .env. "
            "Get your API key at: https://www.zotero.org/settings/keys "
            "Your library ID is listed as 'Your userID' on that page."
        )
    return zotero.Zotero(ZOTERO_LIBRARY_ID, ZOTERO_LIBRARY_TYPE, ZOTERO_API_KEY)


ZOTERO_COLLECTION_NAME = "_Reader Digest"


def _get_or_create_collection(zot: zotero.Zotero) -> str:
    """Find or create the _Reader Digest collection. Returns the collection key."""
    collections = zot.collections()
    for col in collections:
        if col["data"]["name"] == ZOTERO_COLLECTION_NAME:
            return col["key"]

    # Create the collection
    resp = zot.create_collections([{"name": ZOTERO_COLLECTION_NAME}])
    if resp.get("successful"):
        return resp["successful"]["0"]["data"]["key"]
    raise RuntimeError(f"Failed to create Zotero collection: {resp}")


def _build_zotero_item(paper: dict, template: dict, collection_key: str) -> dict:
    """Convert a staging DB paper to a Zotero item, using a pre-fetched template."""
    creators = []
    if paper.get("authors"):
        for author_name in paper["authors"].split("; "):
            parts = author_name.strip().rsplit(" ", 1)
            if len(parts) == 2:
                creators.append({
                    "creatorType": "author",
                    "firstName": parts[0],
                    "lastName": parts[1],
                })
            elif parts[0]:
                creators.append({
                    "creatorType": "author",
                    "lastName": parts[0],
                    "firstName": "",
                })

    item = dict(template)
    item.update({
        "itemType": "journalArticle",
        "title": paper["title"],
        "creators": creators,
        "abstractNote": paper.get("abstract", ""),
        "publicationTitle": paper.get("journal", ""),
        "DOI": paper.get("doi", ""),
        "url": paper.get("url", ""),
        "date": paper.get("published_date", ""),
        "collections": [collection_key],
        "tags": [
            {"tag": "reader-pipeline"},
            {"tag": f"score:{paper.get('score_composite', 0):.1f}"},
        ],
        "extra": paper.get("triage_reasoning", ""),
    })
    return item


def _download_pdf(url: str) -> str | None:
    """Download a PDF to a temp file. Returns the file path, or None on failure."""
    try:
        resp = requests.get(url, timeout=30, allow_redirects=True,
                            headers={"Accept": "application/pdf"})
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
            return None
        fd, path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as f:
            f.write(resp.content)
        return path
    except Exception:
        return None


def promote_paper(paper: dict, zot: zotero.Zotero, template: dict, collection_key: str) -> bool:
    """Promote a single paper to Zotero. Returns True on success."""
    item = _build_zotero_item(paper, template, collection_key)
    try:
        resp = zot.create_items([item])
        if not resp.get("successful"):
            print(f"    Zotero API error: {resp.get('failed', {})}")
            return False

        item_key = resp["successful"]["0"]["key"]
        database.mark_promoted(paper["id"])

        # Attempt to download and attach open access PDF
        oa_url = paper.get("oa_pdf_url", "")
        if oa_url:
            pdf_path = _download_pdf(oa_url)
            if pdf_path:
                try:
                    zot.attachment_simple([pdf_path], item_key)
                    print("[PDF] ", end="", flush=True)
                except Exception:
                    pass  # Item created successfully, PDF attachment is a bonus
                finally:
                    os.unlink(pdf_path)

        return True
    except Exception as e:
        print(f"    Error promoting: {e}")
        return False


def run_promote(threshold: float = None, select: str = None, yes: bool = False) -> int:
    """
    Promote scored papers above threshold to Zotero.

    Modes:
      - default: Show list, prompt for numbers to promote
      - --select 1,3,5: Promote specific papers by number
      - --yes: Promote all above threshold without asking
    """
    if threshold is None:
        threshold = PROMOTE_THRESHOLD

    papers = database.get_scored_papers(min_score=threshold)
    if not papers:
        print(f"No scored papers above threshold ({threshold}).")
        return 0

    already_promoted = database.count_by_status(STATUS_PROMOTED)
    remaining_slots = max(0, READING_QUEUE_CAP - already_promoted)

    if remaining_slots == 0:
        print(f"Reading queue is full ({READING_QUEUE_CAP} papers). "
              "Read or archive some papers first.")
        return 0

    papers = papers[:remaining_slots]

    # Display the list
    print(f"Reading queue: {already_promoted}/{READING_QUEUE_CAP} slots used.")
    print(f"Papers above threshold ({threshold}):\n")

    for i, paper in enumerate(papers, 1):
        title = paper["title"]
        authors = paper.get("authors", "")
        journal = paper.get("journal", "")
        doi = paper.get("doi", "")
        abstract = paper.get("abstract", "")
        reasoning = paper.get("triage_reasoning", "")

        print(f"  {'─' * 72}")
        print(f"  {i:>2}. [{paper['score_composite']:.1f}]  R={paper.get('score_relevance', 0):.0f}  "
              f"Q={paper.get('score_quality', 0):.0f}  T={paper.get('score_timeliness', 0):.0f}")
        print(f"      {title}")
        print(f"      {authors}")
        print(f"      {journal}" + (f" | DOI: {doi}" if doi else ""))
        if reasoning:
            print(f"      AI: {reasoning}")
        if abstract:
            abstract_display = abstract[:300] + "..." if len(abstract) > 300 else abstract
            print(f"      Abstract: {abstract_display}")
        print()

    # Determine which papers to promote
    if yes:
        selected_indices = list(range(len(papers)))
    elif select:
        try:
            selected_indices = [int(x.strip()) - 1 for x in select.split(",")]
            selected_indices = [i for i in selected_indices if 0 <= i < len(papers)]
        except ValueError:
            print("Invalid selection. Use comma-separated numbers, e.g.: 1,3,5")
            return 0
    else:
        print("Enter paper numbers to promote (comma-separated), 'all', or 'none':")
        print("  Example: 1,3,5")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0

        if choice in ("none", "n", "q", ""):
            print("No papers promoted.")
            return 0
        elif choice == "all":
            selected_indices = list(range(len(papers)))
        else:
            try:
                selected_indices = [int(x.strip()) - 1 for x in choice.split(",")]
                selected_indices = [i for i in selected_indices if 0 <= i < len(papers)]
            except ValueError:
                print("Invalid input. Use comma-separated numbers, 'all', or 'none'.")
                return 0

    if not selected_indices:
        print("No valid papers selected.")
        return 0

    # Archive non-selected papers
    selected_set = set(selected_indices)
    for i in range(len(papers)):
        if i not in selected_set:
            database.mark_archived(papers[i]["id"])

    # Promote selected papers
    zot = _get_zotero_client()
    template = zot.item_template("journalArticle")
    collection_key = _get_or_create_collection(zot)
    print(f"  Adding to Zotero collection: {ZOTERO_COLLECTION_NAME}\n")
    promoted = 0

    for i in selected_indices:
        paper = papers[i]
        title = paper["title"][:60] + "..." if len(paper["title"]) > 60 else paper["title"]
        print(f"  Promoting: {title}...", end=" ", flush=True)

        if promote_paper(paper, zot, template, collection_key):
            promoted += 1
            print("✓")
        else:
            print("✗")

    print(f"\nPromoted {promoted} papers to Zotero. "
          f"Archived {len(papers) - len(selected_indices)} others.")
    return promoted


if __name__ == "__main__":
    run_promote()
