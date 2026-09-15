"""Durable offline readiness check and explicit owner-local one-shot resume."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
import time
from pathlib import Path
from typing import Any

from . import local_probe as probe
from .admission import ROOT, implementation_identity
from .campaign import (
    CAMPAIGN,
    AdmissionError,
    Campaign,
    create_private,
    decode,
    digest,
    encoded,
    private_directory,
    read_private,
)
from .cli_adapter import MODEL
from .cli_check import load_contract


def runtime_versions() -> dict[str, str]:
    return {d.metadata["Name"].lower(): d.version for d in importlib.metadata.distributions()}


def check() -> dict[str, Any]:
    """No prompt, binding, reservation, provider call, or campaign initialization."""
    manifest = decode(read_private(probe.DIRECTORY / "prepared.json"))
    if implementation_identity() != manifest["source_sha256"]:
        raise AdmissionError("prepared_source_changed")
    if runtime_versions() != manifest["runtime_versions"]:
        raise AdmissionError("prepared_runtime_changed")
    if digest(Path(sys.executable).resolve().read_bytes()) != manifest["python_sha256"]:
        raise AdmissionError("prepared_python_changed")
    for name, expected in manifest["files"].items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise AdmissionError("prepared_file_changed")
    for name, expected in manifest["private_files"].items():
        if digest(read_private(probe.DIRECTORY / name)) != expected:
            raise AdmissionError("prepared_evidence_changed")
    request, _ = probe.sample()
    if digest(request.media) != manifest["media_sha256"]:
        raise AdmissionError("prepared_media_changed")
    contract = load_contract()
    if (
        digest((Path.home() / contract["relative_install_path"]).read_bytes())
        != contract["binary_sha256"]
    ):
        raise AdmissionError("tool_changed")
    # Restore ONLY absent immutable evidence at the paths embedded in the original ledger.
    # Never rewrite the ledger or overwrite a changed historical record.
    for ref in manifest["historical_evidence"]:
        original = Path(ref["path"])
        backup = read_private(probe.DIRECTORY / ref["backup"])
        if digest(backup) != ref["sha256"]:
            raise AdmissionError("history_backup_changed")
        if not original.exists() and not original.is_symlink():
            original.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            private_directory(original.parent)
            create_private(original, backup)
        if digest(read_private(original)) != ref["sha256"]:
            raise AdmissionError("history_changed")
    campaign = Campaign(Path.home() / ".local/state/colacci-law")
    with campaign.locked():
        _, pending, raw = campaign.state()
        if pending or digest(raw) != manifest["ledger_sha256"]:
            raise AdmissionError("campaign_changed_review_required")
        if (campaign.root / (probe.SCOPE + ".used")).exists():
            raise AdmissionError("single_probe_already_attempted")
    return manifest


def bind(project: str, manifest: dict[str, Any]) -> Path:
    """New one-hour execution binding; substantive owner approval stays unchanged."""
    if not re.fullmatch(r"proj_[A-Za-z0-9_-]+", project):
        raise AdmissionError("project_required")
    # Recheck the frozen preparation, never bless whatever source happens to be current.
    if check() != manifest:
        raise AdmissionError("preparation_changed")
    decision = probe.DIRECTORY / "owner-approval-20260913.json"
    owner = decode(read_private(decision))
    if not (
        owner["scope"] == probe.SCOPE
        and owner["owner_reply"] == "approved, no additional requests"
        and owner["estimated_attempt_approved"] is True
        and owner["billing_and_redirect_limitations_accepted"] is True
        and owner["additional_colacci_requests"] == 0
    ):
        raise AdmissionError("owner_decision_changed")
    issued = int(time.time())
    record = {
        "scope": probe.SCOPE,
        "campaign": CAMPAIGN,
        "model": MODEL,
        "source_sha256": manifest["source_sha256"],
        "media_sha256": manifest["media_sha256"],
        "contract_sha256": digest((ROOT / "scripts/p1/cli-contract.json").read_bytes()),
        "requests": 1,
        "automatic_retries": 0,
        "estimate_micro_usd": probe.ESTIMATE_MICRO_USD,
        "authorize_estimated_request_without_guaranteed_2usd_ceiling": True,
        "accept_same_origin_redirect_gets": True,
        "accept_unverified_physical_request_count": True,
        "project_key_matches_selected_project": True,
        "example": False,
        "account_kind": "personal_development",
        "project_id": project,
        "reviewer": "existing owner approval; fresh owner-local project entry",
        "issued_at": issued,
        "expires_at": issued + 3600,
        "owner_decision": {"path": str(decision), "sha256": digest(read_private(decision))},
        "prepared_sha256": digest(read_private(probe.DIRECTORY / "prepared.json")),
    }
    approval = probe.DIRECTORY / f"execution-approval-{time.time_ns()}.json"
    create_private(approval, encoded(record))
    return approval


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "enter"))
    args = parser.parse_args()
    try:
        manifest = check()
        if args.mode == "check":
            print("Offline preparation verified. No binding, reservation or provider request.")
            return 0
        if not sys.stdin.isatty():
            raise AdmissionError("owner_local_terminal_required")
        print("Already approved: one generated sample, estimated $0.06, no retries.")
        print("A NEW one-hour execution binding will be recorded for this prepared source.")
        print("Enter the personal/development project ID; then its matching key when prompted.")
        project = input("Personal/development Platform project ID (proj_...): ").strip()
        approval = bind(project, manifest)
        result = probe.run(approval)
        print("Result:", result["status"], "— stop; no automatic retry.")
        return 0 if result["status"] == "observed_local_cli_success" else 2
    except Exception, KeyboardInterrupt:
        print("Stopped: local prerequisite or execution failure. No automatic retry.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
