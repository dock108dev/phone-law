from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import campaign_resources as resources
from scripts import prepare_candidate_images as images


@pytest.fixture
def campaign_root():
    with tempfile.TemporaryDirectory(prefix="colacci-law-ownership-", dir="/tmp") as directory:
        yield Path(directory)


@pytest.mark.parametrize("resource", ["container", "volume", "network"])
def test_existing_docker_resources_prevent_claim(campaign_root, resource):
    def inventory(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, "existing\n" if command[1] == resource else ""
        )

    with (
        patch.object(resources.subprocess, "run", side_effect=inventory),
        pytest.raises(ValueError, match="existing"),
    ):
        resources.claim(
            "colacci-law-proof",
            str(campaign_root / "runtime"),
            str(campaign_root / "evidence"),
            "token",
        )
    assert list(campaign_root.iterdir()) == []


def test_claim_and_cleanup_preserve_other_data_and_evidence(campaign_root):
    runtime, evidence = campaign_root / "runtime", campaign_root / "evidence"
    retained = campaign_root / "owner.txt"
    retained.write_text("preserve")
    with patch.object(resources, "require_unused_project"):
        resources.claim("colacci-law-proof", str(runtime), str(evidence), "token")
    (evidence / "proof.json").write_text("{}")
    with pytest.raises(ValueError, match="ownership"):
        resources.owned("colacci-law-proof", str(runtime), "other-token")
    shutil.rmtree(resources.owned("colacci-law-proof", str(runtime), "token"))
    assert retained.read_text() == "preserve"
    assert (evidence / "proof.json").read_text() == "{}"
    assert evidence.stat().st_mode & 0o777 == 0o700


