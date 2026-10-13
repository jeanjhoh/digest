"""Write data/published/{meta,sources,issues/NNN}.json — the contract consumed by the site builder."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .issues import Issues
from .keywords import reasons_list
from .llm import apply_highlights
from .models import Article, iso, utcnow
from .pipeline import load_source_state
from .settings import CATEGORY_LABELS, PUBLICATION_STATUSES, Settings
from .store import Store


def _version_note(a: Article) -> str | None:
    notes = []
    for v in a.versions:
        label = v.get("venue") or v.get("source_slug")
        if v.get("publication_status") in ("working_paper", "preprint"):
            notes.append(f"Earlier version: {label}")
        else:
            notes.append(f"Also published: {label}")
    return "; ".join(notes) or None


def article_record(a: Article) -> dict[str, Any]:
    c = a.classification or {}
    return {
        "canonical_key": a.key, "title": a.title, "authors": list(a.authors), "venue": a.venue,
        "source_slug": a.source_slug, "source_category": a.source_category,
        "publication_status": a.publication_status, "doi": a.doi, "arxiv_id": a.arxiv_id, "nber_id": a.nber_id,
        "ssrn_id": a.ssrn_id, "primary_url": a.primary_url, "paper_url": a.pdf_url or a.primary_url or None,
        "pdf_url": a.pdf_url, "published_at": a.published_at, "first_seen_at": a.first_seen_at, "year": a.year,
        "volume": a.volume, "issue": a.issue, "pages": a.pages, "issue_number": a.issue_number,
        "sets": list(c.get("sets", [])), "relevance_score": int(c.get("relevance", 0)),
        "relevance_reasons": reasons_list(a.keyword), "recommended": bool(a.recommended), "note": c.get("note"),
        "abstract": a.abstract, "abstract_source": a.abstract_source if a.abstract else None,
        "version_note": _version_note(a),
    }


def publish(settings: Settings, out_dir: Path | None = None, store: Store | None = None,
            issues: Issues | None = None, source_state: dict[str, Any] | None = None) -> Path:
    out = Path(out_dir) if out_dir else Path(settings.data_dir) / "published"
    store = store or Store.load(settings.data_dir)
    issues = issues or Issues.load(settings.data_dir)
    state = source_state if source_state is not None else load_source_state(settings.data_dir)
    (out / "issues").mkdir(parents=True, exist_ok=True)
    now = iso(utcnow())
    set_ids = [s["id"] for s in settings.sets]
    categories = [{"id": cid, "label": label, "order": i + 1} for i, (cid, label) in enumerate(CATEGORY_LABELS)]

    issue_meta = []
    total_articles = 0
    for issue in sorted(issues.items, key=lambda i: i.number):
        apply_highlights(settings, list(store.iter_issue(issue.number)))
        arts = sorted(store.iter_issue(issue.number),
                      key=lambda a: (not a.recommended, -((a.classification or {}).get("relevance", 0)), a.title.lower()))
        records = [article_record(a) for a in arts]
        total_articles += len(records)
        set_counts = {s: sum(1 for r in records if s in r["sets"]) for s in set_ids}
        cat_counts: dict[str, int] = {}
        for r in records:
            cat_counts[r["source_category"]] = cat_counts.get(r["source_category"], 0) + 1
        cutoff = issue.cutoff_at[:10]
        (out / "issues" / f"{issue.number:03d}.json").write_text(json.dumps({
            "number": issue.number, "cutoff": cutoff, "window_start": issue.window_start[:10],
            "generated_at": now, "articles": records}, indent=1, ensure_ascii=False), encoding="utf-8")
        issue_meta.append({
            "number": issue.number, "cutoff": cutoff, "window_start": issue.window_start[:10],
            "published_at": issue.created_at, "count": len(records),
            "recommended_count": sum(1 for r in records if r["recommended"]),
            "set_counts": set_counts, "category_counts": cat_counts,
            "run_status": issue.run_status, "run_errors": issue.run_errors,
            "stats": {"seen": issue.stats.get("seen", 0), "in_scope": len(records),
                      "est_cost_usd": issue.stats.get("est_cost_usd", 0.0)},
        })

    sources_out = []
    for s in settings.sources:
        st = state.get(s.slug, {})
        sources_out.append({
            "slug": s.slug, "name": s.name, "kind": s.kind, "category": s.category, "tier": s.tier,
            "url": s.url, "issn": list(s.issn), "method": s.method, "notes": None, "enabled": s.enabled,
            "last_checked_at": st.get("last_checked_at"), "last_status": st.get("last_status", "pending"),
            "last_error": st.get("last_error"), "last_run": st.get("last_run", {"pulled": 0, "in_scope": 0}),
            "totals": st.get("totals", {"pulled": 0, "in_scope": 0}), "latest_in_scope_at": st.get("latest_in_scope_at"),
        })
    (out / "sources.json").write_text(json.dumps(sources_out, indent=1, ensure_ascii=False), encoding="utf-8")

    site = dict(settings.site)
    site.pop("embed_issues", None)
    meta = {
        "schema_version": 1, "generated_at": now, "site": site, "sets": settings.sets, "categories": categories,
        "publication_statuses": PUBLICATION_STATUSES,
        "latest_issue": max((i["number"] for i in issue_meta), default=0), "issues": issue_meta,
        "stats": {"issue_count": len(issue_meta), "article_count": total_articles,
                  "source_count": sum(1 for s in settings.sources if s.enabled)},
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return out
