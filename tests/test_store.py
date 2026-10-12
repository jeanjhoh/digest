import json
from pathlib import Path

from digest.models import RawRecord
from digest.store import Store


def _wp(**kw):
    base = dict(source_slug="nber", title="Generative AI and the Task Content of Jobs", authors=["Priya Natarajan", "Tom Becker"],
                doi="10.3386/w34001", nber_id="w34001", venue="NBER Working Papers", url="https://www.nber.org/papers/w34001",
                publication_status="working_paper", crossref_type="report", abstract="wp abstract", abstract_source="native")
    base.update(kw)
    return RawRecord(**base)


def test_insert_update_and_persist(tmp_path: Path):
    s = Store(tmp_path)
    a, how = s.upsert(_wp(), "working_paper", "2026-10-01T00:00:00Z")
    assert how == "inserted" and a.key == "doi:10.3386/w34001" and a.nber_id == "w34001"
    a2, how2 = s.upsert(_wp(pdf_url="https://x/pdf"), "working_paper", "2026-10-02T00:00:00Z")
    assert how2 == "updated" and a2 is a and a.pdf_url == "https://x/pdf" and a.last_seen_at.startswith("2026-10-02")
    assert a.first_seen_at.startswith("2026-10-01")
    s.save()
    s2 = Store.load(tmp_path)
    assert len(s2) == 1 and s2.get("doi:10.3386/w34001").title == a.title
    s2.save()
    assert (tmp_path / "articles" / "2026.jsonl").read_text() == (tmp_path / "articles" / "2026.jsonl").read_text()
    line = (tmp_path / "articles" / "2026.jsonl").read_text().splitlines()[0]
    assert json.loads(line)["key"] == "doi:10.3386/w34001"


def test_working_paper_to_journal_merge(tmp_path: Path):
    s = Store(tmp_path)
    s.upsert(_wp(), "working_paper", "2026-10-01T00:00:00Z")
    journal = RawRecord(source_slug="amj", title="Generative AI and the Task Content of Jobs", authors=["P. Natarajan", "T. Becker"],
                        doi="10.5465/amj.2026.1", venue="Academy of Management Journal", url="https://doi.org/10.5465/amj.2026.1",
                        publication_status="published", crossref_type="journal-article", published_at="2026-10-05")
    a, how = s.upsert(journal, "management_journal", "2026-10-06T00:00:00Z")
    assert how == "merged"
    assert a.key == "doi:10.5465/amj.2026.1" and a.publication_status == "published" and a.venue == "Academy of Management Journal"
    assert a.version_count == 2 and "doi:10.3386/w34001" in a.aliases
    assert s.get("doi:10.3386/w34001") is a and len(s) == 1
    assert a.first_seen_at.startswith("2026-10-01")
    assert a.abstract == "wp abstract"
    # re-sighting the WP key resolves to the merged record
    _, how3 = s.upsert(_wp(), "working_paper", "2026-10-07T00:00:00Z")
    assert how3 == "updated" and len(s) == 1
    s.save()
    s2 = Store.load(tmp_path)
    assert s2.get("doi:10.3386/w34001").key == "doi:10.5465/amj.2026.1"


def test_generic_titles_do_not_merge(tmp_path: Path):
    s = Store(tmp_path)
    s.upsert(RawRecord(source_slug="a", title="Introduction", authors=["X Y"], doi="10.1/a"), "c", "2026-10-01T00:00:00Z")
    _, how = s.upsert(RawRecord(source_slug="b", title="Introduction", authors=["Q R"], doi="10.1/b"), "c", "2026-10-01T00:00:00Z")
    assert how == "inserted" and len(s) == 2
    s.upsert(RawRecord(source_slug="a", title="Long Title About Many Different Things Here", authors=["X Y"], doi="10.1/c"), "c", "2026-10-01T00:00:00Z")
    _, how = s.upsert(RawRecord(source_slug="b", title="Long Title About Many Different Things Here", authors=["Other Person"], doi="10.1/d"), "c", "2026-10-01T00:00:00Z")
    assert how == "inserted"


def test_doi_less_records_do_not_collide(tmp_path: Path):
    s = Store(tmp_path)
    s.upsert(RawRecord(source_slug="alerts", title="First Scholar Alert Paper Title"), "alert", "2026-10-01T00:00:00Z")
    _, how = s.upsert(RawRecord(source_slug="alerts", title="Second Scholar Alert Paper Title"), "alert", "2026-10-01T00:00:00Z")
    assert how == "inserted" and len(s) == 2
    assert all(a.doi is None for a in s)


def test_slim_drops_only_non_candidates(tmp_path: Path):
    s = Store(tmp_path)
    a, _ = s.upsert(_wp(), "working_paper", "2026-10-01T00:00:00Z")
    b, _ = s.upsert(RawRecord(source_slug="x", title="Other Paper Entirely", doi="10.1/z", abstract="abs"), "c", "2026-10-01T00:00:00Z")
    a.keyword = {"candidate": True, "max": 5}
    b.keyword = {"candidate": False, "max": 0}
    assert s.slim() == 1 and a.abstract and b.abstract is None and b.abstract_dropped
