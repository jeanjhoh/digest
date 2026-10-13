"""Weekly issues keyed by ISO week."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .models import Issue, iso
from .store import Store


class Issues:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: list[Issue] = []

    @classmethod
    def load(cls, data_dir: Path) -> "Issues":
        s = cls(Path(data_dir) / "issues.json")
        if s.path.exists():
            raw = json.loads(s.path.read_text(encoding="utf-8"))
            s.items = [Issue.from_dict(x) for x in raw.get("issues", [])]
        return s

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"issues": [i.to_dict() for i in self.items]}, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def latest(self) -> Issue | None:
        return max(self.items, key=lambda i: i.number) if self.items else None

    @staticmethod
    def week_key(dt: datetime) -> str:
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"

    def get_or_create(self, now: datetime, window_days: int) -> tuple[Issue, bool]:
        key = self.week_key(now)
        for i in self.items:
            if i.key == key:
                return i, False
        latest = self.latest
        number = (latest.number + 1) if latest else 1
        window_start = latest.cutoff_at if latest else iso(now - timedelta(days=window_days))
        issue = Issue(number=number, key=key, window_start=window_start, cutoff_at=iso(now), created_at=iso(now))
        self.items.append(issue)
        return issue, True

    @staticmethod
    def assign(store: Store, issue: Issue) -> int:
        n = 0
        for a in store:
            if a.in_scope and not a.hidden and a.issue_number is None:
                a.issue_number = issue.number
                n += 1
        return n

    @staticmethod
    def finalize(issue: Issue, store: Store, set_ids: list[str]) -> None:
        arts = list(store.iter_issue(issue.number))
        by_set = {s: 0 for s in set_ids}
        by_cat: dict[str, int] = {}
        for a in arts:
            for s in (a.classification or {}).get("sets", []):
                if s in by_set:
                    by_set[s] += 1
            by_cat[a.source_category] = by_cat.get(a.source_category, 0) + 1
        issue.counts = {"in_scope": len(arts), "recommended": sum(1 for a in arts if a.recommended),
                        "by_set": by_set, "by_category": by_cat}
