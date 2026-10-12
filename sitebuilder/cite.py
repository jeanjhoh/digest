"""Citation helpers: COinS (OpenURL KEV), Highwire meta tags, BibTeX, plain citation."""
from __future__ import annotations

import re
from urllib.parse import quote

from .config import RFR_ID
from .model import Article, split_author


def _q(v: str) -> str:
    return quote(str(v), safe="")


def coins_kev(a: Article) -> str:
    """Return the KEV string for a ``<span class="Z3988" title="...">``.

    Journal articles use the journal format; working papers and preprints use
    the book format with genre=report so Zotero imports them as Reports with
    the series preserved.
    """
    pairs: list[tuple[str, str]] = [("ctx_ver", "Z39.88-2004"), ("rfr_id", RFR_ID)]
    if a.is_journal:
        pairs += [("rft_val_fmt", "info:ofi/fmt:kev:mtx:journal"), ("rft.genre", "article"),
                  ("rft.atitle", a.title), ("rft.jtitle", a.venue)]
        if a.issn:
            pairs.append(("rft.issn", a.issn))
        for k, v in (("rft.volume", a.volume), ("rft.issue", a.issue)):
            if v:
                pairs.append((k, v))
        if a.pages:
            sp, _, ep = a.pages.replace("–", "-").partition("-")
            pairs.append(("rft.spage", sp.strip()))
            if ep.strip():
                pairs.append(("rft.epage", ep.strip()))
    else:
        pairs += [("rft_val_fmt", "info:ofi/fmt:kev:mtx:book"), ("rft.genre", "report"),
                  ("rft.btitle", a.title), ("rft.series", a.venue)]
        if a.nber_id:
            pairs.append(("rft.pub", "National Bureau of Economic Research"))
    for i, name in enumerate(a.authors):
        fam, giv = split_author(name)
        pairs.append(("rft.au", f"{fam}, {giv}" if giv else fam))
        if i == 0:
            pairs.append(("rft.aulast", fam))
            if giv:
                pairs.append(("rft.aufirst", giv))
    if a.published_at:
        pairs.append(("rft.date", a.published_at))
    elif a.year:
        pairs.append(("rft.date", str(a.year)))
    pairs.append(("rft.language", "en"))
    if a.doi:
        pairs.append(("rft_id", f"info:doi/{a.doi}"))
    if a.primary_url and not (a.doi and a.primary_url.lower().startswith("https://doi.org/")):
        pairs.append(("rft_id", a.primary_url))
    elif a.primary_url and not a.doi:
        pairs.append(("rft_id", a.primary_url))
    return "&".join(f"{k}={_q(v)}" for k, v in pairs)


def highwire_meta(a: Article) -> list[tuple[str, str]]:
    tags: list[tuple[str, str]] = [("citation_title", a.title)]
    tags += [("citation_author", n) for n in a.authors]
    if a.published_at:
        tags.append(("citation_publication_date", a.published_at.replace("-", "/")))
    elif a.year:
        tags.append(("citation_publication_date", str(a.year)))
    if a.is_journal:
        tags.append(("citation_journal_title", a.venue))
        if a.issn:
            tags.append(("citation_issn", a.issn))
        for k, v in (("citation_volume", a.volume), ("citation_issue", a.issue)):
            if v:
                tags.append((k, v))
        if a.pages:
            sp, _, ep = a.pages.replace("–", "-").partition("-")
            tags.append(("citation_firstpage", sp.strip()))
            if ep.strip():
                tags.append(("citation_lastpage", ep.strip()))
    else:
        tags.append(("citation_technical_report_institution", a.venue))
    if a.doi:
        tags.append(("citation_doi", a.doi))
    if a.arxiv_id:
        tags.append(("citation_arxiv_id", a.arxiv_id))
    if a.pdf_url:
        tags.append(("citation_pdf_url", a.pdf_url))
    if a.primary_url:
        tags.append(("citation_abstract_html_url", a.primary_url))
    if a.abstract:
        tags.append(("citation_abstract", a.abstract))
    return tags


_KEY_CLEAN = re.compile(r"[^a-z0-9]+")
_STOP = {"a", "an", "the", "on", "of", "in", "and", "for", "to", "from", "with", "how", "why", "what", "when"}


def bibtex_key(a: Article) -> str:
    fam = _KEY_CLEAN.sub("", split_author(a.authors[0])[0].lower()) if a.authors else "anon"
    words = [w for w in _KEY_CLEAN.sub(" ", a.title.lower()).split() if w not in _STOP]
    first = words[0] if words else "paper"
    return f"{fam}{a.year or ''}{first}"


def _bib_escape(s: str) -> str:
    return s.replace("\\", "\\textbackslash{}").replace("&", "\\&").replace("%", "\\%").replace("#", "\\#").replace("_", "\\_")


def bibtex(a: Article) -> str:
    key = bibtex_key(a)
    authors = " and ".join(f"{split_author(n)[0]}, {split_author(n)[1]}".rstrip(", ") for n in a.authors)
    lines = []
    if a.is_journal:
        lines.append(f"@article{{{key},")
        lines.append(f"  journal = {{{_bib_escape(a.venue)}}},")
        for k, v in (("volume", a.volume), ("number", a.issue), ("pages", a.pages)):
            if v:
                lines.append(f"  {k} = {{{_bib_escape(v)}}},")
    else:
        lines.append(f"@techreport{{{key},")
        lines.append(f"  institution = {{{_bib_escape(a.venue)}}},")
        if a.nber_id:
            lines.append(f"  number = {{{a.nber_id}}},")
        lines.append("  type = {Working Paper},")
    lines.insert(1, f"  title = {{{_bib_escape(a.title)}}},")
    lines.insert(2, f"  author = {{{_bib_escape(authors)}}},")
    if a.year:
        lines.append(f"  year = {{{a.year}}},")
    if a.doi:
        lines.append(f"  doi = {{{a.doi}}},")
    url = a.primary_url or a.paper_url
    if url:
        lines.append(f"  url = {{{url}}},")
    lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


def plain_citation(a: Article) -> str:
    names = []
    for n in a.authors:
        fam, giv = split_author(n)
        initials = " ".join(f"{p[0]}." for p in giv.replace("-", " ").split() if p)
        names.append(f"{fam}, {initials}" if initials else fam)
    if len(names) > 1:
        auth = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        auth = names[0] if names else "Anon."
    year = f" ({a.year})" if a.year else ""
    venue = a.venue
    if a.is_journal and a.volume:
        venue += f", {a.volume}"
        if a.issue:
            venue += f"({a.issue})"
        if a.pages:
            venue += f", {a.pages}"
    tail = f" https://doi.org/{a.doi}" if a.doi else (f" {a.primary_url}" if a.primary_url else "")
    return f"{auth}{year}. {a.title}. {venue}.{tail}"
