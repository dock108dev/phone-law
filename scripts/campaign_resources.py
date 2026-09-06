"""Claim fresh disposable harness resources; never adopt an existing dataset."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess  # nosec B404 -- fixed Docker inventory commands
from pathlib import Path

MARKER = ".campaign-owner.json"


def bounded_path(value: str) -> Path:
    path = Path(value)
    temporary = Path("/tmp").resolve()  # noqa: S108  # nosec B108 -- canonical temporary boundary
    resolved = path.resolve()
    relative = resolved.relative_to(temporary)
    if not relative.parts or not relative.parts[0].startswith("colacci-law-"):
        raise ValueError("campaign paths must be bounded Colacci Law temporary paths")
    if relative.parts[0] == "colacci-law-slice4-local":
        raise ValueError("retained owner runtime is forbidden")
    # /tmp itself is a system symlink on macOS; descendants must not be aliases.
    for parent in (path, *path.parents):
        if parent == Path("/tmp"):  # noqa: S108  # nosec B108
            break
        if parent.is_symlink():
            raise ValueError("campaign path contains a symlink")
    return resolved


def require_unused_project(project: str) -> None:
    if not re.fullmatch(r"colacci-law-[a-z0-9-]+", project):
        raise ValueError("a separately named disposable project is required")
    for resource, operation in (("container", "ls"), ("volume", "ls"), ("network", "ls")):
        command = ["docker", resource, operation, "-q"]
        if resource == "container":
            command.append("-a")
        command += ["--filter", f"label=com.docker.compose.project={project}"]
        result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed read-only Docker inventory
            command, check=True, capture_output=True, text=True
        )
        if result.stdout.strip():
            raise ValueError(f"existing {resource} resources for {project}; preserve and inspect")


def claim(project: str, runtime: str, evidence: str, token: str) -> None:
    root, output = bounded_path(runtime), bounded_path(evidence)
    if root == output or root in output.parents or output in root.parents:
        raise ValueError("runtime and retained evidence must be separate")
    if root.exists() or output.exists():
        raise ValueError("runtime/evidence already exists; choose fresh attempt paths")
    require_unused_project(project)
    root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    (root / MARKER).write_text(json.dumps({"project": project, "token": token}))
    (root / MARKER).chmod(0o600)
    output.mkdir(mode=0o700)


def owned(project: str, runtime: str, token: str) -> Path:
    root = bounded_path(runtime)
    marker = root / MARKER
    if marker.is_symlink() or json.loads(marker.read_text()) != {
        "project": project,
        "token": token,
    }:
        raise ValueError("runtime ownership does not match this attempt")
    return root


def secure_evidence(evidence: str) -> None:
    root = bounded_path(evidence)
    paths = [root, *root.rglob("*")]
    if any(path.is_symlink() for path in paths):
        raise ValueError("evidence contains a symlink; preserve and inspect")
    for path in paths:
        path.chmod(0o700 if path.is_dir() else 0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("claim", "check", "remove", "secure", "verify-clean"))
    parser.add_argument("project")
    parser.add_argument("runtime")
    parser.add_argument("evidence")
    args = parser.parse_args()
    token = os.environ["COLACCI_CAMPAIGN_TOKEN"]
    os.umask(0o077)
    if args.action == "claim":
        claim(args.project, args.runtime, args.evidence, token)
    else:
        root = owned(args.project, args.runtime, token)
        if args.action == "verify-clean":
            require_unused_project(args.project)
        elif args.action == "secure":
            secure_evidence(args.evidence)
        elif args.action == "remove":
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
