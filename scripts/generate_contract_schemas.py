"""Generate or verify canonical JSON Schemas from strict Pydantic models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from packages.contracts.report import AuditEvent, DailyReport, ReviewEvent
from packages.contracts.review import (
    ExtractedFacts,
    IngestionEvent,
    NormalizedCall,
    PlaybookVersion,
    ProcessingAttempt,
    SanitizedProcessingFailure,
    StructuredAnalysis,
    Transcript,
)

SCHEMA_DIRECTORY = Path("packages/contracts/schemas")
MODELS: dict[str, type[BaseModel]] = {
    "extracted-facts.schema.json": ExtractedFacts,
    "ingestion-event.schema.json": IngestionEvent,
    "normalized-call.schema.json": NormalizedCall,
    "playbook-version.schema.json": PlaybookVersion,
    "processing-attempt.schema.json": ProcessingAttempt,
    "sanitized-processing-failure.schema.json": SanitizedProcessingFailure,
    "structured-analysis.schema.json": StructuredAnalysis,
    "transcript.schema.json": Transcript,
    "daily-report.schema.json": DailyReport,
    "review-event.schema.json": ReviewEvent,
    "audit-event.schema.json": AuditEvent,
}


def rendered_schema(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    SCHEMA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    for filename, model in MODELS.items():
        path = SCHEMA_DIRECTORY / filename
        expected = rendered_schema(model)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                stale.append(filename)
        else:
            path.write_text(expected, encoding="utf-8")
    if stale:
        raise SystemExit("contract schemas are stale: " + ",".join(stale))
    action = "verified" if args.check else "generated"
    print(f"contract-schemas {action}: {len(MODELS)}")


if __name__ == "__main__":
    main()
