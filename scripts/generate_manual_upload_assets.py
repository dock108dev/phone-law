"""Generate deterministic non-human WAV inputs and their private Slice 4 allowlist."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import wave
from pathlib import Path

ROOT = Path("/tmp/colacci-law-slice4-local")  # nosec B108
GENERATED = ROOT / "generated"
MANIFEST = ROOT / "synthetic-manifest.json"
SAMPLE_RATE = 16000
DURATION_SECONDS = 59


def write_tone(path: Path, frequency: float) -> str:
    half_second_frames = SAMPLE_RATE // 2
    one_second = b"".join(
        struct.pack(
            "<h",
            int(32767 * amplitude * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)),
        )
        for amplitude in (0.16, 0.08)
        for index in range(half_second_frames)
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(one_second * DURATION_SECONDS)
    os.chmod(path, 0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if Path("/tmp/colacci-law-slice4-local") != ROOT:  # nosec B108
        raise SystemExit("unsafe manual-upload generation root")
    # Preserve the evidence bundle across later full-suite runs while replacing
    # every generated input and transient object from the prior run.
    shutil.rmtree(GENERATED, ignore_errors=True)
    shutil.rmtree(ROOT / "objects", ignore_errors=True)
    MANIFEST.unlink(missing_ok=True)
    GENERATED.mkdir(mode=0o700, parents=True)
    os.chmod(ROOT, 0o700)
    os.chmod(GENERATED, 0o700)
    cases = (
        ("generated-success.wav", 330.0, "success"),
        ("generated-retry.wav", 440.0, "transcription_retryable_once"),
        ("generated-cancel.wav", 550.0, "success"),
        ("generated-transcription-terminal.wav", 660.0, "transcription_terminal"),
        ("generated-analysis-retry.wav", 770.0, "analysis_retryable_once"),
        ("generated-analysis-terminal.wav", 880.0, "analysis_terminal"),
        ("generated-unexpected.wav", 990.0, "success"),
        ("generated-deletion-failure.wav", 1100.0, "success"),
    )
    entries: list[dict[str, str]] = []
    for filename, frequency, outcome in cases:
        digest = write_tone(GENERATED / filename, frequency)
        entries.append(
            {
                "content_sha256": digest,
                "fixture_id": "CL-FX-002",
                "outcome": outcome,
            }
        )
    overlong = GENERATED / "generated-overlong.wav"
    with wave.open(str(overlong), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(b"\x00\x00" * SAMPLE_RATE * 61)
    os.chmod(overlong, 0o600)
    (GENERATED / "generated-corrupt.wav").write_bytes(b"RIFF\x08\x00\x00\x00WAVEfmt")
    os.chmod(GENERATED / "generated-corrupt.wav", 0o600)
    transcript_source = Path("fixtures/transcript-only/invented-call.json")
    transcript_destination = GENERATED / "invented-transcript.json"
    shutil.copyfile(transcript_source, transcript_destination)
    os.chmod(transcript_destination, 0o600)
    MANIFEST.write_text(
        json.dumps(
            {
                "manifest_version": "manual-upload-synthetic-manifest-v1",
                "generated_only": True,
                "entries": entries,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(MANIFEST, 0o600)
    print(
        "manual-upload-inputs accepted_audio=8 invalid_audio=2 transcript=1 generated_only=true "
        "human_recording=false external_services=false"
    )


if __name__ == "__main__":
    main()
