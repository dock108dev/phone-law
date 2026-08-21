# End-to-end tests

Run `make test-e2e` to create a disposable Slice 2 database and execute the complete synthetic
reviewer flow in pinned Chromium. The test covers report reconciliation, all review sections,
evidence focus, append-only feedback and reload persistence, the role matrix, current/resolved
failures, playbook publication, unchanged provenance, automated WCAG checks, screenshots, browser
diagnostics, content-free application logs, and safe database evidence. The disposable stack is
removed and the ordinary local stack is restored even when the test fails.
