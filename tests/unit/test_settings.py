from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.config import AppProfile, Settings


def safe_deployment_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_profile": AppProfile.PRODUCTION,
        "allow_real_call_data": False,
        "real_call_processing_authorized": False,
        "auth_mode": "sso",
        "app_secret": "a-production-grade-value-with-40-characters",
        "database_url": (
            "postgresql+psycopg://colacci_app:strong-database-password-839274@"
            "database.internal/colacci"
        ),
        "object_storage_backend": "private_cloud",
        "object_storage_bucket": "firm-private-objects",
        "call_source_adapter": "disabled",
        "transcriber_adapter": "disabled",
        "analyzer_adapter": "disabled",
        "audio_retention_days": 7,
        "transcript_retention_days": 30,
        "analysis_retention_days": 30,
        "audit_retention_days": 90,
        "retention_policy_approved": True,
        "debug": False,
        "cors_origins": ["https://review.firm.invalid"],
    }
    values.update(overrides)
    return Settings(**values)


def test_demo_is_the_safe_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_profile is AppProfile.DEMO
    assert settings.synthetic_mode is True
    assert settings.allow_real_call_data is False
    assert settings.call_source_adapter == "fixture"


def test_demo_rejects_real_call_data() -> None:
    with pytest.raises(ValidationError, match="allow_real_call_data"):
        Settings(_env_file=None, allow_real_call_data=True)


def test_staging_rejects_demo_defaults() -> None:
    with pytest.raises(ValidationError, match="auth_mode") as error:
        Settings(_env_file=None, app_profile=AppProfile.STAGING)
    message = str(error.value)
    assert "object_storage_backend" in message
    assert "call_source_adapter" in message
    assert "retention_settings" in message
    assert "cors_origins" in message


@pytest.mark.parametrize(
    ("override", "unsafe_value", "expected_field"),
    [
        ("auth_mode", "fake", "auth_mode"),
        ("app_secret", "change-me", "app_secret"),
        ("object_storage_backend", "local_synthetic", "object_storage_backend"),
        ("object_storage_bucket", "example-bucket", "object_storage_bucket"),
        ("call_source_adapter", "fixture", "call_source_adapter"),
        ("transcriber_adapter", "fixture", "transcriber_adapter"),
        ("analyzer_adapter", "fixture", "analyzer_adapter"),
        ("audio_retention_days", 0, "retention_settings"),
        ("retention_policy_approved", False, "retention_settings"),
        ("debug", True, "debug"),
        ("cors_origins", ["*"], "cors_origins"),
        ("cors_origins", ["http://localhost:15173"], "cors_origins"),
        (
            "database_url",
            "postgresql+psycopg://colacci_app:strong-password-123456@db/colacci",
            "database_url",
        ),
    ],
)
def test_production_rejects_each_unsafe_default(
    override: str,
    unsafe_value: object,
    expected_field: str,
) -> None:
    with pytest.raises(ValidationError, match=expected_field):
        safe_deployment_settings(**{override: unsafe_value})


def test_real_processing_requires_explicit_authorization() -> None:
    with pytest.raises(ValidationError, match="real_call_processing_authorized"):
        safe_deployment_settings(
            allow_real_call_data=True,
            real_call_processing_authorized=False,
            real_data_approval_reference="approved-2026-001",
        )


def test_real_processing_requires_non_placeholder_approval_reference() -> None:
    with pytest.raises(ValidationError, match="real_data_approval_reference"):
        safe_deployment_settings(
            allow_real_call_data=True,
            real_call_processing_authorized=True,
            real_data_approval_reference="example",
        )


def test_safe_production_shape_validates_while_processing_stays_disabled() -> None:
    settings = safe_deployment_settings()
    assert settings.app_profile is AppProfile.PRODUCTION
    assert settings.allow_real_call_data is False
    assert settings.call_source_adapter == "disabled"


def test_safe_authorized_shape_can_be_explicitly_represented() -> None:
    settings = safe_deployment_settings(
        allow_real_call_data=True,
        real_call_processing_authorized=True,
        real_data_approval_reference="approval-2026-001",
        call_source_adapter="manual_upload",
    )
    assert settings.allow_real_call_data is True
