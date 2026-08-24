from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from packages.database.model_hydration import validated_model


class StoredExample(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    count: int


def test_persisted_payloads_are_revalidated_without_coercion() -> None:
    assert validated_model(StoredExample, {"count": 3}) == StoredExample(count=3)

    with pytest.raises(ValidationError, match="int_type"):
        validated_model(StoredExample, {"count": "3"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        validated_model(StoredExample, {"count": 3, "unexpected": True})
