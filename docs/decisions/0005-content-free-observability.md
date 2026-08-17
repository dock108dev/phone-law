# ADR 0005: Allowlisted content-free observability

**Status:** Accepted for Slice 0

Use opaque correlation IDs and an allowlisted JSON logger rather than arbitrary messages or
structured dictionaries. Disable access and SQL logs. Record only operational state needed to
answer whether a service, database, or migration is healthy. This deliberately sacrifices rich
debug details to prevent future client content and credentials from escaping into logs.
