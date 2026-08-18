"""Exercise the complete offline media boundary and emit content-free evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, cast

from packages.config import AppProfile
from packages.contracts.media import MediaErrorClass
from packages.media import (
    LocalSyntheticObjectStore,
    MediaBoundaryError,
    MediaInspector,
    MediaNormalizer,
)

SLICE_ROOT = Path("/tmp/colacci-law-slice3a")  # nosec B108
ASSET_ROOT = SLICE_ROOT / "generated"
OBJECT_ROOT = SLICE_ROOT / "objects"
REPORT_ROOT = SLICE_ROOT / "reports"
MANIFEST_PATH = SLICE_ROOT / "generated-manifest.json"


def _artifact_id(asset_id: str) -> str:
    return hashlib.sha256(f"artifact:{asset_id}".encode()).hexdigest()[:32]


def _validate_log(content: str) -> None:
    forbidden_terms = (
        "api key",
        "audio",
        "authorization",
        "caller",
        "credential",
        "database",
        "filename",
        "local path",
        "provider",
        "secret",
        "staff",
        "transcript",
        "url",
    )
    if any(term in content.lower() for term in forbidden_terms):
        raise AssertionError("media operations log contains a forbidden term")


def main() -> None:
    manifest = cast(dict[str, Any], json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
    assets = cast(list[dict[str, Any]], manifest["assets"])
    store = LocalSyntheticObjectStore(
        OBJECT_ROOT,
        profile=AppProfile.TEST,
        approved_source_root=ASSET_ROOT,
    )
    inspector = MediaInspector(
        max_bytes=20 * 1024 * 1024,
        max_duration_seconds=60,
        allowed_root=OBJECT_ROOT,
    )
    normalizer = MediaNormalizer(store=store, inspector=inspector)
    expected_failures = {
        "empty": MediaErrorClass.EMPTY_MEDIA,
        "malformed": MediaErrorClass.CORRUPT_MEDIA,
        "unsupported": MediaErrorClass.UNSUPPORTED_MEDIA,
        "oversized": MediaErrorClass.OVERSIZED_MEDIA,
        "overlong": MediaErrorClass.OVERLONG_MEDIA,
    }
    inspected: list[dict[str, object]] = []
    rejected: dict[str, str] = {}
    deletion_events = []
    channel_preservation = False
    file_modes: set[str] = set()
    normalized_count = 0
    lifecycle_counts = dict.fromkeys(
        (
            "RECEIVED",
            "INSPECTED",
            "NORMALIZED",
            "TRANSCRIBING",
            "TRANSCRIBED",
            "DELETED",
        ),
        0,
    )

    for asset in assets:
        asset_id = cast(str, asset["asset_id"])
        source = ASSET_ROOT / cast(str, asset["filename"])
        artifact_id = _artifact_id(asset_id)
        reference = store.import_file(source, artifact_id=artifact_id)
        lifecycle_counts["RECEIVED"] += 1
        file_modes.add(f"{store.permission_mode(reference):04o}")
        try:
            inspection = inspector.inspect(store.resolve(reference), artifact_id=artifact_id)
        except MediaBoundaryError as exc:
            expected = expected_failures.get(asset_id)
            if expected is None or exc.error_class is not expected:
                raise AssertionError(f"unexpected rejection class for {asset_id}") from exc
            rejected[asset_id] = exc.error_class.value
            deletion = store.delete(reference)
            if not deletion.deletion_confirmed:
                raise AssertionError("terminal rejection cleanup was not confirmed") from exc
            deletion_events.append(deletion)
            lifecycle_counts["DELETED"] += 1
            continue

        if asset_id in expected_failures:
            raise AssertionError(f"rejection asset unexpectedly passed: {asset_id}")
        lifecycle_counts["INSPECTED"] += 1
        normalized_reference, result = normalizer.normalize(reference, inspection)
        lifecycle_counts["NORMALIZED"] += 1
        if result.normalized:
            normalized_count += 1
            file_modes.add(f"{store.permission_mode(normalized_reference):04o}")
        if asset_id == "dual-channel":
            channel_preservation = inspection.channel_count == result.channel_count == 2
        inspected.append(
            {
                "asset_id": asset_id,
                "format": result.media_format.value,
                "byte_size": result.byte_size,
                "duration_seconds": round(result.duration_seconds, 3),
                "sample_rate_hz": result.sample_rate_hz,
                "channel_count": result.channel_count,
                "normalized": result.normalized,
                "hash_reference": inspection.hash_reference,
            }
        )
        if normalized_reference.object_id != reference.object_id:
            normalized_deletion = store.delete(normalized_reference)
            if not normalized_deletion.deletion_confirmed:
                raise AssertionError("normalized object cleanup was not confirmed")
            deletion_events.append(normalized_deletion)
            lifecycle_counts["DELETED"] += 1
        original_deletion = store.delete(reference)
        if not original_deletion.deletion_confirmed:
            raise AssertionError("original object cleanup was not confirmed")
        deletion_events.append(original_deletion)
        lifecycle_counts["DELETED"] += 1

    if set(rejected) != set(expected_failures):
        raise AssertionError("not every media rejection class was exercised")
    if any(OBJECT_ROOT.iterdir()):
        raise AssertionError("temporary object root is not empty")
    if not channel_preservation:
        raise AssertionError("stereo channel structure was not preserved")
    if (OBJECT_ROOT.stat().st_mode & 0o777) != 0o700 or file_modes != {"0600"}:
        raise AssertionError("temporary permissions are not restrictive")

    REPORT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    operation_log = REPORT_ROOT / "slice3a-media-operations.log"
    operation_log.write_text(
        "".join(
            json.dumps(
                {
                    "case_code": f"case-{index + 1:03d}",
                    "event": "boundary_case_completed",
                    "outcome": "rejected" if item["asset_id"] in rejected else "accepted",
                    "status": "pass",
                },
                sort_keys=True,
            )
            + "\n"
            for index, item in enumerate(assets)
        ),
        encoding="utf-8",
    )
    os.chmod(operation_log, 0o600)
    _validate_log(operation_log.read_text(encoding="utf-8"))
    report = {
        "version": "media-boundary-report-v1",
        "status": "pass",
        "external_services_used": False,
        "valid_media_count": len(inspected),
        "rejection_count": len(rejected),
        "rejections": rejected,
        "normalization_count": normalized_count,
        "channel_preservation_confirmed": channel_preservation,
        "temporary_directory_mode": "0700",
        "temporary_file_modes": sorted(file_modes),
        "deletion_event_count": len(deletion_events),
        "all_deletions_confirmed": all(item.deletion_confirmed for item in deletion_events),
        "remaining_temporary_object_count": 0,
        "lifecycle_counts": lifecycle_counts,
        "operations_log_content_scan": "pass",
        "inspections": inspected,
    }
    report_path = REPORT_ROOT / "media-boundary-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.chmod(report_path, 0o600)
    shutil.rmtree(ASSET_ROOT)
    MANIFEST_PATH.unlink(missing_ok=True)
    OBJECT_ROOT.rmdir()
    print(
        f"media-boundary pass: valid={len(inspected)} rejected={len(rejected)} "
        f"deletions={len(deletion_events)} remaining=0"
    )


if __name__ == "__main__":
    main()
