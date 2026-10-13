import yaml
from pathlib import Path

from digest.keywords import KeywordScorer, is_candidate
from digest.settings import Source

TOPICS = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "topics.yaml").read_text())
SC = KeywordScorer(TOPICS)


def test_ai_needs_core_term():
    r = SC.score("Worker productivity and job tasks in manufacturing", "labor, occupation, hiring.")
    assert r["scores"]["ai_work"] == 0
    r2 = SC.score("Large language models and worker productivity", "")
    assert r2["scores"]["ai_work"] > 0 and "large language model" in r2["reasons"]["ai_work"]


def test_title_hits_double():
    t = SC.score("Founder teams", "")
    a = SC.score("Nothing here", "founder teams")
    assert t["scores"]["entrepreneurship"] == 2 * a["scores"]["entrepreneurship"]


def test_negatives_subtract_and_word_boundaries():
    r = SC.score("Protein folding with AI", "neuron receptor")
    assert r["scores"]["ai_work"] == 0
    r2 = SC.score("Said and done", "maid")
    assert r2["scores"]["ai_work"] == 0  # 'ai' must be a whole word


def test_candidate_gate():
    r = SC.score("A paper about hiring", "")
    assert r["max"] == 4
    assert is_candidate(r, Source(slug="x", name="x", kind="crossref_journal", category="c", tier="B", min_score=2))
    assert not is_candidate(r, Source(slug="x", name="x", kind="crossref_journal", category="c", tier="C", min_score=5))
    assert is_candidate({"max": 0}, Source(slug="x", name="x", kind="crossref_journal", category="c", tier="A", always_candidate=True))


def test_ai_requires_work_context():
    pure_nlp = SC.score("Efficient Large-Vocabulary Loss Kernels for Large Language Models", "We train LLMs faster.")
    assert pure_nlp["scores"]["ai_work"] == 0
    with_work = SC.score("Large Language Models and Worker Productivity", "")
    assert with_work["scores"]["ai_work"] > 0
