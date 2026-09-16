# Supported input boundaries

The application remains offline. Separate host-only CLI tooling lives under
`scripts/p1/`; see [operator boundaries](runbooks/p1-cli-adapter.md).
The historical HTTP/Whisper harness is not the selected transport.

The application accepts deterministic fixture events, allowlisted generated audio and strict
invented-transcript JSON. These application paths have no telephony ingestion, live transcription provider, CLI
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
The fixture verification harness `scripts/verify_transcript_import.py` uses the same importer
but also writes test feedback and report evidence. It accepts only an empty `_test` database;
it is not a general import utility. See [testing](testing.md#transcript-fixture-verification).

## Historical compatibility

Earlier application provider experiments and their configuration, SDK dependency, preflights
and fixtures are retired. Current host CLI tooling is documented separately above.
Migration history, existing metadata tables and serialized provenance remain readable so cleanup
and audit history are not silently lost. See [data models](data-models.md) and
[source ownership](ssot.md). Future external integrations require a new implementation and
contract; old ADRs are historical rationale, not setup instructions.
