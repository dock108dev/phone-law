"""Strict Pydantic hydration for JSON-compatible database payloads."""

from __future__ import annotations

import json

from pydantic import BaseModel


def validated_model[ModelT: BaseModel](model: type[ModelT], payload: object) -> ModelT:
    """Revalidate persisted JSON without weakening strict model configuration."""

    return model.model_validate_json(json.dumps(payload, ensure_ascii=False))
