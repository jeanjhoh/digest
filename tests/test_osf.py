from types import SimpleNamespace as NS

from digest.sources import REGISTRY
from digest.sources.osf import fetch

PAGE = {
    "data": [
        {"attributes": {"title": "Class Origins and Founder Outcomes", "description": "<p>We study founders.</p>",
                        "is_published": True, "reviews_state": "accepted", "date_published": "2026-10-10T09:00:00",
                        "date_created": "2026-10-10T08:00:00", "is_latest_version": True, "date_withdrawn": None},
         "links": {"preprint_doi": "https://doi.org/10.31235/osf.io/abc12_v1", "html": "https://osf.io/preprints/socarxiv/abc12_v1"},
         "embeds": {"contributors": {"data": [
             {"attributes": {"bibliographic": True}, "embeds": {"users": {"data": {"attributes": {"full_name": "Ada Lovelace", "given_name": "Ada", "family_name": "Lovelace"}}}}},
             {"attributes": {"bibliographic": False}, "embeds": {"users": {"data": {"attributes": {"full_name": "Not Author"}}}}},
         ]}}},
        {"attributes": {"title": "Pending moderation", "is_published": True, "reviews_state": "pending", "date_created": "2026-10-10T08:00:00"},
         "links": {}, "embeds": {}},
    ],
    "links": {"next": None},
}


class FakeHttp:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return NS(json=lambda: PAGE)


def test_osf_fetch_parses_accepted_preprints():
    http = FakeHttp()
    src = NS(slug="socarxiv", name="SocArXiv", provider="socarxiv")
    recs = fetch(src, NS(start_date="2026-10-01"), NS(http=http))
    assert len(recs) == 1
    r = recs[0]
    assert r.doi == "10.31235/osf.io/abc12_v1" and r.venue == "SocArXiv" and r.publication_status == "preprint"
    assert r.authors == ["Ada Lovelace"] and r.author_parts[0]["family"] == "Lovelace"
    assert r.abstract == "We study founders." and r.abstract_source == "osf"
    assert http.calls[0][1]["filter[provider]"] == "socarxiv" and http.calls[0][1]["filter[date_created][gte]"] == "2026-10-01"


def test_registry_has_osf():
    assert REGISTRY["osf_preprints"] is fetch
