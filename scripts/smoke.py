"""Content-free smoke checks for local API, worker, web, database, and migration health."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

import httpx

from packages.config import Settings
from packages.database.health import create_database_engine, database_readiness


@dataclass(frozen=True)
class SmokeResult:
    component: str
    status: str
    detail: str


def read_json(url: str) -> dict[str, object]:
    response = httpx.get(url, timeout=5)
    response.raise_for_status()
    return cast(dict[str, object], response.json())


def main() -> None:
    settings = Settings(service_name="smoke")
    checks: list[SmokeResult] = []

    for service, endpoint in (
        ("api", "http://api:8000/health/ready"),
        ("worker", "http://worker:8001/health/ready"),
    ):
        payload = read_json(endpoint)
        if payload.get("status") != "ready" or payload.get("migration") != "current":
            raise SystemExit(f"{service} readiness failed")
        checks.append(SmokeResult(service, "pass", "service, database, and migration ready"))

    web_health = read_json("http://web:5173/healthz.json")
    if web_health.get("status") != "up" or web_health.get("synthetic_data") is not True:
        raise SystemExit("web readiness failed")
    checks.append(SmokeResult("web", "pass", "synthetic health endpoint up"))

    dashboard = httpx.get("http://web:5173/", timeout=5)
    if dashboard.status_code != 200:
        raise SystemExit("dashboard failed")
    checks.append(SmokeResult("dashboard", "pass", "web shell served"))

    engine = create_database_engine(settings.sqlalchemy_database_url)
    try:
        database = database_readiness(engine)
    finally:
        engine.dispose()
    if not database.ready:
        raise SystemExit("database readiness failed")
    checks.append(SmokeResult("database", "pass", "connected and migration current"))

    print(json.dumps([asdict(item) for item in checks], indent=2))


if __name__ == "__main__":
    main()
