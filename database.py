"""
SQLite staging database for the paper pipeline.
Papers land here from discovery and manual capture, get triaged, then optionally promoted to Zotero.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from config import DB_PATH

# --- Status constants ---
STATUS_PENDING = "pending"
STATUS_SCORED = "scored"
STATUS_PROMOTED = "promoted"
STATUS_ARCHIVED = "archived"
STATUS_FAILED = "failed"
ALL_STATUSES = [STATUS_PENDING, STATUS_SCORED, STATUS_PROMOTED, STATUS_ARCHIVED, STATUS_FAILED]

_initialized = False


def _init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist. Called once per process."""
    global _initialized
    if _initialized:
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            authors TEXT,
            abstract TEXT,
            journal TEXT,
            doi TEXT UNIQUE,
            url TEXT,
            published_date TEXT,
            source_channel TEXT NOT NULL DEFAULT 'manual',
            date_added TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            score_relevance REAL,
            score_quality REAL,
            score_timeliness REAL,
            score_composite REAL,
            triage_reasoning TEXT,
            promoted_date TEXT
        )
    """)
    conn.commit()
    _initialized = True


@contextmanager
def connection():
    """Context manager for database connections. Ensures cleanup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def compute_composite(relevance: float, quality: float, timeliness: float) -> float:
    """Single source of truth for composite score calculation."""
    return (relevance + quality + timeliness) / 3.0


def normalize_doi(raw: str) -> str:
    """Normalize a DOI string by stripping common URL prefixes and whitespace."""
    return (
        raw.strip()
        .replace("https://doi.org/", "")
        .replace("http://dx.doi.org/", "")
        .replace("http://doi.org/", "")
    )


def add_paper(
    title: str,
    authors: str = "",
    abstract: str = "",
    journal: str = "",
    doi: str = "",
    url: str = "",
    published_date: str = "",
    source_channel: str = "manual",
) -> Optional[int]:
    """
    Add a paper to the staging database.
    Returns the paper ID, or None if it's a duplicate (by DOI).
    """
    with connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO papers (title, authors, abstract, journal, doi, url,
                                    published_date, source_channel, date_added, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, authors, abstract, journal, doi, url,
                 published_date, source_channel, datetime.now().isoformat(),
                 STATUS_PENDING),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def add_papers_bulk(papers: list[dict]) -> int:
    """
    Bulk-insert papers in a single transaction.
    Returns the number of papers actually added (skipping duplicates).
    """
    added = 0
    with connection() as conn:
        for p in papers:
            try:
                conn.execute(
                    """
                    INSERT INTO papers (title, authors, abstract, journal, doi, url,
                                        published_date, source_channel, date_added, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (p["title"], p.get("authors", ""), p.get("abstract", ""),
                     p.get("journal", ""), p.get("doi", ""), p.get("url", ""),
                     p.get("published_date", ""), p.get("source_channel", "manual"),
                     datetime.now().isoformat(), STATUS_PENDING),
                )
                added += 1
            except sqlite3.IntegrityError:
                continue
        conn.commit()
    return added


def get_papers_by_status(status: str, limit: int = None) -> list[dict]:
    """Get papers by status (pending, scored, promoted, archived, failed)."""
    with connection() as conn:
        query = "SELECT * FROM papers WHERE status = ? ORDER BY date_added DESC"
        if limit:
            query += f" LIMIT {int(limit)}"
        rows = conn.execute(query, (status,)).fetchall()
        return [dict(row) for row in rows]


def get_pending_papers() -> list[dict]:
    """Get all papers with status 'pending' (not yet triaged)."""
    return get_papers_by_status(STATUS_PENDING)


def get_scored_papers(min_score: float = 0.0) -> list[dict]:
    """Get triaged papers above a minimum composite score."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT * FROM papers WHERE status = ? AND score_composite >= ?
               ORDER BY score_composite DESC""",
            (STATUS_SCORED, min_score),
        ).fetchall()
        return [dict(row) for row in rows]


def count_by_status(status: str) -> int:
    """Count papers with a given status without loading all data."""
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM papers WHERE status = ?", (status,)
        ).fetchone()
        return row["cnt"]


def update_triage_scores(
    paper_id: int,
    relevance: float,
    quality: float,
    timeliness: float,
    reasoning: str,
) -> float:
    """Update a paper's triage scores and mark as scored. Returns composite."""
    composite = compute_composite(relevance, quality, timeliness)
    with connection() as conn:
        conn.execute(
            """
            UPDATE papers SET
                score_relevance = ?,
                score_quality = ?,
                score_timeliness = ?,
                score_composite = ?,
                triage_reasoning = ?,
                status = ?
            WHERE id = ?
            """,
            (relevance, quality, timeliness, composite, reasoning,
             STATUS_SCORED, paper_id),
        )
        conn.commit()
    return composite


def mark_triage_failed(paper_id: int, reason: str) -> None:
    """Mark a paper as failed during triage."""
    with connection() as conn:
        conn.execute(
            "UPDATE papers SET status = ?, triage_reasoning = ? WHERE id = ?",
            (STATUS_FAILED, reason, paper_id),
        )
        conn.commit()


def mark_promoted(paper_id: int) -> None:
    """Mark a paper as promoted to Zotero."""
    with connection() as conn:
        conn.execute(
            "UPDATE papers SET status = ?, promoted_date = ? WHERE id = ?",
            (STATUS_PROMOTED, datetime.now().isoformat(), paper_id),
        )
        conn.commit()


def mark_archived(paper_id: int) -> None:
    """Mark a paper as archived (skipped during triage)."""
    with connection() as conn:
        conn.execute(
            "UPDATE papers SET status = ? WHERE id = ?",
            (STATUS_ARCHIVED, paper_id),
        )
        conn.commit()


def get_stats() -> dict:
    """Get counts by status."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM papers GROUP BY status"
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}


def paper_exists(doi: str) -> bool:
    """Check if a paper with this DOI already exists."""
    if not doi:
        return False
    with connection() as conn:
        row = conn.execute("SELECT 1 FROM papers WHERE doi = ?", (doi,)).fetchone()
        return row is not None
