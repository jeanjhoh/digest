from datetime import datetime, timezone

from digest.issues import Issues
from digest.models import Article
from digest.store import Store


def _art(key, in_scope=True, rec=False, sets=("ai_work",)):
    a = Article(key=key, title=key, normalized_title=key, source_slug="asq", source_category="management_journal", venue="ASQ",
                first_seen_at="2026-10-01T00:00:00Z", last_seen_at="2026-10-01T00:00:00Z", in_scope=in_scope, recommended=rec,
                classification={"sets": list(sets), "relevance": 8})
    return a


def test_week_keys_numbering_and_idempotency(tmp_path):
    iss = Issues.load(tmp_path)
    t1 = datetime(2026, 10, 7, 10, tzinfo=timezone.utc)
    i1, created = iss.get_or_create(t1, 14)
    assert created and i1.number == 1 and i1.key == "2026-W41" and i1.window_start.startswith("2026-09-23")
    i1b, created_b = iss.get_or_create(t1.replace(day=9), 8)
    assert not created_b and i1b is i1
    i2, created2 = iss.get_or_create(datetime(2026, 10, 14, 10, tzinfo=timezone.utc), 8)
    assert created2 and i2.number == 2 and i2.window_start == i1.cutoff_at
    iss.save()
    assert Issues.load(tmp_path).latest.number == 2


def test_assign_and_finalize(tmp_path):
    store = Store(tmp_path)
    for a in [_art("a", rec=True), _art("b", sets=("ai_work", "entrepreneurship")), _art("c", in_scope=False)]:
        store._index(a)
    iss = Issues.load(tmp_path)
    issue, _ = iss.get_or_create(datetime(2026, 10, 7, tzinfo=timezone.utc), 8)
    assert Issues.assign(store, issue) == 2
    assert Issues.assign(store, issue) == 0
    Issues.finalize(issue, store, ["entrepreneurship", "ai_work", "orgs_inequality"])
    assert issue.counts["in_scope"] == 2 and issue.counts["recommended"] == 1
    assert issue.counts["by_set"] == {"entrepreneurship": 1, "ai_work": 2, "orgs_inequality": 0}
