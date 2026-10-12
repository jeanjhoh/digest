import json
from datetime import datetime, timezone
from pathlib import Path

from digest.issues import Issues
from digest.models import RawRecord
from digest.publish import publish
from digest.settings import load_settings
from digest.store import Store

FIX = Path(__file__).resolve().parent / "fixtures" / "published"


def _keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out.add(prefix + k)
        if isinstance(v, dict) and k in ("site", "stats", "last_run", "totals"):
            out |= _keys(v, prefix + k + ".")
    return out


def test_publish_matches_fixture_contract(tmp_path):
    s = load_settings()
    s.data_dir = tmp_path
    store = Store(tmp_path)
    a, _ = store.upsert(RawRecord(source_slug="asq", title="Class Signals in the Pitch", authors=["Maria Alvarez", "Daniel K. Park"],
                                  author_parts=[{"given": "Maria", "family": "Alvarez"}], abstract="We study founders.", abstract_source="crossref",
                                  doi="10.1177/1", venue="Administrative Science Quarterly", url="https://doi.org/10.1177/1",
                                  published_at="2026-10-03", crossref_type="journal-article"), "management_journal", "2026-10-07T10:00:00Z")
    a.keyword = {"scores": {"entrepreneurship": 6}, "reasons": {"entrepreneurship": ["founder", "seed funding"]}, "max": 6, "candidate": True}
    a.classification = {"model": "m", "at": "x", "sets": ["entrepreneurship", "orgs_inequality"], "relevance": 9, "note": "Founder class origins.", "flags": [], "basis": "title+abstract"}
    a.in_scope, a.recommended = True, True
    b, _ = store.upsert(RawRecord(source_slug="nber", title="Generative AI and Jobs", doi="10.3386/w1", nber_id="w1", venue="NBER Working Papers",
                                  url="https://www.nber.org/papers/w1", publication_status="working_paper", crossref_type="report"), "working_paper", "2026-10-07T10:00:00Z")
    b.keyword = {"scores": {}, "reasons": {}, "max": 3, "candidate": True}
    b.classification = {"model": "m", "at": "x", "sets": [], "relevance": 2, "note": None, "flags": [], "basis": "title_only"}
    hidden, _ = store.upsert(RawRecord(source_slug="asq", title="Editorial Something Long Enough", doi="10.1177/2", venue="ASQ", url="u",
                                       crossref_type="journal-article"), "management_journal", "2026-10-07T10:00:00Z")
    hidden.in_scope, hidden.hidden = True, True
    issues = Issues.load(tmp_path)
    issue, _ = issues.get_or_create(datetime(2026, 10, 7, 10, tzinfo=timezone.utc), 14)
    Issues.assign(store, issue)
    Issues.finalize(issue, store, [x["id"] for x in s.sets])
    state = {"asq": {"last_checked_at": "2026-10-07T10:00:00Z", "last_status": "ok", "last_error": None,
                     "last_run": {"pulled": 1, "in_scope": 1}, "totals": {"pulled": 1, "in_scope": 1}, "latest_in_scope_at": "2026-10-03"}}
    out = publish(s, out_dir=tmp_path / "published", store=store, issues=issues, source_state=state)

    meta = json.loads((out / "meta.json").read_text())
    fmeta = json.loads((FIX / "meta.json").read_text())
    assert _keys(meta) == _keys(fmeta)
    assert set(meta["issues"][0]) == set(fmeta["issues"][0])
    assert [c["id"] for c in meta["categories"]] == [c["id"] for c in fmeta["categories"]]
    assert set(meta["sets"][0]) == set(fmeta["sets"][0]) and [x["id"] for x in meta["sets"]] == ["entrepreneurship", "ai_work", "orgs_inequality"]
    assert meta["latest_issue"] == 1 and meta["issues"][0]["count"] == 1 and meta["issues"][0]["recommended_count"] == 1
    assert meta["site"]["title"] == "Weekly Research Digest"

    sources = json.loads((out / "sources.json").read_text())
    fsources = json.loads((FIX / "sources.json").read_text())
    assert set(sources[0]) == set(fsources[0])
    assert {x["slug"] for x in sources} >= {"asq", "nber", "alerts"}
    asq = next(x for x in sources if x["slug"] == "asq")
    assert asq["tier"] == "A" and asq["last_status"] == "ok" and asq["totals"]["in_scope"] == 1

    issue1 = json.loads((out / "issues" / "001.json").read_text())
    fissue = json.loads((FIX / "issues" / "001.json").read_text())
    assert set(issue1) == set(fissue)
    assert len(issue1["articles"]) == 1  # out-of-scope and hidden articles are excluded
    art = issue1["articles"][0]
    assert set(art) == set(fissue["articles"][0])
    assert art["sets"] == ["entrepreneurship", "orgs_inequality"] and art["relevance_score"] == 9 and art["recommended"]
    assert art["abstract"] == "We study founders." and art["abstract_source"] == "crossref" and art["year"] == 2026
    assert art["relevance_reasons"] == ["entrepreneurship:founder, seed funding"] and art["paper_url"] == "https://doi.org/10.1177/1"
