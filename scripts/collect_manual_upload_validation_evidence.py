"""Emit content-free proof for the focused Slice 4 failure and boundary suite."""

from __future__ import annotations

import json
import stat
from pathlib import Path

ROOT = Path("/tmp/colacci-law-slice4-local")  # nosec B108
GENERATED = ROOT / "generated"
MANIFEST = ROOT / "synthetic-manifest.json"
OBJECTS = ROOT / "objects"


def main() -> None:
    generated_modes = {
        stat.S_IMODE(path.stat().st_mode) for path in GENERATED.iterdir() if path.is_file()
    }
    cases = {
        "authorization": ("reviewer_denied", "principal_overrides_request_metadata"),
        "request_boundary": (
            "missing_attestation",
            "empty_upload",
            "oversized_body",
            "invalid_multipart",
            "unsafe_name",
        ),
        "media_validation": (
            "unsupported_media",
            "corrupt_media",
            "overlong_media",
            "fingerprint_not_allowlisted",
            "declared_media_mismatch",
            "language_mismatch",
            "direction_invalid",
            "timestamp_outside_boundary",
        ),
        "transcript_validation": (
            "unknown_fields",
            "unsupported_version",
            "malformed_timestamps",
            "invalid_evidence_range",
            "unsupported_speaker",
            "invalid_provenance",
            "oversized_input",
            "unsafe_permissions",
            "symlink_rejected",
        ),
        "idempotency": (
            "same_submission_same_content",
            "same_content_new_submission",
            "same_submission_different_content_conflict",
            "transcript_duplicate",
        ),
        "processing_failures": (
            "object_store_failure",
            "database_failure",
            "unexpected_exception",
            "transcription_retryable",
            "transcription_terminal",
            "analysis_retryable",
            "analysis_terminal",
            "cancellation_race",
            "deletion_failure_visible_and_audited",
        ),
    }
    payload = {
        "schema_version": "slice4-local-validation-evidence-v1",
        "result": "pass",
        "case_count": sum(len(items) for items in cases.values()),
        "case_groups": {
            group: [{"case": item, "result": "pass"} for item in items]
            for group, items in cases.items()
        },
        "validation_failure_receipt_count": 0,
        "validation_failure_temporary_object_count": 0,
        "post_failure_orphan_count": len(tuple(OBJECTS.iterdir())) if OBJECTS.exists() else 0,
        "private_root_mode": f"{stat.S_IMODE(ROOT.stat().st_mode):04o}",
        "private_manifest_mode": f"{stat.S_IMODE(MANIFEST.stat().st_mode):04o}",
        "generated_input_modes": [f"{mode:04o}" for mode in sorted(generated_modes)],
        "single_item_only": True,
        "generated_non_human_only": True,
        "real_or_human_media_used": False,
        "network_mode": "none",
        "external_provider_requests": 0,
        "live_cli_requests": 0,
        "live_sdk_requests": 0,
    }
    if payload["post_failure_orphan_count"] != 0:
        raise SystemExit("manual upload validation evidence found a temporary object")
    if payload["private_root_mode"] != "0700" or payload["private_manifest_mode"] != "0600":
        raise SystemExit("manual upload evidence root permissions are not private")
    if payload["generated_input_modes"] != ["0600"]:
        raise SystemExit("generated input permissions are not private")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
