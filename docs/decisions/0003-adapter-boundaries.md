# ADR 0003: Vendor-neutral adapter boundaries

**Status:** Accepted for Slice 0

Reserve separate `CallSource`, `Transcriber`, `Analyzer`, `ObjectStore`, and `Notifier` seams.
Only configuration names and documentation exist now. Broadvoice remains an unimplemented,
disabled placeholder until account-specific authentication, event, and recording behavior is
proved. No guessed contract is acceptable.
