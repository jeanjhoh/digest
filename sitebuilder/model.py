"""Data model and derived fields for the site builder."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


class BuildError(Exception):
    """Raised when the published data violates the contract."""


_SLUG_RE = re.compile(r"[^a-z0-9.]+")


def slugify_key(key: str) -> str:
    """``doi:10.1257/aer.20231368`` -> ``doi-10.1257-aer.20231368``."""
    s = _SLUG_RE.sub("-", key.lower()).strip("-")
    return s or hashlib.blake2b(key.encode(), digest_size=4).hexdigest()


def split_author(name: str) -> tuple[str, str]:
    """Return (family, given) from a display name. Handles 'Family, Given' too."""
    name = " ".join(name.split())
    if "," in name:
        fam, _, giv = name.partition(",")
        return fam.strip(), giv.strip()
    parts = name.rsplit(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[1], parts[0]


@dataclass
class Source:
    slug: str
    name: str
    kind: str
    category: str
    url: str | None = None
    issn: list[str] = field(default_factory=list)
    tier: str | None = None
    method: str | None = None
    notes: str | None = None
    enabled: bool = True
    last_checked_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    last_run: dict = field(default_factory=dict)
    totals: dict = field(default_factory=dict)
    latest_in_scope_at: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        issn = d.get("issn") or []
        if isinstance(issn, str):
            issn = [issn]
        return cls(
            slug=d["slug"], name=d["name"], kind=d.get("kind", ""), category=d.get("category", ""),
            url=d.get("url"), issn=list(issn), tier=d.get("tier"), method=d.get("method"),
            notes=d.get("notes"), enabled=d.get("enabled", True), last_checked_at=d.get("last_checked_at"),
            last_status=d.get("last_status"), last_error=d.get("last_error"),
            last_run=d.get("last_run") or {}, totals=d.get("totals") or {},
            latest_in_scope_at=d.get("latest_in_scope_at"),
        )


@dataclass
class Article:
    canonical_key: str
    title: str
    authors: list[str]
    venue: str
    source_slug: str
    source_category: str
    publication_status: str
    issue_number: int
    sets: list[str]
    relevance_score: float
    recommended: bool
    doi: str | None = None
    arxiv_id: str | None = None
    nber_id: str | None = None
    ssrn_id: str | None = None
    primary_url: str | None = None
    paper_url: str | None = None
    pdf_url: str | None = None
    published_at: str | None = None
    first_seen_at: str | None = None
    year: int | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    relevance_reasons: list[str] = field(default_factory=list)
    note: str | None = None
    abstract: str | None = None
    abstract_source: str | None = None
    version_note: str | None = None
    # derived
    slug: str = ""
    ordinal: int = 0
    set_labels: list[str] = field(default_factory=list)
    status_label: str = ""
    link: str = ""
    coins: str = ""
    bibtex: str = ""
    plain_citation: str = ""
    issn: str | None = None

    REQUIRED = ("canonical_key", "title", "authors", "venue", "source_slug", "source_category",
                "publication_status", "issue_number", "sets", "relevance_score", "recommended")

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        missing = [k for k in cls.REQUIRED if k not in d]
        if missing:
            raise BuildError(f"article {d.get('canonical_key')!r} missing keys: {missing}")
        kwargs: dict[str, Any] = {}
        for k in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            if k in d:
                kwargs[k] = d[k]
        kwargs["authors"] = [str(a) for a in (d.get("authors") or [])]
        kwargs["sets"] = list(d.get("sets") or [])
        kwargs["relevance_reasons"] = list(d.get("relevance_reasons") or [])
        kwargs["recommended"] = bool(d.get("recommended"))
        for k in ("volume", "issue", "pages"):
            if kwargs.get(k) is not None:
                kwargs[k] = str(kwargs[k])
        return cls(**kwargs)

    @property
    def family_names(self) -> list[str]:
        return [split_author(a)[0] for a in self.authors]

    @property
    def is_journal(self) -> bool:
        return self.publication_status == "published"

    def to_public_dict(self) -> dict:
        """Compact dict embedded in pages and the search index."""
        return {
            "slug": self.slug, "key": self.canonical_key, "title": self.title, "authors": self.authors,
            "venue": self.venue, "source_slug": self.source_slug, "source_category": self.source_category,
            "publication_status": self.publication_status, "status_label": self.status_label,
            "doi": self.doi, "primary_url": self.primary_url, "paper_url": self.paper_url,
            "pdf_url": self.pdf_url, "link": self.link, "published_at": self.published_at, "year": self.year,
            "issue_number": self.issue_number, "sets": self.sets, "set_labels": self.set_labels,
            "recommended": self.recommended, "note": self.note, "abstract": self.abstract,
            "abstract_source": self.abstract_source, "bibtex": self.bibtex, "plain": self.plain_citation,
            "coins": self.coins,
        }


@dataclass
class Issue:
    number: int
    cutoff: str
    window_start: str | None
    generated_at: str | None
    articles: list[Article]
    meta: dict = field(default_factory=dict)  # the entry from meta.issues, if any

    @property
    def label(self) -> str:
        return f"No. {self.number:03d}"

    @property
    def count(self) -> int:
        return len(self.articles)

    @property
    def picks(self) -> list[Article]:
        return [a for a in self.articles if a.recommended]


@dataclass
class Meta:
    site: dict
    sets: list[dict]
    categories: list[dict]
    publication_statuses: dict
    latest_issue: int
    issues: list[dict]
    stats: dict
    generated_at: str | None = None
    schema_version: int = 1

    @classmethod
    def from_dict(cls, d: dict, site_defaults: dict) -> "Meta":
        site = {**site_defaults, **(d.get("site") or {})}
        return cls(
            site=site, sets=d.get("sets") or [], categories=d.get("categories") or [],
            publication_statuses=d.get("publication_statuses") or {},
            latest_issue=int(d.get("latest_issue") or 0), issues=d.get("issues") or [],
            stats=d.get("stats") or {}, generated_at=d.get("generated_at"),
            schema_version=int(d.get("schema_version") or 1),
        )

    @property
    def set_ids(self) -> list[str]:
        return [s["id"] for s in self.sets]

    def set_label(self, sid: str, short: bool = False) -> str:
        for s in self.sets:
            if s["id"] == sid:
                return s.get("short" if short else "label") or s.get("label", sid)
        return sid

    def category_label(self, cid: str) -> str:
        for c in self.categories:
            if c["id"] == cid:
                return c.get("label", cid)
        return cid.replace("_", " ").capitalize()

    def status_label(self, status: str) -> str:
        return self.publication_statuses.get(status) or status.replace("_", " ").capitalize()


def group_issue(issue: Issue, sources: dict[str, Source], meta: Meta) -> list[dict]:
    """Group articles by category (meta order) then source (name order)."""
    cat_order = {c["id"]: i for i, c in enumerate(meta.categories)}
    by_cat: dict[str, dict[str, list[Article]]] = {}
    for a in issue.articles:
        by_cat.setdefault(a.source_category, {}).setdefault(a.source_slug, []).append(a)
    out = []
    for cid in sorted(by_cat, key=lambda c: (cat_order.get(c, 999), c)):
        srcs = []
        for slug in sorted(by_cat[cid], key=lambda s: (sources[s].name if s in sources else s).lower()):
            arts = sorted(by_cat[cid][slug], key=lambda a: (-a.relevance_score, a.title.lower()))
            srcs.append({"slug": slug, "name": sources[slug].name if slug in sources else slug, "articles": arts})
        out.append({"id": cid, "label": meta.category_label(cid), "sources": srcs,
                    "count": sum(len(s["articles"]) for s in srcs)})
    return out


def for_you(issue: Issue, cap: int) -> list[Article]:
    picks = sorted(issue.picks, key=lambda a: (-a.relevance_score, a.title.lower()))
    return picks[:cap]
