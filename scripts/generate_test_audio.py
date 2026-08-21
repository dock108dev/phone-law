"""Generate invented non-human media with local macOS voices only."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from packages.generated_audio_scripts import (
    ENGLISH_LONG_A_TEXT,
    ENGLISH_LONG_B_TEXT,
    ENGLISH_SHORT_TEXT,
    SPANISH_SHORT_TEXT,
)

SLICE_ROOT = Path(
    os.environ.get(
        "COLACCI_SYNTHETIC_ROOT",
        "/tmp/colacci-law-slice3a",  # nosec B108
    )
)
ASSET_ROOT = SLICE_ROOT / "generated"
REPORT_ROOT = SLICE_ROOT / "reports"
MANIFEST_PATH = SLICE_ROOT / "generated-manifest.json"
APP_MAX_BYTES = 20 * 1024 * 1024


def _opaque_name(asset_id: str, suffix: str = ".wav") -> str:
    return hashlib.sha256(f"slice3a:{asset_id}".encode()).hexdigest()[:32] + suffix


def _run(command: list[str]) -> None:
    subprocess.run(  # noqa: S603  # nosec B603
        command,
        check=True,
        capture_output=True,
        timeout=120,
    )


def _voices() -> dict[str, list[str]]:
    completed = subprocess.run(  # nosec B603
        ["/usr/bin/say", "-v", "?"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    result: dict[str, list[str]] = {"en": [], "es": []}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        locale_index = next(
            (index for index, part in enumerate(parts) if part.startswith(("en_", "es_"))),
            None,
        )
        if locale_index is None:
            continue
        language = parts[locale_index].split("_", 1)[0]
        result[language].append(" ".join(parts[:locale_index]))
    return result


def _speak(text: str, voice: str, destination: Path, ffmpeg: str) -> None:
    intermediate = destination.with_suffix(".aiff")
    _run(["/usr/bin/say", "-v", voice, "-o", str(intermediate), text])
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(intermediate),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
    )
    intermediate.unlink(missing_ok=True)


def _entry(asset_id: str, kind: str, path: Path) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "kind": kind,
        "synthetic": True,
        "filename": path.name,
        "byte_size": path.stat().st_size,
        "status": "generated",
    }


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or not Path("/usr/bin/say").exists():
        raise SystemExit("local-generation unavailable: required offline media tools missing")
    if not str(SLICE_ROOT).startswith("/tmp/colacci-law-"):  # nosec B108
        raise SystemExit("unsafe generation root")
    if ASSET_ROOT.exists():
        shutil.rmtree(ASSET_ROOT)
    ASSET_ROOT.mkdir(mode=0o700, parents=True)
    REPORT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SLICE_ROOT, 0o700)
    os.chmod(ASSET_ROOT, 0o700)
    os.chmod(REPORT_ROOT, 0o700)

    voices = _voices()
    entries: list[dict[str, Any]] = []
    unavailable: list[str] = []
    if voices["en"]:
        en_short_path = ASSET_ROOT / _opaque_name("english-short")
        _speak(ENGLISH_SHORT_TEXT, voices["en"][0], en_short_path, ffmpeg)
        entries.append(_entry("english-short", "short_english_mono", en_short_path))
    else:
        unavailable.append("english_local_voice")

    if len(voices["en"]) >= 2:
        long_first = ASSET_ROOT / _opaque_name("english-long-a")
        long_second = ASSET_ROOT / _opaque_name("english-long-b")
        _speak(ENGLISH_LONG_A_TEXT, voices["en"][0], long_first, ffmpeg)
        _speak(ENGLISH_LONG_B_TEXT, voices["en"][1], long_second, ffmpeg)
        en_long_path = ASSET_ROOT / _opaque_name("english-long")
        _run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(long_first),
                "-i",
                str(long_second),
                "-filter_complex",
                "[0:a][1:a]concat=n=2:v=0:a=1[out]",
                "-map",
                "[out]",
                str(en_long_path),
            ]
        )
        long_first.unlink(missing_ok=True)
        long_second.unlink(missing_ok=True)
        entry = _entry(
            "english-long",
            "english_multi_speaker_over_30_seconds",
            en_long_path,
        )
        entry["speaker_source_count"] = 2
        entries.append(entry)
    else:
        unavailable.append("english_long_multiple_local_voices")

    if voices["es"]:
        es_short_path = ASSET_ROOT / _opaque_name("spanish-short")
        _speak(SPANISH_SHORT_TEXT, voices["es"][0], es_short_path, ffmpeg)
        entries.append(_entry("spanish-short", "short_spanish_mono", es_short_path))
    else:
        unavailable.append("spanish_local_voice")

    if len(voices["en"]) >= 2:
        first = ASSET_ROOT / _opaque_name("speaker-a")
        second = ASSET_ROOT / _opaque_name("speaker-b")
        _speak(
            "This invented participant asks for a checklist review.",
            voices["en"][0],
            first,
            ffmpeg,
        )
        _speak(
            "This different synthetic participant says a human reviewer will confirm it.",
            voices["en"][1],
            second,
            ffmpeg,
        )
        multi_path = ASSET_ROOT / _opaque_name("multiple-speakers")
        _run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(first),
                "-i",
                str(second),
                "-filter_complex",
                "[0:a][1:a]concat=n=2:v=0:a=1[out]",
                "-map",
                "[out]",
                str(multi_path),
            ]
        )
        entries.append(_entry("multiple-speakers", "multi_speaker_synthetic", multi_path))
        stereo_path = ASSET_ROOT / _opaque_name("dual-channel")
        _run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(first),
                "-i",
                str(second),
                "-filter_complex",
                "[0:a][1:a]amerge=inputs=2[out]",
                "-map",
                "[out]",
                "-ac",
                "2",
                str(stereo_path),
            ]
        )
        entries.append(_entry("dual-channel", "stereo_channel_preservation", stereo_path))
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)
    else:
        unavailable.append("multiple_local_english_voices")

    silent_path = ASSET_ROOT / _opaque_name("silent")
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "3",
            str(silent_path),
        ]
    )
    entries.append(_entry("silent", "silent_supported_media", silent_path))

    empty_path = ASSET_ROOT / _opaque_name("empty")
    empty_path.touch(mode=0o600)
    entries.append(_entry("empty", "empty_rejection", empty_path))
    malformed_path = ASSET_ROOT / _opaque_name("malformed")
    malformed_path.write_bytes(b"RIFF\x10\x00\x00\x00WAVEbroken")
    entries.append(_entry("malformed", "corrupt_rejection", malformed_path))
    unsupported_path = ASSET_ROOT / _opaque_name("unsupported", ".bin")
    unsupported_path.write_bytes(b"invented unsupported media boundary input")
    entries.append(_entry("unsupported", "unsupported_rejection", unsupported_path))
    oversized_path = ASSET_ROOT / _opaque_name("oversized")
    with oversized_path.open("wb") as oversized:
        oversized.truncate(APP_MAX_BYTES + 1)
    entries.append(_entry("oversized", "oversized_rejection", oversized_path))
    overlong_path = ASSET_ROOT / _opaque_name("overlong")
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=8000:cl=mono",
            "-t",
            "61",
            str(overlong_path),
        ]
    )
    entries.append(_entry("overlong", "overlong_rejection", overlong_path))

    for path in ASSET_ROOT.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
    manifest = {"version": "generated-audio-v1", "assets": entries, "unavailable": unavailable}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.chmod(MANIFEST_PATH, 0o600)
    safe_report = {
        "version": "generated-audio-report-v1",
        "generator": "macos-local-speech-and-ffmpeg",
        "external_services_used": False,
        "human_voice_recorded": False,
        "synthetic_asset_count": len(entries),
        "inventory": [
            {
                "asset_id": item["asset_id"],
                "kind": item["kind"],
                "synthetic": True,
                "byte_size": item["byte_size"],
                "status": item["status"],
            }
            for item in entries
        ],
        "unavailable_optional_capabilities": unavailable,
    }
    report_path = REPORT_ROOT / "generated-audio-report.json"
    report_path.write_text(json.dumps(safe_report, indent=2, sort_keys=True) + "\n")
    os.chmod(report_path, 0o600)
    print(
        f"generated-media pass: {len(entries)} synthetic assets; "
        f"unavailable optional capabilities={len(unavailable)}; external services=0"
    )


if __name__ == "__main__":
    main()
