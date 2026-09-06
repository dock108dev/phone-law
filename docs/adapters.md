# Supported input boundaries

The application accepts deterministic fixture events, allowlisted generated audio and strict
invented-transcript JSON. There is no telephony ingestion, live transcription provider, CLI
transport, cloud object store or external notification implementation.

## Fixture processing

`packages/review/pipeline.py` sequences `FixtureCallSource`, `FixtureTranscriber` and
`FixtureAnalyzer`, then persists through the review repositories. Tests and seeders use these
same implementations. Fixture ordering and expected failures are deterministic.

## Manual upload

`packages/manual_upload/service.py` owns receipts and delegates to existing domain services.
Audio is bounded, checked against the private generated-input fingerprint manifest, inspected
and normalized by the local media boundary, and processed with fixture transcription/analysis.
Cleanup failure is visible. No provider client or process is constructed.

JSON uploads use `packages/review/transcript_import.py`. Whole-artifact validation precedes
persistence; deterministic IDs make duplicate import a no-op. Transcript import creates no
media object and invokes no transcriber. It reuses analysis, reports, evidence and feedback.
The explicit `scripts/import_transcript_only.py` command uses the same importer.

## Historical compatibility

Provider experiments and their configuration, SDK dependency, preflights and fixtures are retired.
Migration history, existing metadata tables and serialized provenance remain readable so cleanup
and audit history are not silently lost. See [data models](data-models.md) and
[source ownership](ssot.md). Future external integrations require a new implementation and
contract; old ADRs are historical rationale, not setup instructions.
