"""Verify that runtime, direct dependencies, and lock artifacts are exact."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def verify(root: Path) -> None:
    failures: list[str] = []

    for line in (root / "requirements.in").read_text(encoding="utf-8").splitlines():
        requirement = line.strip()
        if requirement and not requirement.startswith("#") and "==" not in requirement:
            failures.append(f"unbounded Python requirement: {requirement.split('[')[0]}")

    lock_text = (root / "requirements.lock").read_text(encoding="utf-8")
    requirement_pattern = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;\\]+)", re.MULTILINE)
    locked = {
        name.lower().replace("_", "-"): version
        for name, version in requirement_pattern.findall(lock_text)
    }
    for name, version in requirement_pattern.findall((root / "requirements.in").read_text()):
        if locked.get(name.lower().replace("_", "-")) != version:
            failures.append(f"Python direct/lock mismatch: {name}")
    python_version = (root / ".python-version").read_text().strip()
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    python_image = (root / "infrastructure/local/python.Dockerfile").read_text()
    if (
        project["requires-python"] != f"=={python_version}"
        or f"FROM python:{python_version}-" not in python_image
    ):
        failures.append("Python runtime declarations disagree")
    web_image = (root / "infrastructure/local/web.Dockerfile").read_text()
    node_version = (root / ".nvmrc").read_text().strip()
    if f"FROM node:{node_version}-" not in web_image:
        failures.append("Node runtime declarations disagree")
    if "--hash=sha256:" not in lock_text:
        failures.append("Python lock does not include hashes")

    package = json.loads((root / "apps/web/package.json").read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        for name, version in package.get(section, {}).items():
            if not EXACT_VERSION.fullmatch(version):
                failures.append(f"unbounded JavaScript dependency: {name}")

    package_lock = json.loads((root / "apps/web/package-lock.json").read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        if package.get(section, {}) != package_lock.get("packages", {}).get("", {}).get(
            section, {}
        ):
            failures.append(f"JavaScript direct/lock mismatch: {section}")
    npm_version = package["packageManager"].removeprefix("npm@")
    browser_image = (root / "infrastructure/local/playwright.Dockerfile").read_text()
    if any(f"npm@{npm_version}" not in content for content in (web_image, browser_image)):
        failures.append("npm runtime declarations disagree")
    playwright_version = package["devDependencies"]["@playwright/test"]
    if f"FROM mcr.microsoft.com/playwright:v{playwright_version}-" not in browser_image:
        failures.append("Playwright package/image mismatch")
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


def main() -> None:
    verify(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
