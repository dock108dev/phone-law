# Transcript-only local fixture

This directory contains one entirely invented, contract-valid synthetic transcript artifact for
the explicit `local_dev` import command. It contains no audio, real person, client data, provider
payload, credential, project identifier, or externally sourced text.

The importer validates the complete artifact before creating database state. Its source identifier,
call identifier, transcript identifier, processing-attempt identifier, source label, language,
timestamps, speaker identities, and provenance are all deterministic and fail closed.
