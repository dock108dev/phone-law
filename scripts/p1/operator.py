"""Explicit P1 operator boundary. Only invented offline execution is available."""

import argparse
import json
from pathlib import Path

from packages.review.transcript_import import load_transcript_only_artifact

from .admission import Inputs, execute, preflight
from .campaign import CAMPAIGN, AdmissionError, Campaign, read_private
from .cli_adapter import AdapterError, MockRunner, OperatorSelection, Request, transcribe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--transport", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--initialize", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--media", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--key-fd", type=int)
    args = parser.parse_args()
    try:
        selection = OperatorSelection(args.profile, args.transport)
        campaign = Campaign(Path.home() / ".local/state/colacci-law")
        inputs = Inputs(args.approval, args.media, args.provenance, args.key_fd)
        if sum((args.offline, args.preflight, args.initialize is not None)) > 1:
            raise AdmissionError("mode_conflict")
        if args.initialize is not None:
            campaign.initialize(read_private(args.initialize))
            print(
                json.dumps({"status": "initialized", "campaign": CAMPAIGN, "provider_requests": 0})
            )
            return 0
        if args.preflight or not args.offline:
            readiness = preflight(campaign, inputs)
            print(json.dumps(readiness.record(), sort_keys=True))
            if args.preflight:
                return 0 if readiness.ready else 2
            execute(campaign, inputs)
            return 2
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
    except (AdmissionError, OSError, ValueError, TypeError, KeyError) as exc:
        code = str(exc) if isinstance(exc, AdmissionError) else "local_state_invalid"
        print(json.dumps({"status": "blocked", "code": code, "provider_requests": 0}))
        return 2
    except AdapterError as exc:
        print(json.dumps({"status": "blocked", "code": exc.code, "provider_requests": 0}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
