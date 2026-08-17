# Staging and production safety requirements

Slice 0 does not create or authorize staging or production. Before either process may start, its
configuration must use firm-owned SSO, a non-placeholder secret, a non-local database, private
cloud object storage, approved positive retention periods, HTTPS allowlisted origins, disabled
fixture adapters, and debug off.

Real-call mode additionally requires an explicit processing authorization switch and a recorded
non-placeholder approval reference. Passing this code guard is necessary but never sufficient:
every real-data preflight item in the Desktop roadmap must be approved, and later ingestion,
authorization, retention/deletion, audit, incident, backup, and access-control slices must pass.

Production startup failures emit only `unsafe_configuration` and exit 78. Do not weaken or
bypass this guard for a demo, test, or deadline.
