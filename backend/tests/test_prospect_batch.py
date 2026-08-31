"""Running the assessment across a whole book, territory by territory.

The ordering is the point. A whole-book run is ~1,300 shops; in store_name
order that leaves twelve territories half-assessed for the entire run, and a
batch stopped halfway helps nobody. One territory at a time finishes each book
complete and usable — which matters because a run WILL be stopped halfway.
"""
from app.prospects import batch


def test_territories_are_ordered_biggest_first_after_the_lead():
    """Lead territory first (whoever is being tested against), then most work."""
    counts = {"A": 10, "B": 300, "C": 50, "D": 120}
    assert batch.order_territories(counts, lead="C") == ["C", "B", "D", "A"]


def test_the_lead_is_optional():
    counts = {"A": 10, "B": 300, "C": 50}
    assert batch.order_territories(counts) == ["B", "C", "A"]


def test_a_lead_with_no_pending_work_is_dropped():
    """Naming a finished territory must not put an empty run at the front."""
    counts = {"B": 300, "C": 50}
    assert batch.order_territories(counts, lead="Z") == ["B", "C"]


def test_territories_with_nothing_pending_are_skipped_entirely():
    counts = {"A": 0, "B": 5}
    assert batch.order_territories(counts) == ["B"]


def test_run_visits_every_territory_and_sums_what_was_written(monkeypatch):
    seen, written = [], {"X": 3, "Y": 7}
    monkeypatch.setattr(batch, "pending_by_territory", lambda db: {"X": 3, "Y": 7})
    def _assess(db, territory=None, **kw):
        seen.append(territory)
        return written[territory]
    monkeypatch.setattr(batch.assess, "assess_pending", _assess)
    assert batch.run(object()) == 10
    assert seen == ["Y", "X"]          # biggest first


def test_one_failing_territory_does_not_abandon_the_rest(monkeypatch):
    """Each row already cost a scrape and a model call. A territory that raises
    must not throw away the books that would have run after it."""
    monkeypatch.setattr(batch, "pending_by_territory", lambda db: {"X": 9, "Y": 5})
    def _assess(db, territory=None, **kw):
        if territory == "X":
            raise RuntimeError("boom")
        return 5
    monkeypatch.setattr(batch.assess, "assess_pending", _assess)
    assert batch.run(object()) == 5
