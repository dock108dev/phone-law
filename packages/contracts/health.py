"""Stable operational health response contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["up", "ready", "not_ready"]
    service: Literal["api", "worker"]
    profile: Literal["test", "demo", "local_dev", "live_test", "staging", "production"]
    version: str
    synthetic_data: bool
    database: Literal["not_checked", "ready", "not_ready"]
    migration: Literal["not_checked", "current", "not_current"]
