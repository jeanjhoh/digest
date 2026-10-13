"""COinS / BibTeX / citation unit tests."""
from urllib.parse import parse_qs

from sitebuilder import cite
from sitebuilder.model import Article, split_author


def _art(**kw):
    base = dict(canonical_key="doi:10.1/x", title="A & B: 100% Résumé", authors=["Élodie Durand-Lévy", "J. R. R. Tolkien"],
                venue="Journal of Tests", source_slug="jt", source_category="management_journal", publication_status="published",
                issue_number=1, sets=["ai_work"], relevance_score=5, recommended=False, doi="10.1/x",
                primary_url="https://doi.org/10.1/x", published_at="2026-01-02", year=2026, volume="3", issue="2", pages="10-20")
    base.update(kw)
    return Article.from_dict(base)


def test_split_author():
    assert split_author("Jane Q. Doe") == ("Doe", "Jane Q.")
    assert split_author("Doe, Jane") == ("Doe", "Jane")
    assert split_author("Plato") == ("Plato", "")


def test_coins_journal_encoding():
    kev = cite.coins_kev(_art())
    q = parse_qs(kev)
    assert q["rft_val_fmt"] == ["info:ofi/fmt:kev:mtx:journal"]
    assert q["rft.genre"] == ["article"]
    assert q["rft.atitle"] == ["A & B: 100% Résumé"]
    assert q["rft.au"] == ["Durand-Lévy, Élodie", "Tolkien, J. R. R."]
    assert q["rft.aulast"] == ["Durand-Lévy"] and q["rft.aufirst"] == ["Élodie"]
    assert q["rft.spage"] == ["10"] and q["rft.epage"] == ["20"] and q["rft.volume"] == ["3"]
    assert q["rft_id"] == ["info:doi/10.1/x"]
    assert "%26" in kev and "%25" in kev and "&rft.atitle=A%20%26%20B" in kev


def test_coins_report():
    a = _art(publication_status="working_paper", doi="10.3386/w1", nber_id="w1", primary_url="https://www.nber.org/papers/w1",
             venue="NBER Working Papers", volume=None, issue=None, pages=None)
    q = parse_qs(cite.coins_kev(a))
    assert q["rft_val_fmt"] == ["info:ofi/fmt:kev:mtx:book"]
    assert q["rft.genre"] == ["report"] and q["rft.btitle"] == [a.title] and q["rft.series"] == ["NBER Working Papers"]
    assert "info:doi/10.3386/w1" in q["rft_id"] and "https://www.nber.org/papers/w1" in q["rft_id"]


def test_bibtex_and_plain():
    a = _art()
    bib = cite.bibtex(a)
    assert bib.startswith("@article{durandlevy2026b,") or bib.startswith("@article{durandlvy2026b,")
    assert "title = {A \\& B: 100\\% Résumé}" in bib
    assert "author = {Durand-Lévy, Élodie and Tolkien, J. R. R.}" in bib
    assert "pages = {10-20}" in bib and bib.rstrip().endswith("}")
    plain = cite.plain_citation(a)
    assert plain.startswith("Durand-Lévy, É., & Tolkien, J. R. R. (2026). A & B: 100% Résumé. Journal of Tests, 3(2), 10-20.")
    assert plain.endswith("https://doi.org/10.1/x")


def test_highwire():
    tags = dict(cite.highwire_meta(_art(pdf_url="https://x/y.pdf", abstract="Abs.")))
    assert tags["citation_title"] == "A & B: 100% Résumé"
    assert tags["citation_pdf_url"] == "https://x/y.pdf" and tags["citation_abstract"] == "Abs."
    assert tags["citation_publication_date"] == "2026/01/02"
