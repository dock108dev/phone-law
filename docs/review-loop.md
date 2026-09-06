# Everyday review behavior

The morning briefing retains its explicit New York date. Month dates open briefings,
including weekends and closures; outside coverage is unavailable, never verified
zero. The latest earlier activity link is explicit. Supporting screens retain a
return to the selected briefing. Call and passage links preserve the recap anchor;
keyboard returns focus it, and reduced-motion users receive an immediate passage jump.

Assessment controls name the original finding being reviewed. Correct confirms that
analysis; Incorrect rejects it. Partial, unsupported, not-applicable and analysis-level
missing-finding feedback remain distinct. These events never complete real-world
callbacks, appointments, filings or other actions. History is chronological and names
the original finding, author and saved time; later assessments append new events.

Every browser save carries a stable request intent, retained in session storage until
the server confirms a persisted event. Repeated delivery uses the same event ID;
changed content under the same request ID returns a conflict. Authorization is checked
before replay. While a save is pending, repeat submission is locked. A lost response
keeps the same note and intent across reload and offers Retry same assessment. A
confirmed save followed by a refresh failure explicitly says it was saved. Definite
denials preserve the draft and never display success. Review events and audit events
remain append-only; no database migration or task-completion state was added.

Coverage names late occurrence, arrival and cutoff, failed results, duplicate deliveries
and absent inputs. A missing expected input cannot be retried. Transcript failure and
transcript-without-analysis are distinguished. Recovery retains prior attempts and
refreshes coverage with the original expected source IDs stored in the immutable report,
so retrying a received call cannot erase missing-call expectations. Older reports without
those IDs retain honest reconciliation-needed behavior until supported reseeding writes
the current projection. The report projection fingerprint is versioned independently
from unchanged fixture content.

Manual upload, failures, playbook and Operations remain reachable under their original
permissions. Engineering identity selection is inside Demo controls, outside the primary
lawyer workflow. The supported desktop launch is documented in
[Local development](runbooks/local-development.md#isolated-desktop-browser-review-rehearsal).
This document describes implemented behavior; the Desktop tracker alone records status.
