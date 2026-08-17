# Local development and troubleshooting

Run `make bootstrap`, `make dev`, then `make smoke`. Stop with `make stop`; this preserves the
local synthetic database. Restart with `make dev`.

If a port is occupied, stop the conflicting local process or update only the host-side loopback
mapping. Do not publish services on all interfaces. If API or worker readiness fails, confirm
PostgreSQL is healthy and rerun `docker compose run --rm api alembic upgrade head`.

If a clean reset is necessary, `CONFIRM_LOCAL_DATA_DELETE=yes make clean` removes only Compose
resources named `colacci-law`, including its synthetic database volume. Then rerun bootstrap.

If a locked package changes, update the exact direct version first and mechanically regenerate
the relevant lock; run every stable command plus the separate advisory audit. Do not hand-edit a
resolved lockfile.

Tests, smoke checks, and migrations use no live AI, telephony, email, cloud, or identity service.
No external credential is accepted.
