"""Load config/*.yaml, config/profile.md and environment variables."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = Path(os.environ.get("DIGEST_DATA_DIR") or (BASE_DIR / "data"))

CATEGORY_LABELS = [
    ("management_journal", "Management journals"),
    ("sociology_journal", "Sociology journals"),
    ("economics_journal", "Economics journals"),
    ("science_journal", "General science journals"),
    ("working_paper", "Working papers"),
    ("preprint", "Preprints"),
    ("alert", "Email alerts"),
]
PUBLICATION_STATUSES = {"published": "Published", "working_paper": "Working paper", "preprint": "Preprint"}


def _load_env() -> None:
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
        except ImportError:  # pragma: no cover
            pass


@dataclass
class Source:
    slug: str
    name: str
    kind: str
    category: str
    tier: str
    enabled: bool = True
    issn: list[str] = field(default_factory=list)
    prefix: str | None = None
    query: str | None = None
    report: str | None = None
    url: str | None = None
    min_score: int = 2
    always_candidate: bool = False

    @property
    def method(self) -> str:
        gate = "every paper is classified" if self.always_candidate else f"keyword-gated (min score {self.min_score})"
        if self.kind == "crossref_journal":
            return f"Crossref works for ISSN {', '.join(self.issn)} (journal-article type) created within the run window; {gate}."
        if self.kind == "crossref_prefix":
            return f"Crossref works with DOI prefix {self.prefix} created within the run window; {gate}."
        if self.kind == "arxiv":
            return f"arXiv API query `{self.query}` sorted by submission date within the run window; {gate}."
        if self.kind == "repec_nep":
            return f"RePEc NEP report {self.report} RSS feed (latest issue); {gate}."
        if self.kind == "gsheet":
            return f"Google Sheet of SSRN and Google Scholar alert emails, resolved via Crossref by DOI or title; {gate}."
        return gate


@dataclass
class Settings:
    window_days: int
    bootstrap_window_days: int
    enrich_max_age_days: int
    llm: dict[str, Any]
    http: dict[str, Any]
    site: dict[str, Any]
    sources: list[Source]
    topics: dict[str, Any]
    profile: str
    anthropic_api_key: str
    crossref_mailto: str
    gsheet_csv_url: str
    s2_api_key: str
    data_dir: Path = DATA_DIR

    @property
    def sets(self) -> list[dict[str, str]]:
        out = []
        for sid, s in self.topics["sets"].items():
            out.append({"id": sid, "label": s["label"], "short": s.get("short", s["label"]),
                        "description": " ".join(str(s.get("description", "")).split())})
        return out

    def source(self, slug: str) -> Source | None:
        for s in self.sources:
            if s.slug == slug:
                return s
        return None


def _parse_sources(raw: dict[str, Any]) -> list[Source]:
    defaults = raw.get("defaults", {})
    tiers = raw.get("tiers", {})
    out = []
    for item in raw["sources"]:
        d = {**defaults, **item}
        tier = d.get("tier", "B")
        t = tiers.get(tier, {})
        issn = d.get("issn") or []
        if isinstance(issn, str):
            issn = [issn]
        out.append(Source(
            slug=d["slug"], name=d["name"], kind=d.get("kind", "crossref_journal"), category=d["category"],
            tier=tier, enabled=bool(d.get("enabled", True)), issn=[str(x) for x in issn],
            prefix=d.get("prefix"), query=d.get("query"), report=d.get("report"), url=d.get("url"),
            min_score=int(d.get("min_score", t.get("min_score", 2))),
            always_candidate=bool(d.get("always_candidate", t.get("always_candidate", False))),
        ))
    return out


def load_settings(config_dir: Path = CONFIG_DIR, data_dir: Path = DATA_DIR) -> Settings:
    _load_env()
    settings_raw = yaml.safe_load((config_dir / "settings.yaml").read_text()) or {}
    sources_raw = yaml.safe_load((config_dir / "sources.yaml").read_text()) or {}
    topics = yaml.safe_load((config_dir / "topics.yaml").read_text()) or {}
    profile = (config_dir / "profile.md").read_text().strip()
    mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
    if not mailto:
        mailto = "digest@example.org"
        print("warning: CROSSREF_MAILTO not set; using a placeholder (set it for Crossref's polite pool)", file=sys.stderr)
    return Settings(
        window_days=int(settings_raw.get("window_days", 8)),
        bootstrap_window_days=int(settings_raw.get("bootstrap_window_days", 14)),
        enrich_max_age_days=int(settings_raw.get("enrich_max_age_days", 35)),
        llm=settings_raw.get("llm", {}),
        http=settings_raw.get("http", {}),
        site=settings_raw.get("site", {}),
        sources=_parse_sources(sources_raw),
        topics=topics,
        profile=profile,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        crossref_mailto=mailto,
        gsheet_csv_url=os.environ.get("GSHEET_CSV_URL", ""),
        s2_api_key=os.environ.get("S2_API_KEY", ""),
        data_dir=data_dir,
    )
