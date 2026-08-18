from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

from apps.api.colacci_api import create_app
from packages.config import Settings
from packages.contracts.report import (
    DemoPrincipal,
    DemoPrincipalId,
    DemoRole,
    ReviewEventCreate,
    ReviewLabel,
)
from packages.contracts.review import PlaybookVersion
from packages.database.repository import ReviewRepository
from packages.database.review_experience import ReviewExperienceRepository
from packages.database.review_schema import (
    analyses,
    audit_events,
    daily_report_items,
    daily_reports,
    playbook_versions,
    review_events,
)
from packages.review.fixtures import FixtureCallSource
from packages.review.pipeline import FixturePipeline

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded_experience() -> tuple[sa.Engine, ReviewExperienceRepository, dict[str, str]]:
    settings = Settings(_env_file=None, app_profile="test")
    parsed = urlsplit(settings.sqlalchemy_database_url.replace("postgresql+psycopg", "postgresql"))
    assert parsed.path.endswith("_test")
    alembic = Config("alembic.ini")
    alembic.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.downgrade(alembic, "base")
    command.upgrade(alembic, "head")
    engine = create_engine(settings.sqlalchemy_database_url)
    source = FixtureCallSource()
    repository = ReviewRepository(engine)
    playbook = PlaybookVersion.model_validate_json(
        Path("fixtures/playbooks/synthetic-draft-v1.json").read_text(encoding="utf-8")
    )
    repository.install_playbook(playbook.model_dump(mode="json"))
    pipeline = FixturePipeline(repository, source=source)
    call_ids: dict[str, str] = {}
    for event in source.events():
        outcome = pipeline.process(event)
        call_ids[event.fixture_id] = outcome.call_id
    pipeline.process(source.events("CL-FX-002")[0])
    experience = ReviewExperienceRepository(engine)
    expected = tuple(sorted({event.call.source_call_id for event in source.events()}))
    experience.generate_report(
        business_date=date(2026, 8, 17),
        cutoff_at=datetime(2026, 8, 17, 18, tzinfo=ZoneInfo("America/New_York")),
        expected_source_call_ids=expected,
    )
    try:
        yield engine, experience, call_ids
    finally:
        engine.dispose()


