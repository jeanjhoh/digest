"""Build configuration: paths, budgets, and site defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
ROOT_DIR = PKG_DIR.parent
TEMPLATES_DIR = ROOT_DIR / "web" / "templates"
STATIC_DIR = ROOT_DIR / "web" / "static"

# Size budgets enforced by ``sitebuilder check``.
BUDGETS = {
    "index.html": 1_000_000,   # a 14-day bootstrap issue of ~50 papers is ~410 KB
    "app.js": 40_000,
    "styles.css": 40_000,
}
SEARCH_SHARD_BUDGET = 4_000_000

SITE_DEFAULTS = {
    "title": "Weekly Research Digest",
    "nav_label": "Digest",
    "tagline": "New research on entrepreneurship, generative AI and work, and organizations and inequality",
    "url": "https://jeanjhoh.github.io/digest/",
    "parent_url": "https://jeanoh.org/",
    "owner": "Jean Joohyun Oh",
    "owner_role": "Assistant Professor, Tepper School of Business, Carnegie Mellon University",
    "publish_day": "Wednesday",
}

RFR_ID = "info:sid/jeanoh.org:digest"
PICKS_CAP = 12
PAPER_FEED_LIMIT = 200
BOOTSTRAP_ICONS_CSS = "https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.11.3/font/bootstrap-icons.min.css"


@dataclass
class BuildOptions:
    data_dir: Path
    out_dir: Path
    site_url: str | None = None
    strict: bool = False
    templates_dir: Path = field(default=TEMPLATES_DIR)
    static_dir: Path = field(default=STATIC_DIR)
