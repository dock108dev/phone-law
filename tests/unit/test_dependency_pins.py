from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.verify_dependency_pins import verify

ROOT = Path(__file__).resolve().parents[2]
FILES = (
    "requirements.in",
    "requirements.lock",
    "pyproject.toml",
    ".python-version",
    ".nvmrc",
    "docker-compose.yml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "infrastructure/local/python.Dockerfile",
    "infrastructure/local/web.Dockerfile",
    "infrastructure/local/playwright.Dockerfile",
)


@pytest.fixture
def declarations(tmp_path: Path) -> Path:
    for name in FILES:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    return tmp_path


def test_current_declarations_agree(declarations: Path) -> None:
    verify(declarations)


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("requirements.lock", "Python direct/lock mismatch"),
        (".nvmrc", "Node runtime declarations disagree"),
        (".python-version", "Python runtime declarations disagree"),
        ("infrastructure/local/web.Dockerfile", "npm runtime"),
        ("apps/web/package-lock.json", "JavaScript direct/lock"),
        ("infrastructure/local/playwright.Dockerfile", "Playwright package/image"),
    ],
)
def test_drift_fails_before_installation(declarations, name, message):
    import json
    import re

    path = declarations / name
    source = path.read_text()
    if name == "requirements.lock":
        changed = re.sub(r"(?m)^fastapi==[^\s]+", "fastapi==0.0.0", source)
    elif name in {".nvmrc", ".python-version"}:
        changed = "0.0.0\n"
    elif name.endswith("package-lock.json"):
        package = json.loads(source)
        package["packages"][""]["dependencies"]["react"] = "0.0.0"
        changed = json.dumps(package)
    elif name.endswith("playwright.Dockerfile"):
        changed = re.sub(r"playwright:v[0-9.]+-", "playwright:v0.0.0-", source)
    else:
        changed = re.sub(r"npm@[0-9.]+", "npm@0.0.0", source)
    assert changed != source
    path.write_text(changed)
    with pytest.raises(SystemExit, match=message):
        verify(declarations)