def test_existing_evidence_and_symlink_runtime_are_refused(campaign_root):
    evidence = campaign_root / "evidence"
    evidence.mkdir()
    (evidence / "old.json").write_text("historical")
    with pytest.raises(ValueError, match="already exists"):
        resources.claim("colacci-law-proof", str(campaign_root / "runtime"), str(evidence), "token")
    alias = campaign_root / "alias"
    alias.symlink_to(evidence, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        resources.bounded_path(str(alias / "child"))
    assert (evidence / "old.json").read_text() == "historical"


def test_retained_owner_runtime_is_always_refused():
    with pytest.raises(ValueError, match="retained owner"):
        resources.bounded_path("/tmp/colacci-law-slice4-local")


@pytest.mark.parametrize(
    "name",
    [
        "collect_local_acceptance_evidence",
        "finalize_local_acceptance_evidence",
        "write_local_acceptance_cleanup_evidence",
    ],
)
def test_acceptance_evidence_override_reaches_each_consumer(monkeypatch, tmp_path, name):
    monkeypatch.setenv("COLACCI_EVIDENCE_ROOT", str(tmp_path))
    module = importlib.import_module("scripts." + name)
    importlib.reload(module)
    assert tmp_path == module.EVIDENCE_ROOT
    module._write("override-proof.json", {"isolated": True})
    assert json.loads((tmp_path / "override-proof.json").read_text()) == {"isolated": True}
    monkeypatch.delenv("COLACCI_EVIDENCE_ROOT")
    importlib.reload(module)


@pytest.mark.parametrize("name", ["transcription_cli_preflight", "inspect_slice3c_evidence"])
def test_cli_host_override_reaches_consumers(monkeypatch, tmp_path, name):
    monkeypatch.setenv("COLACCI_CLI_ROOT", str(tmp_path))
    module = importlib.import_module("scripts." + name)
    importlib.reload(module)
    assert tmp_path / "evidence" == module.EVIDENCE_ROOT
    monkeypatch.delenv("COLACCI_CLI_ROOT")
    importlib.reload(module)


def test_candidate_image_override_selects_all_observed_images(monkeypatch):
    monkeypatch.setenv("COLACCI_CANDIDATE_IMAGE_PREFIX", "colacci-law-proof")
    with (
        patch.object(images, "_image_metadata", return_value=("sha256:example", {})) as metadata,
        patch.object(images, "_container_output", return_value="1.0.0"),
    ):
        images.collect_image_observation()
    assert [call.args[0] for call in metadata.call_args_list] == [
        f"colacci-law-proof-{service}:latest" for service in ("api", "worker", "web", "e2e")
    ]


def test_make_mount_overrides_reach_container_paths():
    root = Path(__file__).resolve().parents[2]
    environment = dict(
        os.environ,
        COLACCI_SYNTHETIC_ROOT="/tmp/colacci-law-proof-audio",
        COLACCI_CLI_ROOT="/tmp/colacci-law-proof-cli",
        COLACCI_FIXTURE_IMAGE="colacci-law-proof-api:latest",
    )
    recipes = []
    selected = False
    for line in (root / "Makefile").read_text().splitlines():
        if line and not line.startswith("\t"):
            selected = line in {
                "test-audio: generate-test-audio",
                "test-transcription-contract: generate-test-audio",
                "test-transcription-cli-offline:",
            }
        if selected and line.startswith("\t") and " run " in line:
            recipes.append(
                line.strip()
                .replace("$(COMPOSE)", "docker compose")
                .replace("$(CURDIR)", str(root))
                .replace("$$", "$")
            )
    # Exercise the actual recipe shell expansions with an inert Docker function.
    output = subprocess.run(  # noqa: S603 -- repository recipes, inert Docker function
        ["/bin/bash", "-c", 'docker() { printf "%s\\n" "$@"; };\n' + "\n".join(recipes)],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert output.count("/tmp/colacci-law-proof-audio:/tmp/colacci-law-slice3a") == 2
    assert output.count("/tmp/colacci-law-proof-cli:/tmp/colacci-law-slice3c") == 3
    assert output.count("colacci-law-proof-api:latest") == 3


def test_shell_failure_trap_cleans_only_claimed_runtime(campaign_root):
    root = Path(__file__).resolve().parents[2]
    executable = campaign_root / "docker"
    command_log = campaign_root / "docker.log"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_TEST_LOG"\n')
    executable.chmod(0o700)
    runtime, evidence = campaign_root / "runtime", campaign_root / "evidence"
    environment = dict(
        os.environ,
        PATH=str(campaign_root) + os.pathsep + os.environ["PATH"],
        DOCKER_TEST_LOG=str(command_log),
        repository_root=str(root),
        project_name="colacci-law-proof",
        runtime_root=str(runtime),
        evidence_root=str(evidence),
    )
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'set -euo pipefail; source "$repository_root/scripts/campaign_resources.sh"; '
            "campaign_claim; trap campaign_cleanup EXIT; "
            'echo proof > "$evidence_root/proof.txt"; false',
        ],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    assert not runtime.exists()
    assert (evidence / "proof.txt").read_text().strip() == "proof"
    assert (evidence / "proof.txt").stat().st_mode & 0o777 == 0o600
    assert (
        "compose -p colacci-law-proof --profile e2e down -v --remove-orphans"
        in command_log.read_text()
    )


def test_review_launcher_overrides_reach_compose(monkeypatch, tmp_path):
    monkeypatch.setenv("COLACCI_REVIEW_PROJECT", "colacci-law-frozen-host")
    monkeypatch.setenv("COLACCI_REVIEW_RUNTIME", str(tmp_path))
    monkeypatch.setenv("COLACCI_REVIEW_PORT", "15179")
    module = importlib.import_module("scripts.local_review")
    importlib.reload(module)
    with patch.object(module.subprocess, "run") as run:
        module.compose("config")
    assert run.call_args.kwargs["env"]["SLICE4_RUNTIME_ROOT"] == str(tmp_path)
    assert run.call_args.kwargs["env"]["COMPOSE_PROJECT_NAME"] == "colacci-law-frozen-host"
    assert module.PORT == 15179
    for key in ("COLACCI_REVIEW_PROJECT", "COLACCI_REVIEW_RUNTIME", "COLACCI_REVIEW_PORT"):
        monkeypatch.delenv(key)
    importlib.reload(module)


@pytest.mark.parametrize("matches", [True, False])
def test_acceptance_finalizer_binds_observed_runtime_to_source(monkeypatch, tmp_path, matches):
    from scripts import finalize_local_acceptance_evidence as finalizer

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    observation = {"api": {"python": "observed-runtime"}}
    (candidate / "candidate-images.json").write_text(
        json.dumps(
            {
                "candidate_commit": "current" if matches else "stale",
                "candidate_tree": "current",
                "images": observation,
            }
        )
    )
    monkeypatch.setattr(finalizer, "EVIDENCE_ROOT", tmp_path / "evidence")
    monkeypatch.setattr(finalizer, "_git", lambda *args: "current")
    if matches:
        assert finalizer.observed_candidate_images() == observation
    else:
        with pytest.raises(SystemExit, match="does not match"):
            finalizer.observed_candidate_images()
