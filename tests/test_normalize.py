from digest.models import RawRecord
from digest.normalize import (canonical_key, extract_doi, is_front_matter, nber_id_from_doi, normalize_doi,
                              normalize_title, strip_jats)


def test_normalize_doi_variants():
    assert normalize_doi("https://doi.org/10.1177/ABC.123") == "10.1177/abc.123"
    assert normalize_doi("http://dx.doi.org/10.1/x.") == "10.1/x"
    assert normalize_doi("doi:10.1/X") == "10.1/x"
    assert normalize_doi("") is None and normalize_doi(None) is None


def test_extract_doi_from_url():
    assert extract_doi("https://pubsonline.informs.org/doi/full/10.1287/orsc.2025.21838?x=1") == "10.1287/orsc.2025.21838"
    assert extract_doi("https://iris.unibocconi.it/handle/11565/4080356") is None


def test_normalize_title():
    assert normalize_title("The Marginal Propensity to Hire (Revised)") == "marginal propensity to hire"
    assert normalize_title("Élite &amp; Inequality: A <i>Study</i>") == "elite and inequality a study"
    assert normalize_title("Self‐Employment, Automation, and $\\beta$") == "self employment automation and"


def test_canonical_key_priority():
    r = RawRecord(source_slug="x", title="A Paper About Things", doi="10.1/a", arxiv_id="2401.0001")
    assert canonical_key(r) == "doi:10.1/a"
    r.doi = None
    assert canonical_key(r) == "arxiv:2401.0001"
    r.arxiv_id = None
    r.ssrn_id = "123"
    assert canonical_key(r) == "ssrn:123"
    r.ssrn_id = None
    assert canonical_key(r).startswith("title:") and len(canonical_key(r)) == len("title:") + 16
    # two DOI-less records with different titles never collide
    r2 = RawRecord(source_slug="x", title="Another Paper")
    assert canonical_key(r) != canonical_key(r2)


def test_nber_id():
    assert nber_id_from_doi("10.3386/w34210") == "w34210"
    assert nber_id_from_doi("10.1/x") is None


def test_strip_jats():
    assert strip_jats("<jats:p>Abstract: We study &amp; find.</jats:p>") == "We study & find."
    assert strip_jats("") is None


def _rec(title, authors=("A Smith",), abstract="abs", ctype="journal-article"):
    return RawRecord(source_slug="s", title=title, authors=list(authors), abstract=abstract, crossref_type=ctype)


def test_front_matter_titles():
    for t in ["Issue Information", "Editorial Board", "Erratum to: Founders and Finance", "Correction: Something",
              "Call for Papers: AI and Work", "Book Review: de Rond, M. Dark Justice", "Thanks to Reviewers",
              "Masthead", "Corrigendum", "Editor's Note", "In Memoriam: J. Doe", "Table of Contents"]:
        assert is_front_matter(_rec(t))[0], t


def test_front_matter_type_and_heuristics():
    assert is_front_matter(_rec("Real Paper", ctype="journal-issue"))[0]
    assert is_front_matter(_rec("Contents", authors=(), abstract=None))[0]
    assert is_front_matter(_rec("The Great Novel by Jane Doe, Oxford University Press, 320 pp.", abstract=None))[0]
    assert not is_front_matter(_rec("Racial Promotion Gaps"))[0]
    assert not is_front_matter(_rec("A Study With No Abstract But Authors and a Long Title", abstract=None))[0]
    assert not is_front_matter(RawRecord(source_slug="arx", title="LLMs and Work", authors=["A B"], abstract="x",
                                         crossref_type="posted-content"))[0]


def test_nature_news_items_filtered():
    for t in ["Daily briefing: Physics Nobel for founder of neutrino-hunting observatory", "Author Correction: Something",
              "Research Highlights: AI", "News & Views: Work and AI"]:
        assert is_front_matter(_rec(t))[0], t
