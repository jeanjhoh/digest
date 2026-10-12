"""Stage 1: zero-cost keyword scoring against config/topics.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Term:
    text: str
    weight: int
    pattern: re.Pattern[str]

    def hits(self, text: str) -> bool:
        return bool(self.pattern.search(text))


def _compile(term: dict[str, Any]) -> Term:
    t = str(term["t"]).lower()
    w = int(term.get("w", 1))
    if term.get("word"):
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(t.strip()) + r"(?![a-z0-9])")
    else:
        pat = re.compile(re.escape(t))
    return Term(t, w, pat)


class KeywordScorer:
    def __init__(self, topics: dict[str, Any]) -> None:
        self.sets: dict[str, dict[str, list[Term]]] = {}
        for sid, s in topics["sets"].items():
            self.sets[sid] = {"core": [_compile(x) for x in s.get("core", [])],
                              "context": [_compile(x) for x in s.get("context", [])],
                              "require_context": bool(s.get("require_context", False))}
        self.negative = [_compile(x) for x in topics.get("negative", [])]

    @staticmethod
    def _score_terms(terms: list[Term], title: str, abstract: str) -> tuple[int, list[str]]:
        total, reasons = 0, []
        for t in terms:
            if t.hits(title):
                total += 2 * t.weight
                reasons.append(t.text)
            elif t.hits(abstract):
                total += t.weight
                reasons.append(t.text)
        return total, reasons

    def score(self, title: str, abstract: str | None) -> dict[str, Any]:
        title_l = (title or "").lower()
        abs_l = (abstract or "").lower()
        neg, _ = self._score_terms(self.negative, title_l, abs_l)
        scores: dict[str, int] = {}
        reasons: dict[str, list[str]] = {}
        for sid, groups in self.sets.items():
            core, core_r = self._score_terms(groups["core"], title_l, abs_l)
            ctx, ctx_r = (0, [])
            if core > 0:
                ctx, ctx_r = self._score_terms(groups["context"], title_l, abs_l)
            if groups["require_context"] and ctx == 0:
                core, core_r = 0, []  # e.g. AI papers with no work/labor angle are out of scope by definition
            s = max(0, core + ctx - neg)
            scores[sid] = s
            if core_r or ctx_r:
                reasons[sid] = core_r + ctx_r
        best = max(scores.values()) if scores else 0
        return {"scores": scores, "reasons": reasons, "max": best}


def is_candidate(result: dict[str, Any], source: Any) -> bool:
    return bool(source.always_candidate) or int(result.get("max", 0)) >= int(source.min_score)


def reasons_list(keyword: dict[str, Any] | None) -> list[str]:
    if not keyword:
        return []
    return [f"{sid}:{', '.join(terms[:4])}" for sid, terms in (keyword.get("reasons") or {}).items() if terms]
