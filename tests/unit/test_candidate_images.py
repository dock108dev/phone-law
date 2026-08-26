from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from scripts.prepare_candidate_images import (
    COMMIT_LABEL,
    RUNTIME_LABEL,
    TREE_LABEL,
    CandidateIdentity,
    CandidateImageError,
    declared_runtime_contract,
    validate_image_observation,
)

ROOT = Path(__file__).resolve().parents[2]


def test_every_repository_python_source_parses() -> None:
    roots = (ROOT / "apps", ROOT / "packages", ROOT / "scripts", ROOT / "tests")
    parsed = 0
    for source_root in roots:
        for path in sorted(source_root.rglob("*.py")):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path.relative_to(ROOT)))
            parsed += 1
    assert parsed >= 100


def test_all_seven_multi_exception_handlers_remain_parenthesized() -> None:
    expected = {
        "apps/api/colacci_api/main.py": "except (ValidationError, ValueError):",
        "apps/worker/colacci_worker/main.py": "except (ValidationError, ValueError):",
        "packages/review/pipeline.py": (
            "except (ValidationError, ReviewValidationError, ValueError):"
        ),
        "scripts/secret_scan.py": "except (OSError, UnicodeDecodeError):",
        "scripts/transcription_cli_preflight.py": ("except (OSError, subprocess.TimeoutExpired):"),
        "scripts/transcription_live_preflight.py": (
            "except (FileNotFoundError, KeyError, TypeError, ValueError, MediaBoundaryError):"
        ),
        "scripts/unsafe_production_probe.py": "except (ValidationError, ValueError):",
    }
    for relative, handler in expected.items():
        assert handler in (ROOT / relative).read_text(encoding="utf-8")


def _identity() -> CandidateIdentity:
    return CandidateIdentity(
        commit="a" * 40,
        tree="b" * 40,
        runtime_contract="sha256:" + "c" * 64,
    )


def _observation(identity: CandidateIdentity, contract: dict[str, str]) -> dict[str, Any]:
    labels = {
        COMMIT_LABEL: identity.commit,
        TREE_LABEL: identity.tree,
        RUNTIME_LABEL: identity.runtime_contract,
    }
    return {
        "api": {"image_id": "sha256:api", "labels": labels, "python": contract["python"]},
        "worker": {
            "image_id": "sha256:worker",
            "labels": labels,
            "python": contract["python"],
        },
        "web": {
            "image_id": "sha256:web",
            "labels": labels,
            "node": contract["node"],
            "npm": contract["npm"],
        },
        "e2e": {
            "image_id": "sha256:e2e",
            "labels": labels,
            "node": "24.18.1",
            "npm": contract["npm"],
            "playwright": contract["playwright"],
        },
    }


def test_runtime_declarations_agree_on_python_3147() -> None:
    contract = declared_runtime_contract(ROOT)
    assert contract["python"] == "3.14.7"
    assert contract["pip"] == "26.2.1"
    assert contract["node"] == "26.3.0"
    assert contract["npm"] == "12.0.2"
    assert contract["playwright"] == "1.62.1"


def test_exact_candidate_image_observation_is_accepted() -> None:
    contract = declared_runtime_contract(ROOT)
    identity = _identity()
    validate_image_observation(_observation(identity, contract), identity, contract)


@pytest.mark.parametrize(
    ("service", "field", "value", "failure"),
    [
        ("api", "labels", {}, "api:candidate_commit"),
        ("worker", "python", "3.13.5", "worker:python_runtime"),
        ("web", "node", "24.18.1", "web:node_runtime"),
        ("e2e", "playwright", "1.61.0", "e2e:playwright_runtime"),
    ],
)
def test_stale_or_runtime_mismatched_image_fails_closed(
    service: str, field: str, value: object, failure: str
) -> None:
    contract = declared_runtime_contract(ROOT)
    identity = _identity()
    observation = _observation(identity, contract)
    observation[service][field] = value
    with pytest.raises(CandidateImageError, match=failure):
        validate_image_observation(observation, identity, contract)
