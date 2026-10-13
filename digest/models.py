"""Dataclasses for raw fetched records, stored articles, issues and run statistics."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RawRecord:
    source_slug: str
    title: str
    authors: list[str] = field(default_factory=list)
    author_parts: list[dict[str, str]] = field(default_factory=list)
    abstract: str | None = None
    abstract_source: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    nber_id: str | None = None
    ssrn_id: str | None = None
    repec_handle: str | None = None
    venue: str = ""
    url: str = ""
    pdf_url: str | None = None
    published_at: str | None = None
    first_available_at: str | None = None
    publication_status: str = "published"
    crossref_type: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None


@dataclass
class Article:
    key: str
    title: str
    normalized_title: str
    source_slug: str
    source_category: str
    venue: str
    first_seen_at: str
    last_seen_at: str
    aliases: list[str] = field(default_factory=list)
    doi: str | None = None
    arxiv_id: str | None = None
    nber_id: str | None = None
    ssrn_id: str | None = None
    repec_handle: str | None = None
    authors: list[str] = field(default_factory=list)
    author_parts: list[dict[str, str]] = field(default_factory=list)
    abstract: str | None = None
    abstract_source: str | None = None
    abstract_attempts: int = 0
    abstract_dropped: bool = False
    publication_status: str = "published"
    primary_url: str = ""
    pdf_url: str | None = None
    published_at: str | None = None
    first_available_at: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    sources_seen: list[str] = field(default_factory=list)
    keyword: dict[str, Any] | None = None
    classification: dict[str, Any] | None = None
    in_scope: bool = False
    recommended: bool = False
    hidden: bool = False
    issue_number: int | None = None
    versions: list[dict[str, Any]] = field(default_factory=list)
    version_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Article":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    @property
    def candidate(self) -> bool:
        return bool(self.keyword and self.keyword.get("candidate"))

    @property
    def year(self) -> int | None:
        d = self.published_at or self.first_available_at or self.first_seen_at
        try:
            return int(str(d)[:4])
        except (TypeError, ValueError):
            return None


@dataclass
class Issue:
    number: int
    key: str
    window_start: str
    cutoff_at: str
    created_at: str
    counts: dict[str, Any] = field(default_factory=dict)
    run_status: str = "success"
    run_errors: list[dict[str, str]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Issue":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class SourceStats:
    seen: int = 0
    inserted: int = 0
    updated: int = 0
    merged: int = 0
    filtered: int = 0
    filtered_reasons: dict[str, int] = field(default_factory=dict)
    candidates: int = 0
    in_scope: int = 0
    status: str = "ok"
    error: str | None = None


@dataclass
class RunStats:
    run_id: str
    started_at: str
    window_start: str
    window_end: str
    dry_run: bool = False
    finished_at: str | None = None
    issue_number: int | None = None
    sources: dict[str, SourceStats] = field(default_factory=dict)
    abstracts: dict[str, int] = field(default_factory=dict)
    candidates: int = 0
    classified: int = 0
    in_scope: int = 0
    recommended: int = 0
    by_set: dict[str, int] = field(default_factory=dict)
    llm: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)

    def source(self, slug: str) -> SourceStats:
        if slug not in self.sources:
            self.sources[slug] = SourceStats()
        return self.sources[slug]

    @property
    def seen(self) -> int:
        return sum(s.seen for s in self.sources.values())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
