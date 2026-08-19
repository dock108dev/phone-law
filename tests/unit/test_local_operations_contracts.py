from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from packages.contracts.operations import (
    DEFAULT_LOCAL_FIRM_CONFIGURATION,
    LocalFirmConfiguration,
)


def _validate(value: object) -> LocalFirmConfiguration:
    return LocalFirmConfiguration.model_validate_json(json.dumps(value))


def test_local_configuration_is_strict_versioned_and_synthetic_only() -> None:
    payload = DEFAULT_LOCAL_FIRM_CONFIGURATION.model_dump(mode="json")
    assert _validate(payload) == DEFAULT_LOCAL_FIRM_CONFIGURATION

    with pytest.raises(ValidationError, match="extra_forbidden"):
        _validate({**payload, "provider_project_id": "forbidden"})
    with pytest.raises(ValidationError, match="firm_timezone"):
        _validate({**payload, "firm_timezone": "UTC"})
    with pytest.raises(ValidationError, match="notification_preference"):
        _validate({**payload, "notification_preference": "external_email"})
    with pytest.raises(ValidationError, match="synthetic_playbook_version"):
        _validate({**payload, "synthetic_playbook_version": "firm-approved-production"})


def test_local_configuration_requires_complete_unique_demo_values() -> None:
    payload = DEFAULT_LOCAL_FIRM_CONFIGURATION.model_dump(mode="json")
    with pytest.raises(ValidationError, match="all demo roles"):
        _validate({**payload, "report_roles": ["administrator"]})
    with pytest.raises(ValidationError, match="nonempty and unique"):
        _validate({**payload, "eligible_call_directions": ["inbound", "inbound"]})
    retention = {**payload["retention"], "generated_media_days": 0}
    with pytest.raises(ValidationError, match="generated_media_days"):
        _validate({**payload, "retention": retention})
