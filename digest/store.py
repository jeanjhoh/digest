"""JSONL article store with canonical keys, aliases, and working-paper → journal version merging."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator, Literal

from .models import Article, RawRecord, iso, utcnow
from .normalize import canonical_key, family_name, normalize_title

STATUS_RANK = {"preprint": 0, "working_paper": 1, "published": 2}


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir) / "articles"
        self.by_key: dict[str, Article] = {}
        self.alias: dict[str, str] = {}
        self.by_title: dict[str, list[str]] = {}

    # ---- persistence -------------------------------------------------
    @classmethod
    def load(cls, data_dir: Path) -> "Store":
        s = cls(data_dir)
        if s.dir.exists():
            for path in sorted(s.dir.glob("*.jsonl")):
                with path.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            s._index(Article.from_dict(json.loads(line)))
        return s

    def _index(self, a: Article) -> None:
        self.by_key[a.key] = a
        for al in a.aliases:
            self.alias[al] = a.key
        if a.normalized_title:
            self.by_title.setdefault(a.normalized_title, []).append(a.key)

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        by_year: dict[str, list[Article]] = {}
        for a in self.by_key.values():
            by_year.setdefault(a.first_seen_at[:4], []).append(a)
        for year, arts in by_year.items():
            arts.sort(key=lambda a: (a.first_seen_at, a.key))
            path = self.dir / f"{year}.jsonl"
            tmp = path.with_suffix(".jsonl.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                for a in arts:
                    fh.write(json.dumps(a.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            os.replace(tmp, path)

    # ---- lookup ------------------------------------------------------
    def get(self, key: str) -> Article | None:
        if key in self.by_key:
            return self.by_key[key]
        k = self.alias.get(key)
        return self.by_key.get(k) if k else None

    def __len__(self) -> int:
        return len(self.by_key)

    def __iter__(self) -> Iterator[Article]:
        return iter(self.by_key.values())

    def find_version_match(self, rec: RawRecord) -> Article | None:
        nt = normalize_title(rec.title)
        if not nt or len(nt.split()) < 4:
            return None
        fams = {family_name(a) for a in rec.authors if a}
        for key in self.by_title.get(nt, []):
            a = self.by_key.get(key)
            if not a:
                continue
            if not fams or not a.authors:
                if not rec.authors and not a.authors:
                    return a
                continue
            if fams & {family_name(x) for x in a.authors}:
                return a
        return None

    # ---- upsert ------------------------------------------------------
    def upsert(self, rec: RawRecord, source_category: str, now_iso: str | None = None) -> tuple[Article, Literal["inserted", "updated", "merged"]]:
        now_iso = now_iso or iso(utcnow())
        key = canonical_key(rec)
        existing = self.get(key)
        if existing is not None:
            self._refresh(existing, rec, now_iso)
            return existing, "updated"
        match = self.find_version_match(rec)
        if match is not None:
            self._merge_version(match, rec, key, now_iso)
            return match, "merged"
        a = Article(
            key=key, title=rec.title, normalized_title=normalize_title(rec.title), source_slug=rec.source_slug,
            source_category=source_category, venue=rec.venue, first_seen_at=now_iso, last_seen_at=now_iso,
            doi=rec.doi, arxiv_id=rec.arxiv_id, nber_id=rec.nber_id, ssrn_id=rec.ssrn_id, repec_handle=rec.repec_handle,
            authors=list(rec.authors), author_parts=list(rec.author_parts), abstract=rec.abstract,
            abstract_source=rec.abstract_source if rec.abstract else None, publication_status=rec.publication_status,
            primary_url=rec.url, pdf_url=rec.pdf_url, published_at=rec.published_at,
            first_available_at=rec.first_available_at, volume=rec.volume, issue=rec.issue, pages=rec.pages,
            sources_seen=[rec.source_slug],
        )
        self._index(a)
        return a, "inserted"

    def _refresh(self, a: Article, rec: RawRecord, now_iso: str) -> None:
        a.last_seen_at = now_iso
        if rec.source_slug not in a.sources_seen:
            a.sources_seen.append(rec.source_slug)
        if not a.abstract and rec.abstract:
            a.abstract, a.abstract_source, a.abstract_dropped = rec.abstract, rec.abstract_source or "native", False
        if not a.pdf_url and rec.pdf_url:
            a.pdf_url = rec.pdf_url
        if not a.authors and rec.authors:
            a.authors, a.author_parts = list(rec.authors), list(rec.author_parts)
        for f in ("doi", "arxiv_id", "nber_id", "ssrn_id", "repec_handle", "published_at", "volume", "issue", "pages"):
            if getattr(a, f) is None and getattr(rec, f) is not None:
                setattr(a, f, getattr(rec, f))

    def _merge_version(self, a: Article, rec: RawRecord, key: str, now_iso: str) -> None:
        a.versions.append({"key": key, "source_slug": rec.source_slug, "venue": rec.venue,
                           "publication_status": rec.publication_status, "url": rec.url, "seen_at": now_iso})
        a.version_count = 1 + len(a.versions)
        if key not in a.aliases:
            a.aliases.append(key)
            self.alias[key] = a.key
        self._refresh(a, rec, now_iso)
        if STATUS_RANK.get(rec.publication_status, 0) > STATUS_RANK.get(a.publication_status, 0):
            old = {"key": a.key, "source_slug": a.source_slug, "venue": a.venue,
                   "publication_status": a.publication_status, "url": a.primary_url, "seen_at": a.first_seen_at}
            # swap identity to the higher-status version; keep the old key as alias
            self.by_key.pop(a.key, None)
            a.aliases = [x for x in a.aliases if x != key] + [a.key]
            self.alias[a.key] = key
            a.key = key
            a.versions = [v for v in a.versions if v["key"] != key] + [old]
            a.doi, a.arxiv_id, a.nber_id, a.ssrn_id = rec.doi or a.doi, rec.arxiv_id or a.arxiv_id, rec.nber_id or a.nber_id, rec.ssrn_id or a.ssrn_id
            a.venue, a.source_slug, a.publication_status = rec.venue, rec.source_slug, rec.publication_status
            a.primary_url, a.published_at = rec.url or a.primary_url, rec.published_at or a.published_at
            a.volume, a.issue, a.pages = rec.volume, rec.issue, rec.pages
            if rec.abstract:
                a.abstract, a.abstract_source = rec.abstract, rec.abstract_source or "native"
            self.by_key[a.key] = a
            self.alias.pop(a.key, None)

    # ---- queries -----------------------------------------------------
    def needing_abstract(self, max_age_days: int, now: str, max_attempts: int = 4) -> list[Article]:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(days=max_age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return [a for a in self.by_key.values()
                if not a.abstract and not a.abstract_dropped and a.abstract_attempts < max_attempts
                and a.first_seen_at >= cutoff and (a.doi or a.arxiv_id)]

    def unscored(self) -> list[Article]:
        return [a for a in self.by_key.values() if a.keyword is None]

    def unclassified_candidates(self) -> list[Article]:
        return [a for a in self.by_key.values() if a.candidate and a.classification is None and not a.hidden]

    def slim(self) -> int:
        n = 0
        for a in self.by_key.values():
            if not a.candidate and a.abstract:
                a.abstract, a.abstract_dropped = None, True
                n += 1
        return n

    def iter_issue(self, number: int) -> Iterator[Article]:
        for a in self.by_key.values():
            if a.issue_number == number and a.in_scope and not a.hidden:
                yield a
