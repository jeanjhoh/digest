"""Run orchestration: fetch → filter → upsert → abstracts → keywords → LLM → issues → persist."""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .abstracts import enrich
from .issues import Issues
from .keywords import KeywordScorer, is_candidate
from .llm import Classifier, apply_verdict
from .models import RunStats, iso, utcnow
from .normalize import is_front_matter
from .settings import Settings
from .sources import REGISTRY
from .sources.http import build_http
from .store import Store


@dataclass
class Window:
    start: datetime
    end: datetime

    @property
    def start_date(self) -> str:
        return self.start.strftime("%Y-%m-%d")

    @property
    def end_date(self) -> str:
        return self.end.strftime("%Y-%m-%d")


@dataclass
class Context:
    settings: Settings
    http: Any


def load_source_state(data_dir: Path) -> dict[str, Any]:
    p = Path(data_dir) / "source_state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_source_state(data_dir: Path, state: dict[str, Any]) -> None:
    p = Path(data_dir) / "source_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def run(settings: Settings, *, days: int | None = None, dry_run: bool = False, no_llm: bool = False,
        llm_limit: int | None = None, sources: list[str] | None = None, bootstrap: bool = False,
        client: Any = None, now: datetime | None = None) -> RunStats:
    now = now or utcnow()
    window_days = days or (settings.bootstrap_window_days if bootstrap else settings.window_days)
    window = Window(start=now - timedelta(days=window_days), end=now)
    stats = RunStats(run_id=iso(now), started_at=iso(now), window_start=iso(window.start), window_end=iso(now), dry_run=dry_run)
    ctx = Context(settings=settings, http=build_http(settings))
    store = Store.load(settings.data_dir)
    issues = Issues.load(settings.data_dir)
    state = load_source_state(settings.data_dir)
    now_iso = iso(now)
    wanted = [s for s in settings.sources if s.enabled and (not sources or s.slug in sources)]
    print(f"Run {stats.run_id}: window {window.start_date} → {window.end_date}, {len(wanted)} sources, "
          f"{len(store)} stored articles{' (dry run)' if dry_run else ''}")

    # 1. fetch + filter + upsert
    new_or_touched: list[Any] = []
    for src in wanted:
        st = stats.source(src.slug)
        src_state = state.setdefault(src.slug, {"totals": {"pulled": 0, "in_scope": 0}})
        src_state["last_checked_at"] = now_iso
        try:
            records = REGISTRY[src.kind](src, window, ctx)
        except Exception as e:  # noqa: BLE001
            st.status, st.error = "error", f"{type(e).__name__}: {str(e)[:200]}"
            stats.errors.append({"source_slug": src.slug, "message": st.error})
            src_state.update({"last_status": "error", "last_error": st.error, "last_run": {"pulled": 0, "in_scope": 0}})
            print(f"  {src.slug:16s} ERROR {st.error}")
            continue
        for rec in records:
            st.seen += 1
            fm, reason = is_front_matter(rec)
            if fm:
                st.filtered += 1
                st.filtered_reasons[reason] = st.filtered_reasons.get(reason, 0) + 1
                continue
            article, how = store.upsert(rec, src.category, now_iso)
            setattr(st, how, getattr(st, how) + 1)
            new_or_touched.append(article)
        src_state.update({"last_status": "ok" if st.seen or src.kind != "gsheet" else "empty", "last_error": None})
        src_state["totals"]["pulled"] = src_state["totals"].get("pulled", 0) + st.inserted
        print(f"  {src.slug:16s} seen {st.seen:4d}  front-matter {st.filtered:3d}  new {st.inserted:4d}  "
              f"updated {st.updated:3d}  merged {st.merged:2d}")

    # 2. abstracts
    need = store.needing_abstract(settings.enrich_max_age_days, now_iso)
    print(f"Abstracts: {len(need)} records without one; querying OpenAlex / Semantic Scholar…")
    added = enrich(need, ctx.http, settings.s2_api_key, stats.abstracts)
    # coverage over records touched this run
    cov: dict[str, int] = {}
    for a in new_or_touched:
        cov[a.abstract_source or "none"] = cov.get(a.abstract_source or "none", 0) + 1
    stats.abstracts = {"added_this_run": added, **{f"touched_{k}": v for k, v in cov.items()}}
    print(f"  added {added}; coverage of touched records: {cov}")

    # 3. keyword stage
    scorer = KeywordScorer(settings.topics)
    rescored = 0
    for a in store:
        needs = a.keyword is None or (a.keyword.get("basis") == "title_only" and a.abstract)
        if not needs:
            continue
        res = scorer.score(a.title, a.abstract)
        src = settings.source(a.source_slug)
        res["candidate"] = is_candidate(res, src) if src else res["max"] >= 2
        res["basis"] = "title+abstract" if a.abstract else "title_only"
        if a.classification and a.classification.get("basis") == "title_only" and a.abstract:
            a.classification = None  # re-classify now that an abstract exists
        a.keyword = res
        rescored += 1
    cands = store.unclassified_candidates()
    for a in cands:
        if a.source_slug in stats.sources:
            stats.sources[a.source_slug].candidates += 1
    stats.candidates = len(cands)
    per_src = {k: v.candidates for k, v in stats.sources.items() if v.candidates}
    print(f"Keywords: scored {rescored}; {len(cands)} candidates awaiting classification; by source {per_src}")

    # 4. LLM stage
    max_c = int((settings.llm or {}).get("max_candidates_per_run", 600))
    if len(cands) > max_c:
        print(f"  warning: capping candidates at {max_c} (of {len(cands)}) by keyword score")
        cands = sorted(cands, key=lambda a: -(a.keyword or {}).get("max", 0))[:max_c]
    if no_llm:
        print("LLM: skipped (--no-llm)")
    elif not cands:
        print("LLM: nothing to classify")
    else:
        clf = Classifier(settings, client=client)
        if not clf.available:
            print("LLM: skipped — ANTHROPIC_API_KEY not set; candidates stay unclassified until the next run")
        else:
            verdicts = clf.classify_all(cands, limit_batches=llm_limit)
            cfg = settings.llm or {}
            for a in cands:
                v = verdicts.get(a.key)
                if v is not None:
                    apply_verdict(a, v, clf.model, int(cfg.get("in_scope_min", 4)), int(cfg.get("recommended_min", 8)))
                    stats.classified += 1
            stats.llm = clf.stats()
            print(f"LLM: classified {stats.classified}/{len(cands)} in {clf.calls} calls, est. ${stats.llm['est_cost_usd']}")

    # 5. issues
    issue, created = issues.get_or_create(now, window_days)
    if bootstrap and created:
        issue.window_start = iso(window.start)
    assigned = Issues.assign(store, issue)
    # cap recommended per issue
    max_rec = int((settings.llm or {}).get("max_recommended_per_issue", 12))
    recs = sorted(store.iter_issue(issue.number), key=lambda a: -((a.classification or {}).get("relevance", 0)))
    for i, a in enumerate([a for a in recs if a.recommended]):
        if i >= max_rec:
            a.recommended = False
    set_ids = [s["id"] for s in settings.sets]
    Issues.finalize(issue, store, set_ids)
    stats.issue_number = issue.number
    stats.in_scope = issue.counts.get("in_scope", 0)
    stats.recommended = issue.counts.get("recommended", 0)
    stats.by_set = issue.counts.get("by_set", {})
    issue.run_status = "partial" if stats.errors else "success"
    issue.run_errors = list(stats.errors)
    issue.stats = {"seen": stats.seen, "in_scope": stats.in_scope, "est_cost_usd": stats.llm.get("est_cost_usd", 0.0)}
    for a in store.iter_issue(issue.number):
        if a.source_slug in stats.sources:
            stats.sources[a.source_slug].in_scope += 1
    for slug, st in stats.sources.items():
        s_state = state.setdefault(slug, {"totals": {"pulled": 0, "in_scope": 0}})
        s_state["last_run"] = {"pulled": st.inserted, "in_scope": st.in_scope}
    for a in store:
        if a.in_scope and not a.hidden:
            s_state = state.setdefault(a.source_slug, {"totals": {"pulled": 0, "in_scope": 0}})
            s_state.setdefault("_in_scope_total", 0)
    # recompute in_scope totals from the store (idempotent)
    totals: dict[str, int] = {}
    latest: dict[str, str] = {}
    for a in store:
        if a.in_scope and not a.hidden:
            totals[a.source_slug] = totals.get(a.source_slug, 0) + 1
            d = a.published_at or a.first_seen_at[:10]
            latest[a.source_slug] = max(latest.get(a.source_slug, ""), d)
    for slug, s_state in state.items():
        s_state.pop("_in_scope_total", None)
        s_state["totals"]["in_scope"] = totals.get(slug, 0)
        s_state["latest_in_scope_at"] = latest.get(slug)
    print(f"Issue {issue.number} ({issue.key}){' created' if created else ''}: +{assigned} assigned, "
          f"{stats.in_scope} in scope, {stats.recommended} picks, by set {stats.by_set}")

    # 6. persist
    slimmed = store.slim()
    stats.finished_at = iso(utcnow())
    if dry_run:
        print(f"Dry run: nothing written ({slimmed} abstracts would be slimmed)")
    else:
        store.save()
        issues.save()
        save_source_state(settings.data_dir, state)
        with (Path(settings.data_dir) / "runs.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(stats.to_dict(), ensure_ascii=False) + "\n")
        print(f"Saved {len(store)} articles, {len(issues.items)} issues")
    print_funnel(stats)
    return stats


def print_funnel(stats: RunStats) -> None:
    fm = sum(s.filtered for s in stats.sources.values())
    ins = sum(s.inserted for s in stats.sources.values())
    upd = sum(s.updated for s in stats.sources.values())
    mer = sum(s.merged for s in stats.sources.values())
    print(f"Funnel: seen {stats.seen} → front matter {fm} → inserted {ins} / updated {upd} / merged {mer} → "
          f"candidates {stats.candidates} → classified {stats.classified} → in scope (issue) {stats.in_scope} → "
          f"picks {stats.recommended}; errors {len(stats.errors)}")
