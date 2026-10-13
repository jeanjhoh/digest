"""Build the fixture site and verify structure, COinS, checks, and feeds."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from sitebuilder.__main__ import build
from sitebuilder.checks import run_checks
from sitebuilder.config import STATIC_DIR, TEMPLATES_DIR, BuildOptions

FIXTURE = Path(__file__).parent / "fixtures" / "published"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    opts = BuildOptions(data_dir=FIXTURE, out_dir=out, site_url="https://example.org/digest/",
                        templates_dir=TEMPLATES_DIR, static_dir=STATIC_DIR)
    summary = build(opts)
    return out, summary


def test_files_exist(site):
    out, summary = site
    for name in ("index.html", "issues/index.html", "issues/001.html", "issues/002.html", "details.html", "about.html",
                 "llms.html", "llms.txt", "rss.xml", "feed-papers.xml", "sitemap.xml", "robots.txt", "404.html",
                 ".nojekyll", "data/search.json", "data/meta.json", "data/sources.json", "data/issues/002.json",
                 "data/latest.json", "app.js", "styles.css", "photo.jpg"):
        assert (out / name).exists(), name
    assert summary["issues"] == 2 and summary["articles"] == 9
    assert len(list((out / "p").glob("*.html"))) == 9


def test_checks_pass(site):
    out, _ = site
    assert run_checks(out) == []


def test_coins_count_matches_articles(site):
    out, _ = site
    for n in (1, 2):
        html = (out / "issues" / f"{n:03d}.html").read_text(encoding="utf-8")
        data = json.loads((FIXTURE / "issues" / f"{n:03d}.json").read_text(encoding="utf-8"))
        assert html.count('class="Z3988"') == len(data["articles"])
    index = (out / "index.html").read_text(encoding="utf-8")
    assert index.count('class="Z3988"') == 6


def test_entry_markup(site):
    out, _ = site
    index = (out / "index.html").read_text(encoding="utf-8")
    assert '<details class="abstract">' in index
    assert "No abstract available." in index  # the ASR article has no abstract
    assert 'class="entry-note"' in index
    assert 'class="on" href="index.html" aria-current="page">Digest' in index
    assert "data-score" in index
    assert 'class="score"' not in index  # relevance score is never displayed
    assert 'id="issue-data"' in index
    assert "rft.genre=report" in index and "rft.genre=article" in index
    assert "Highlights" in index


def test_permalink_highwire(site):
    out, _ = site
    html = (out / "p" / "doi-10.1257-aer.20264444.html").read_text(encoding="utf-8")
    assert '<meta name="citation_title"' in html
    assert html.count('<meta name="citation_author"') == 2
    assert '<meta name="citation_doi" content="10.1257/aer.20264444">' in html
    assert '<meta name="citation_abstract"' in html
    assert '<meta name="citation_volume" content="116">' in html
    nber = (out / "p" / "doi-10.3386-w34001.html").read_text(encoding="utf-8")
    assert "citation_pdf_url" in nber and "citation_technical_report_institution" in nber


def test_feeds_parse(site):
    out, _ = site
    rss = ET.parse(out / "rss.xml").getroot()
    assert len(rss.findall("./channel/item")) == 2
    papers = ET.parse(out / "feed-papers.xml").getroot()
    items = papers.findall("./channel/item")
    assert len(items) == 9
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    assert items[0].find("dc:creator", ns) is not None
    sm = ET.parse(out / "sitemap.xml").getroot()
    assert len(sm) >= 5 + 2 + 9


def test_search_index(site):
    out, _ = site
    d = json.loads((out / "data" / "search.json").read_text(encoding="utf-8"))
    assert len(d["articles"]) == 9
    a = d["articles"][0]
    assert a["issue_number"] == 2 and "coins" in a and "abstract" in a and "bibtex" not in a


def test_llms_txt_has_abstracts(site):
    out, _ = site
    txt = (out / "llms.txt").read_text(encoding="utf-8")
    assert "Abstract:" in txt and "No. 002" in txt and "{{" not in txt


def test_no_template_leaks(site):
    out, _ = site
    for f in out.rglob("*.html"):
        t = f.read_text(encoding="utf-8")
        assert "{{" not in t and "{%" not in t, f
        assert not re.search(r">\s*None\s*<", t), f
