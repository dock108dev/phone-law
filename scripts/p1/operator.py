"""Explicit P1 operator boundary. Only invented offline execution is available."""

import argparse
import json
from pathlib import Path

from packages.review.transcript_import import load_transcript_only_artifact

from .cli_adapter import AdapterError, MockRunner, OperatorSelection, Request, transcribe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--transport", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        selection = OperatorSelection(args.profile, args.transport)
        if not args.offline:
            raise AdapterError("p1c_required")
        artifact = load_transcript_only_artifact(
            Path("fixtures/transcript-only/invented-call.json").resolve()
        )
        payload = json.dumps(
            {
                "text": "Invented check.",
                "segments": [{"speaker": "A", "start": 0, "end": 1, "text": "Invented check."}],
            }
        ).encode()
        result = transcribe(
            selection,
            Request(b"invented-offline-input", 1, "en"),
            artifact.transcript.provenance,
            "p1b-offline-call",
            runner=MockRunner(payload),
        )
        print(
            json.dumps(
                {
                    "status": "offline_pass",
                    "segments": len(result.segments),
                    "result_kind": "mocked_cli",
                    "provider_requests": 0,
                }
            )
        )
    except AdapterError as exc:
        print(json.dumps({"status": "blocked", "code": exc.code, "provider_requests": 0}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
