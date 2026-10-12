"""Identifier and title normalization, canonical keys, and the front-matter filter."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import date, datetime, timezone

from .models import RawRecord

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>?#&]+", re.I)
ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:)(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
SSRN_RE = re.compile(r"(?:ssrn\.com/(?:abstract=|sol3/papers\.cfm\?abstract_id=)|ssrn\.(\d+)$)(\d+)?", re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
TRAILING_QUALIFIER_RE = re.compile(
    r"\s*[\(\[](?:revised|revised version|working paper|preprint|draft|forthcoming|online first)[\)\]]\s*$", re.I)
LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+")


def normalize_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    s = s.strip().rstrip(".,;)")
    return s.lower() or None


def extract_doi(text: str | None) -> str | None:
    if not text:
        return None
    m = DOI_RE.search(text)
    return normalize_doi(m.group(0)) if m else None


def extract_arxiv_id(text: str | None) -> str | None:
    if not text:
        return None
    m = ARXIV_RE.search(text)
    return m.group(1) if m else None


def extract_ssrn_id(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"abstract(?:_id)?=(\d+)", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"10\.2139/ssrn\.(\d+)", text, re.I)
    return m.group(1) if m else None


def strip_markup(text: str | None) -> str:
    if not text:
        return ""
    s = html.unescape(TAG_RE.sub(" ", text))
    return WS_RE.sub(" ", s).strip()


def strip_jats(text: str | None) -> str | None:
    """Clean a Crossref JATS abstract: drop tags, a leading 'Abstract' label, and extra whitespace."""
    if not text:
        return None
    s = strip_markup(text)
    s = re.sub(r"^(?:abstract|summary)\s*[:.\-–]?\s*", "", s, flags=re.I)
    return s.strip() or None


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    s = strip_markup(title)
    s = re.sub(r"\$[^$]*\$", " ", s)  # latex math
    s = re.sub(r"[\u2010-\u2015\u2212\u00ad]", "-", s)  # unicode hyphens/dashes → ascii
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("&", " and ")
    s = TRAILING_QUALIFIER_RE.sub("", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = WS_RE.sub(" ", s).strip()
    s = LEADING_ARTICLE_RE.sub("", s)
    return s


def title_hash(normalized: str) -> str:
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def canonical_key(rec: RawRecord) -> str:
    if rec.doi:
        return f"doi:{rec.doi}"
    if rec.arxiv_id:
        return f"arxiv:{rec.arxiv_id}"
    if rec.ssrn_id:
        return f"ssrn:{rec.ssrn_id}"
    if rec.repec_handle:
        return f"repec:{rec.repec_handle}"
    return f"title:{title_hash(normalize_title(rec.title))}"


def nber_id_from_doi(doi: str | None) -> str | None:
    if doi and doi.startswith("10.3386/"):
        return doi.split("/", 1)[1]
    return None


ALLOWED_CROSSREF_TYPES = {None, "journal-article", "report", "posted-content", "proceedings-article", "report-component"}

FRONT_MATTER_RE = re.compile(r"""^\s*(?:
    issue\ information|editorial\ board|editorial\ note|editorial\b|front\ matter|back\ matter|masthead|
    table\ of\ contents|contents\b|cover\b|title\ page|copyright|
    erratum|errata|corrigend(?:um|a)|correction(?:s)?(?:\ to)?\b|retraction|retracted|
    call\ for\ papers|announcement(?:s)?|books?\ received|book\ review(?:s)?\b|
    (?:list\ of|thanks?\ to|acknowledg(?:e)?ments?\ (?:of|to))\ (?:our\ )?reviewers?|reviewers?\ (?:list|acknowledgment)|
    acknowledg(?:e)?ments?\b|(?:subject|author|volume|annual)\ index|index\ to\ volume|
    editor(?:['’]s|s['’]?|ial)\ (?:note|introduction|comment|letter|statement)|from\ the\ editors?|in\ this\ issue|
    in\ memoriam|obituary|forthcoming\ papers|preface|introduction\ to\ the\ (?:special\ )?(?:issue|symposium)|
    news\ and\ notes|referees?\b|daily\ briefing|news\ (?:and|&)\ views|research\ highlights?|
    (?:author|publisher)\ correction|correspondence|world\ view|career\ (?:column|feature)|where\ i\ work
)\b""", re.I | re.X)
UPDATE_RE = re.compile(r"\b(?:erratum|corrigendum|correction|retraction)\s+(?:to|of|for)\b", re.I)
BOOK_REVIEW_RE = re.compile(r"\bby\b.+\b(?:press|university|publishers?|pp\.|\$\d)", re.I)


def is_front_matter(rec: RawRecord) -> tuple[bool, str]:
    if rec.crossref_type not in ALLOWED_CROSSREF_TYPES:
        return True, f"type:{rec.crossref_type}"
    title = strip_markup(rec.title)
    if not title:
        return True, "no-title"
    if FRONT_MATTER_RE.search(title) or UPDATE_RE.search(title):
        return True, "title:front-matter"
    if not rec.authors and len(title) < 40:
        return True, "no-authors-short-title"
    if not rec.abstract and not rec.authors:
        return True, "no-authors-no-abstract"
    if not rec.abstract and BOOK_REVIEW_RE.search(title):
        return True, "title:book-review"
    return False, ""


def date_parts_to_iso(parts: list[list[int]] | None) -> str | None:
    if not parts or not parts[0] or parts[0][0] is None:
        return None
    p = parts[0]
    y = int(p[0])
    m = int(p[1]) if len(p) > 1 and p[1] else 1
    d = int(p[2]) if len(p) > 2 and p[2] else 1
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_iso_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
    except ValueError:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def author_display(given: str | None, family: str | None, name: str | None = None) -> str:
    if name:
        return WS_RE.sub(" ", name).strip()
    return WS_RE.sub(" ", f"{given or ''} {family or ''}").strip()


def family_name(display: str) -> str:
    s = normalize_title(display)
    return s.split()[-1] if s else ""
