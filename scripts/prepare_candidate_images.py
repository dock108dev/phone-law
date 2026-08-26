"""Build and fail-closed verify executable images for an exact clean candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess  # nosec B404 - fixed local Docker/Git commands only
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = Path("/tmp/colacci-law-candidate/evidence")  # nosec B108
COMMIT_LABEL = "io.colacci-law.candidate.commit"
TREE_LABEL = "io.colacci-law.candidate.tree"
RUNTIME_LABEL = "io.colacci-law.runtime.contract"


class CandidateImageError(RuntimeError):
    """Candidate images are absent, stale, or inconsistent with frozen source inputs."""


@dataclass(frozen=True)
class CandidateIdentity:
    commit: str
    tree: str
    runtime_contract: str


def _run(arguments: list[str], *, environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(  # noqa: S603  # nosec B603
        arguments,
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git(*arguments: str) -> str:
    return _run(["git", *arguments])  # nosec B607 - fixed executable


def _match(pattern: str, content: str, description: str) -> str:
    match = re.search(pattern, content, re.MULTILINE)
    if match is None:
        raise CandidateImageError(f"candidate runtime declaration missing: {description}")
    return match.group(1)


def declared_runtime_contract(root: Path = REPOSITORY_ROOT) -> dict[str, str]:
    project = cast(
        dict[str, Any],
        tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"],
    )
    python_requirement = str(project["requires-python"])
    python_version = python_requirement.removeprefix("==")
    version_file = (root / ".python-version").read_text(encoding="utf-8").strip()
    python_dockerfile = (root / "infrastructure/local/python.Dockerfile").read_text(
        encoding="utf-8"
    )
    docker_python = _match(r"^FROM python:([0-9.]+)-", python_dockerfile, "Python image")
    pip_version = _match(r"pip==([0-9.]+)", python_dockerfile, "pip image pin")
    if python_requirement != f"=={version_file}" or docker_python != version_file:
        raise CandidateImageError("Python runtime declarations do not agree exactly")

    package = cast(
        dict[str, Any],
        json.loads((root / "apps/web/package.json").read_text(encoding="utf-8")),
    )
    npm_version = str(package["packageManager"]).removeprefix("npm@")
    web_dockerfile = (root / "infrastructure/local/web.Dockerfile").read_text(encoding="utf-8")
    web_node = _match(r"^FROM node:([0-9.]+)-", web_dockerfile, "Node image")
    web_npm = _match(r"npm@([0-9.]+)", web_dockerfile, "web npm pin")
    playwright_dockerfile = (root / "infrastructure/local/playwright.Dockerfile").read_text(
        encoding="utf-8"
    )
    playwright_image = _match(
        r"^FROM mcr\.microsoft\.com/playwright:v([0-9.]+)-",
        playwright_dockerfile,
        "Playwright image",
    )
    playwright_package = str(cast(dict[str, str], package["devDependencies"])["@playwright/test"])
    playwright_npm = _match(r"npm@([0-9.]+)", playwright_dockerfile, "Playwright npm pin")
    if web_npm != npm_version or playwright_npm != npm_version:
        raise CandidateImageError("npm runtime declarations do not agree exactly")
    if playwright_image != playwright_package:
        raise CandidateImageError("Playwright runtime declarations do not agree exactly")

    return {
        "python": python_version,
        "pip": pip_version,
        "node": web_node,
        "npm": npm_version,
        "node_engine": str(cast(dict[str, str], package["engines"])["node"]),
        "playwright": playwright_package,
    }


def candidate_identity(contract: dict[str, str]) -> CandidateIdentity:
    if _git("status", "--porcelain=v1", "--untracked-files=all"):
        raise CandidateImageError("candidate image preparation requires a clean checkout")
    commit = _git("rev-parse", "HEAD")
    tree = _git("rev-parse", "HEAD^{tree}")
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    runtime_contract = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    return CandidateIdentity(commit=commit, tree=tree, runtime_contract=runtime_contract)


def _image_metadata(image: str) -> tuple[str, dict[str, str]]:
    raw = _run(["docker", "image", "inspect", image])  # nosec B607
    inspected = cast(list[dict[str, Any]], json.loads(raw))
    if len(inspected) != 1:
        raise CandidateImageError(f"candidate image inspection was ambiguous: {image}")
    item = inspected[0]
    labels = cast(dict[str, str] | None, cast(dict[str, Any], item["Config"]).get("Labels"))
    return str(item["Id"]), labels or {}


def _container_output(image: str, *command: str) -> str:
    return _run(  # nosec B607
        ["docker", "run", "--rm", "--network", "none", image, *command]
    )


def validate_image_observation(
    observation: dict[str, Any], identity: CandidateIdentity, contract: dict[str, str]
) -> None:
    failures: list[str] = []
    for service in ("api", "worker", "web", "e2e"):
        image = cast(dict[str, Any], observation.get(service, {}))
        labels = cast(dict[str, str], image.get("labels", {}))
        if labels.get(COMMIT_LABEL) != identity.commit:
            failures.append(f"{service}:candidate_commit")
        if labels.get(TREE_LABEL) != identity.tree:
            failures.append(f"{service}:candidate_tree")
        if labels.get(RUNTIME_LABEL) != identity.runtime_contract:
            failures.append(f"{service}:runtime_contract")
        if not str(image.get("image_id", "")).startswith("sha256:"):
            failures.append(f"{service}:image_identity")

    for service in ("api", "worker"):
        if cast(dict[str, Any], observation.get(service, {})).get("python") != contract["python"]:
            failures.append(f"{service}:python_runtime")
    web = cast(dict[str, Any], observation.get("web", {}))
    if web.get("node") != contract["node"]:
        failures.append("web:node_runtime")
    if web.get("npm") != contract["npm"]:
        failures.append("web:npm_runtime")
    e2e = cast(dict[str, Any], observation.get("e2e", {}))
    if e2e.get("npm") != contract["npm"]:
        failures.append("e2e:npm_runtime")
    if e2e.get("playwright") != contract["playwright"]:
        failures.append("e2e:playwright_runtime")
    node_match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", str(e2e.get("node", "")))
    if node_match is None or not 24 <= int(node_match.group(1)) < 27:
        failures.append("e2e:node_engine")
    if failures:
        raise CandidateImageError("candidate image verification failed: " + ",".join(failures))


def collect_image_observation() -> dict[str, Any]:
    images = {
        "api": "colacci-law-api:latest",
        "worker": "colacci-law-worker:latest",
        "web": "colacci-law-web:latest",
        "e2e": "colacci-law-e2e:latest",
    }
    observation: dict[str, Any] = {}
    for service, image in images.items():
        image_id, labels = _image_metadata(image)
        observation[service] = {"image_id": image_id, "labels": labels}
    for service in ("api", "worker"):
        observation[service]["python"] = _container_output(
            images[service], "python", "-c", "import platform; print(platform.python_version())"
        )
    observation["web"]["node"] = _container_output(images["web"], "node", "--version").removeprefix(
        "v"
    )
    observation["web"]["npm"] = _container_output(images["web"], "npm", "--version")
    observation["e2e"]["node"] = _container_output(images["e2e"], "node", "--version").removeprefix(
        "v"
    )
    observation["e2e"]["npm"] = _container_output(images["e2e"], "npm", "--version")
    observation["e2e"]["playwright"] = _container_output(
        images["e2e"], "./node_modules/.bin/playwright", "--version"
    ).removeprefix("Version ")
    return observation


def validate_evidence_root(candidate: Path) -> Path:
    root = candidate.resolve()
    temporary_root = Path("/tmp").resolve()  # nosec B108 - canonical private temp root
    try:
        relative = root.relative_to(temporary_root)
    except ValueError as error:
        raise CandidateImageError(
            "candidate evidence must use a bounded Colacci Law temp path"
        ) from error
    if not relative.parts or not relative.parts[0].startswith("colacci-law-"):
        raise CandidateImageError("candidate evidence must use a bounded Colacci Law temp path")
    return root


def _evidence_root() -> Path:
    candidate = Path(os.environ.get("COLACCI_CANDIDATE_EVIDENCE_DIR", DEFAULT_EVIDENCE_ROOT))
    return validate_evidence_root(candidate)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify existing candidate images without rebuilding them",
    )
    arguments = parser.parse_args()
    contract = declared_runtime_contract()
    identity = candidate_identity(contract)
    if not arguments.verify_only:
        environment = os.environ.copy()
        environment.update(
            {
                "COLACCI_CANDIDATE_COMMIT": identity.commit,
                "COLACCI_CANDIDATE_TREE": identity.tree,
                "COLACCI_RUNTIME_CONTRACT": identity.runtime_contract,
            }
        )
        _run(
            [
                "docker",
                "compose",
                "--profile",
                "e2e",
                "build",
                "api",
                "worker",
                "web",
                "e2e",
            ],
            environment=environment,
        )
    observation = collect_image_observation()
    validate_image_observation(observation, identity, contract)

    evidence_root = _evidence_root()
    evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence_root.parent.chmod(0o700)
    evidence_root.chmod(0o700)
    report = {
        "schema_version": "candidate-images-v1",
        "candidate_commit": identity.commit,
        "candidate_tree": identity.tree,
        "runtime_contract": identity.runtime_contract,
        "declared_runtimes": contract,
        "images": observation,
        "source_and_runtime_match": True,
    }
    target = evidence_root / "candidate-images.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target.chmod(0o600)
    print(
        f"candidate-images commit={identity.commit} tree={identity.tree} "
        f"python={contract['python']} source_and_runtime_match=true"
    )


if __name__ == "__main__":
    main()
