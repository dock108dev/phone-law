from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from scripts import verify_transcript_import as verification


def test_harness_rejects_retained_database_before_connecting(monkeypatch):
    engine = create_engine("sqlite:///retained_demo")

    def unexpected(_):
        pytest.fail("retained database was accessed")

    monkeypatch.setattr(verification, "_database_counts", unexpected)
    with pytest.raises(ValueError, match="disposable _test"):
        verification.require_empty_test_database(engine)
    engine.dispose()


@pytest.mark.parametrize("count", [0, 1])
def test_harness_requires_empty_review_tables(monkeypatch, count):
    engine = create_engine("sqlite:///disposable_test")
    monkeypatch.setattr(verification, "_database_counts", lambda _: {"calls": count})
    if count:
        with pytest.raises(ValueError, match="empty review tables"):
            verification.require_empty_test_database(engine)
    else:
        verification.require_empty_test_database(engine)
    engine.dispose()
