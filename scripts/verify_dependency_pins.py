"""Verify that runtime, direct dependencies, and lock artifacts are exact."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []

    for line in (root / "requirements.in").read_text(encoding="utf-8").splitlines():
        requirement = line.strip()
        if requirement and not requirement.startswith("#") and "==" not in requirement:
            failures.append(f"unbounded Python requirement: {requirement.split('[')[0]}")

    lock_text = (root / "requirements.lock").read_text(encoding="utf-8")
    if "--hash=sha256:" not in lock_text:
        failures.append("Python lock does not include hashes")

    package = json.loads((root / "apps/web/package.json").read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        for name, version in package.get(section, {}).items():
            if not EXACT_VERSION.fullmatch(version):
                failures.append(f"unbounded JavaScript dependency: {name}")

    package_lock = json.loads((root / "apps/web/package-lock.json").read_text(encoding="utf-8"))
    if package_lock.get("lockfileVersion") != 3:
        failures.append("JavaScript lockfile version is not 3")

    dockerfiles = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "infrastructure/local").glob("*.Dockerfile"))
    )
    for forbidden in ("FROM python:latest", "FROM node:latest", "FROM postgres:latest"):
        if forbidden in dockerfiles:
            failures.append(f"floating container runtime: {forbidden}")

    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    if not re.search(r"image: postgres:\d+\.\d+-alpine\d+\.\d+", compose):
        failures.append("PostgreSQL image is not pinned to patch and Alpine release")

    if failures:
        raise SystemExit("dependency pin verification failed: " + "; ".join(failures))
    print("dependency-pin pass: Python, JavaScript, and container runtimes are exact")


if __name__ == "__main__":
    main()
