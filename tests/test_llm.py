import json
from types import SimpleNamespace

import pytest

from digest.llm import BatchFailed, Classifier, apply_verdict, build_system_prompt, estimate_cost, render_batch
from digest.models import Article
from digest.settings import load_settings


def _article(key, title, abstract="abs"):
    return Article(key=key, title=title, normalized_title=title.lower(), source_slug="asq", source_category="management_journal",
                   venue="ASQ", first_seen_at="2026-10-01T00:00:00Z", last_seen_at="2026-10-01T00:00:00Z", abstract=abstract,
                   keyword={"candidate": True, "max": 3, "reasons": {"entrepreneurship": ["founder"]}})


class FakeClient:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responder(kwargs)


def _resp(text, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=500))


@pytest.fixture
def settings():
    return load_settings()


def test_structured_call_and_apply(settings):
    arts = [_article("doi:10.1/a", "Founders and Class"), _article("doi:10.1/b", "Protein Folding", abstract=None)]

    def responder(kwargs):
        assert kwargs["output_config"]["format"]["type"] == "json_schema"
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        ids = [l.split("id: ")[1] for l in kwargs["messages"][0]["content"].splitlines() if l.startswith("id: ")]
        return _resp(json.dumps({"verdicts": [
            {"id": ids[0], "sets": ["entrepreneurship", "orgs_inequality"], "relevance": 9, "note": "Founder class origins and venture funding.", "flags": []},
            {"id": ids[1], "sets": [], "relevance": 9, "note": "", "flags": []}]}))

    clf = Classifier(settings, client=FakeClient(responder))
    v = clf.classify_all(arts)
    assert set(v) == {"doi:10.1/a", "doi:10.1/b"}
    apply_verdict(arts[0], v["doi:10.1/a"], clf.model, 4, 8)
    apply_verdict(arts[1], v["doi:10.1/b"], clf.model, 4, 8)
    assert arts[0].in_scope and arts[0].recommended and arts[0].classification["sets"] == ["entrepreneurship", "orgs_inequality"]
    assert not arts[1].in_scope and "title_only" in arts[1].classification["flags"] and arts[1].classification["relevance"] == 6
    st = clf.stats()
    assert st["calls"] == 1 and st["cache_read_input_tokens"] == 500 and st["est_cost_usd"] > 0


def test_refusal_and_max_tokens_split(settings):
    arts = [_article(f"doi:10.1/{i}", f"Paper {i}") for i in range(4)]
    seen = []

    def responder(kwargs):
        n = kwargs["messages"][0]["content"].count("\nid: ")
        seen.append(n)
        if n > 1:
            return _resp("", stop="max_tokens")
        vid = kwargs["messages"][0]["content"].split("id: ")[1].split("\n")[0]
        return _resp(json.dumps({"verdicts": [{"id": vid, "sets": ["ai_work"], "relevance": 5, "note": "x", "flags": []}]}))

    clf = Classifier(settings, client=FakeClient(responder))
    v = clf.classify_all(arts)
    assert len(v) == 4 and seen[0] == 4 and clf.errors == 0


def test_fallback_when_sdk_rejects_output_config(settings):
    def responder(kwargs):
        if "output_config" in kwargs:
            raise TypeError("unexpected keyword argument 'output_config'")
        return _resp("Here you go:\n" + json.dumps({"verdicts": [{"id": "doi:10.1/a", "sets": [], "relevance": 1, "note": "", "flags": ["not_research"]}]}))

    clf = Classifier(settings, client=FakeClient(responder))
    v = clf.classify_all([_article("doi:10.1/a", "Editorial")])
    assert not clf.structured and v["doi:10.1/a"]["flags"] == ["not_research"]
    a = _article("doi:10.1/a", "Editorial")
    apply_verdict(a, v["doi:10.1/a"], "m", 4, 8)
    assert a.hidden and not a.in_scope


def test_prompt_has_public_safe_note_rules(settings):
    sp = build_system_prompt(settings.profile, settings.sets)
    assert "NEVER mention the reader" in sp and "20 words" in sp
    assert "entrepreneurship" in sp and "ai_work" in sp and "orgs_inequality" in sp
    txt = render_batch([_article("doi:10.1/a", "T", abstract=" ".join(["w"] * 400))], max_abstract_words=10)
    assert txt.count("w ") <= 11 and "id: doi:10.1/a" in txt


def test_no_key_means_unavailable(settings, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert not Classifier(settings).available


def test_cost_estimate():
    assert abs(estimate_cost("claude-sonnet-5-5", {"input_tokens": 1_000_000, "output_tokens": 0}) - 2.0) < 1e-9
    assert abs(estimate_cost("claude-haiku-5-5", {"output_tokens": 1_000_000}) - 0.5) < 1e-9
