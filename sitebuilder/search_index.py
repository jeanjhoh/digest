"""Build the cross-issue search index (one JSON file, or sharded by year)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import SEARCH_SHARD_BUDGET
from .model import Issue


def _entry(a) -> dict:
    d = a.to_public_dict()
    d.pop("bibtex", None)
    d.pop("plain", None)
    return d


def write_search_index(out_dir: Path, issues: list[Issue], generated_at: str | None) -> list[str]:
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    articles = [_entry(a) for issue in reversed(issues) for a in issue.articles]
    issue_list = [{"number": i.number, "cutoff": i.cutoff, "count": i.count} for i in reversed(issues)]
    payload = {"generated_at": generated_at, "issues": issue_list, "articles": articles}
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) <= SEARCH_SHARD_BUDGET:
        (data_dir / "search.json").write_text(text, encoding="utf-8")
        return ["data/search.json"]
    # shard by year, newest first
    by_year: dict[int, list[dict]] = {}
    for a in articles:
        by_year.setdefault(int(a.get("year") or 0), []).append(a)
    shards = []
    for year in sorted(by_year, reverse=True):
        name = f"search-{year}.json"
        (data_dir / name).write_text(json.dumps({"generated_at": generated_at, "articles": by_year[year]},
                                                ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        shards.append(name)
    (data_dir / "search.json").write_text(json.dumps({"generated_at": generated_at, "issues": issue_list,
                                                      "articles": [], "shards": shards},
                                                     ensure_ascii=False), encoding="utf-8")
    return ["data/search.json"] + [f"data/{s}" for s in shards]