def test_report_review_failure_and_playbook_persistence(
    seeded_experience: tuple[sa.Engine, ReviewExperienceRepository, dict[str, str]],
) -> None:
    engine, experience, call_ids = seeded_experience
    report = experience.report(date(2026, 8, 17))
    assert report is not None
    assert report.completeness.status.value == "partial"
    assert report.completeness.reconciliation.model_dump() == {
        "expected": 11,
        "received": 11,
        "duplicate_deliveries": 2,
        "analyzed": 10,
        "failed": 1,
        "missing": 0,
        "late": 0,
    }
    regenerated = experience.generate_report(
        business_date=date(2026, 8, 17),
        cutoff_at=datetime(2026, 8, 17, 18, tzinfo=ZoneInfo("America/New_York")),
        expected_source_call_ids=tuple(
            sorted({event.call.source_call_id for event in FixtureCallSource().events()})
        ),
    )
    assert regenerated.report_id == report.report_id
    with engine.connect() as connection:
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(daily_reports)).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(daily_report_items)
            ).scalar_one()
            == 19
        )

    detail = experience.call_detail(call_ids["CL-FX-002"])
    assert detail is not None
    with engine.connect() as connection:
        original = json.dumps(
            connection.execute(
                sa.select(analyses.c.original_payload).where(analyses.c.id == detail.analysis_id)
            ).scalar_one(),
            sort_keys=True,
        )
    principal = DemoPrincipal(
        principal_id=DemoPrincipalId.REVIEWER,
        role=DemoRole.REVIEWER,
        synthetic=True,
    )
    experience.add_review(
        analysis_id=detail.analysis_id,
        request=ReviewEventCreate(
            label=ReviewLabel.CORRECT,
            finding_id="fx002-finding-commitment",
            note=None,
        ),
        principal=principal,
    )
    experience.add_review(
        analysis_id=detail.analysis_id,
        request=ReviewEventCreate(
            label=ReviewLabel.MISSING,
            finding_id=None,
            note="Synthetic reviewer says a finding is missing.",
        ),
        principal=principal,
    )
    assert [event.label.value for event in experience.review_history(detail.analysis_id)] == [
        "correct",
        "missing",
    ]
    with engine.connect() as connection:
        unchanged = json.dumps(
            connection.execute(
                sa.select(analyses.c.original_payload).where(analyses.c.id == detail.analysis_id)
            ).scalar_one(),
            sort_keys=True,
        )
        assert unchanged == original
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(review_events)).scalar_one()
            == 2
        )
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(audit_events)).scalar_one()
            == 2
        )
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
        connection.execute(review_events.update().values(note="forbidden"))
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
        connection.execute(audit_events.update().values(result="forbidden"))
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
        connection.execute(daily_reports.update().values(status="complete"))

    queue = experience.failure_queue()
    assert [(item.synthetic_reference, item.retryable) for item in queue.current] == [
        ("CL-FX-011", False)
    ]
    assert [item.synthetic_reference for item in queue.resolved] == ["CL-FX-010"]
    provenance_before = detail.provenance.playbook_version
    published = experience.publish_playbook(
        version="synthetic-draft-v1",
        principal=principal.model_copy(
            update={"principal_id": DemoPrincipalId.ADMIN, "role": DemoRole.ADMINISTRATOR}
        ),
    )
    assert published.playbook.lifecycle.value == "published"
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
        connection.execute(
            playbook_versions.update()
            .where(playbook_versions.c.version == "synthetic-draft-v1")
            .values(structured_payload={"forbidden": True})
        )
    assert (
        experience.call_detail(call_ids["CL-FX-002"]).provenance.playbook_version
        == provenance_before
    )  # type: ignore[union-attr]


def test_demo_api_role_matrix_and_safe_errors(
    seeded_experience: tuple[sa.Engine, ReviewExperienceRepository, dict[str, str]],
) -> None:
    _, experience, call_ids = seeded_experience
    detail = experience.call_detail(call_ids["CL-FX-002"])
    assert detail is not None
    settings = Settings(_env_file=None, app_profile="test")
    app = create_app(settings)
    with TestClient(app) as client:
        report = client.get(
            "/api/reports/2026-08-17", headers={"X-Demo-Principal": "demo-reviewer"}
        )
        assert report.status_code == 200
        assert report.headers["Cache-Control"] == "no-store"
        assert "normalized_payload" not in report.text
        assert (
            client.get("/api/failures", headers={"X-Demo-Principal": "demo-reviewer"}).status_code
            == 403
        )
        assert (
            client.get("/api/failures", headers={"X-Demo-Principal": "demo-operations"}).status_code
            == 200
        )
        operation_feedback = client.post(
            f"/api/analyses/{detail.analysis_id}/reviews",
            headers={"X-Demo-Principal": "demo-operations"},
            json={"label": "correct", "finding_id": "fx002-finding-commitment", "note": None},
        )
        assert operation_feedback.status_code == 403
        reviewer_feedback = client.post(
            f"/api/analyses/{detail.analysis_id}/reviews",
            headers={"X-Demo-Principal": "demo-reviewer"},
            json={"label": "correct", "finding_id": "fx002-finding-commitment", "note": None},
        )
        assert reviewer_feedback.status_code == 201
        denied_publish = client.post(
            "/api/playbooks/synthetic-draft-v1/publish",
            headers={"X-Demo-Principal": "demo-reviewer"},
        )
        assert denied_publish.status_code == 403
        assert "correlation_id" in denied_publish.json()["detail"]
        unknown = client.get("/api/reports/dates", headers={"X-Demo-Principal": "arbitrary"})
        assert unknown.status_code == 401
