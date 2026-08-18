# Deterministic local CLI fixtures

These cases are entirely invented and run with an injected runner or the repository fake executable.
They exercise the declared OpenAI CLI argument-array boundary without credentials or network access.
Response bodies reuse the accepted Slice 3A normalized provider fixtures; no second transcript schema
or response converter exists.

Generated audio is never committed here. Duration classes and process behaviors are metadata only.
Raw fake CLI stdout and stderr are consumed in memory and never copied into operational logs or
retained evidence.
