import json
from pathlib import Path

from digest.models import RawRecord
from digest.normalize import is_front_matter
from digest.settings import Source
from digest.sources.crossref import parse_item

FIX = Path(__file__).resolve().parent / "fixtures" / "crossref"
JBV = Source(slug="jbv", name="Journal of Business Venturing", kind="crossref_journal", category="management_journal", tier="B", issn=["0883-9026"])
ASQ = Source(slug="asq", name="Administrative Science Quarterly", kind="crossref_journal", category="management_journal", tier="A", issn=["0001-8392"])
NBER = Source(slug="nber", name="NBER Working Papers", kind="crossref_prefix", category="working_paper", tier="B", prefix="10.3386")


def _load(name):
    return json.loads((FIX / name).read_text())


def test_journal_item_has_abstract_and_authors():
    item = _load("journal_with_abstract.json"); rec = parse_item(item, JBV)
    assert isinstance(rec, RawRecord)
    assert rec.abstract and rec.abstract_source == "crossref" and not rec.abstract.lower().startswith("abstract")
    assert "<" not in rec.abstract
    assert rec.authors and rec.author_parts[0]["family"]
    assert rec.doi and rec.doi == rec.doi.lower() and rec.venue == item["container-title"][0]
    assert rec.publication_status == "published" and rec.crossref_type == "journal-article"
    assert rec.first_available_at and rec.first_available_at <= (rec.published_at or "9999")
    assert not is_front_matter(rec)[0]


def test_sage_book_review_is_filtered():
    rec = parse_item(_load("asq_book_review.json"), ASQ)
    assert rec.abstract is None and rec.pdf_url and rec.pdf_url.endswith(".pdf") or "/pdf/" in (rec.pdf_url or "")
    fm, reason = is_front_matter(rec)
    assert fm and reason == "title:front-matter"


def test_nber_prefix_item_derives_nber_id():
    rec = parse_item(_load("nber_report.json"), NBER)
    assert rec.nber_id == "w35838" and rec.doi == "10.3386/w35838"
    assert rec.publication_status == "working_paper" and rec.venue == "NBER Working Papers"
    assert rec.crossref_type == "report" and not is_front_matter(rec)[0]
    assert rec.published_at and rec.published_at.startswith("2026-10")


def test_journal_issue_type_is_filtered():
    rec = parse_item(_load("journal_issue.json"), ASQ)
    assert is_front_matter(rec) == (True, "type:journal-issue")
