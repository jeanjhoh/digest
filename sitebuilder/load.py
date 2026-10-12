"""Read and validate the published data contract."""
from __future__ import annotations

import json
from pathlib import Path

from .config import SITE_DEFAULTS
from .model import Article, BuildError, Issue, Meta, Source


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise BuildError(f"missing data file: {path}") from e
    except json.JSONDecodeError as e:
        raise BuildError(f"invalid JSON in {path}: {e}") from e


def load_meta(data_dir: Path) -> Meta:
    return Meta.from_dict(_read_json(data_dir / "meta.json"), SITE_DEFAULTS)


def load_sources(data_dir: Path) -> dict[str, Source]:
    raw = _read_json(data_dir / "sources.json")
    if not isinstance(raw, list):
        raise BuildError("sources.json must be a list")
    out: dict[str, Source] = {}
    for d in raw:
        s = Source.from_dict(d)
        if s.slug in out:
            raise BuildError(f"duplicate source slug {s.slug!r}")
        out[s.slug] = s
    return out


def load_issues(data_dir: Path, meta: Meta) -> list[Issue]:
    issue_dir = data_dir / "issues"
    files = sorted(issue_dir.glob("*.json")) if issue_dir.is_dir() else []
    if not files:
        raise BuildError(f"no issue files in {issue_dir}")
    meta_by_num = {int(i["number"]): i for i in meta.issues}
    issues: list[Issue] = []
    for f in files:
        d = _read_json(f)
        arts = [Article.from_dict(a) for a in d.get("articles") or []]
        number = int(d["number"])
        issues.append(Issue(number=number, cutoff=str(d.get("cutoff") or ""), window_start=d.get("window_start"),
                            generated_at=d.get("generated_at"), articles=arts, meta=meta_by_num.get(number, {})))
    issues.sort(key=lambda i: i.number)
    return issues


def validate(meta: Meta, sources: dict[str, Source], issues: list[Issue], strict: bool = False) -> list[str]:
    """Return warnings; raise BuildError on contract violations."""
    warnings: list[str] = []
    set_ids = set(meta.set_ids)
    seen: dict[str, int] = {}
    numbers = [i.number for i in issues]
    if len(set(numbers)) != len(numbers):
        raise BuildError("duplicate issue numbers")
    for issue in issues:
        for a in issue.articles:
            if a.canonical_key in seen:
                raise BuildError(f"article {a.canonical_key} appears in issues {seen[a.canonical_key]} and {issue.number}")
            seen[a.canonical_key] = issue.number
            if a.issue_number != issue.number:
                raise BuildError(f"article {a.canonical_key} has issue_number {a.issue_number} but is in issue {issue.number}")
            if not a.sets:
                raise BuildError(f"article {a.canonical_key} has no sets")
            bad = [s for s in a.sets if s not in set_ids]
            if bad:
                raise BuildError(f"article {a.canonical_key} has unknown sets {bad}")
            if a.source_slug not in sources:
                raise BuildError(f"article {a.canonical_key} references unknown source {a.source_slug!r}")
            if not (0 <= float(a.relevance_score) <= 10):
                raise BuildError(f"article {a.canonical_key} relevance_score out of range")
            if not a.primary_url and not a.paper_url:
                warnings.append(f"{a.canonical_key}: no primary_url or paper_url")
            if a.abstract is None:
                warnings.append(f"{a.canonical_key}: no abstract")
            if not a.authors:
                warnings.append(f"{a.canonical_key}: no authors")
    if meta.latest_issue and meta.latest_issue != issues[-1].number:
        warnings.append(f"meta.latest_issue={meta.latest_issue} but newest issue file is {issues[-1].number}")
    if strict and warnings:
        raise BuildError("strict mode: " + "; ".join(warnings[:10]))
    return warnings
