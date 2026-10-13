"""Source fetchers. REGISTRY maps a source kind to a fetch(source, window, ctx) callable."""
from __future__ import annotations

from . import arxiv, crossref, gsheet, osf, repec

REGISTRY = {
    "crossref_journal": crossref.fetch_journal,
    "crossref_prefix": crossref.fetch_prefix,
    "arxiv": arxiv.fetch,
    "repec_nep": repec.fetch,
    "gsheet": gsheet.fetch,
    "osf_preprints": osf.fetch,
}
