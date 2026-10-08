# Validation — Phase 3 / version 3.2

Checked in Linux with Python 3.12 and Node 24.19.0. Report prepared 8 October 2026. These results describe local automated checks, not live Stripe or production deployment.

| Check | Result |
| --- | --- |
| Backend suite (`python -m pytest -q`) | 102 passed |
| Frontend component suite (`npm test`) | 13 passed across 2 files |
| TypeScript and Vite production build | Passed; bundled interface rebuilt |
| Alembic schema/model alignment and downgrade | Passed within backend suite |
| Upgrade of populated Phase 2 SQLite data | Passed; job/usage foreign-key links preserved, downgrade also checked |
| Concurrent Free quota submissions | 8 simultaneous requests: 5 admitted, 3 rejected; failed job restores capacity |
| Stripe signature verification | Real SDK verification; malformed, wrong-secret and expired signatures rejected |
| Stripe integration behavior | Mocked API transport; duplicate/stale webhooks, failure/retry, price allowlist, customer mapping, checkout reuse/plan switch and portal routing passed |
| Team isolation and limits | Single-use/expired/revoked invite cases, seats, member removal, shared templates and shared owner/member quota passed |

The suite retains the earlier formatting, ownership, authentication, queue, PDF adapter, storage and retention checks. Completion does not double-count reserved quota. Expired subscriptions lose entitlement and active team membership receives paid retention. The new frontend tests cover pilot-disabled payments, actionable billing errors, team invitations, shared-template publishing and the quota upgrade link.

Not exercised: actual Stripe sandbox/live requests, real portal configuration, production Postgres concurrency, real S3 deployment, Windows launcher/Word COM, target-host LibreOffice rendering, a live-browser visual review, production deployment or a 20–50-user pilot. Frontend tests use a simulated DOM. PDF engine adapter tests do not certify report pagination.

One upstream Starlette/httpx test-client deprecation warning was reported; tests passed. jsdom reports that document navigation is unimplemented for an existing download test; actual browser downloads were not exercised here.

`TEST_RESULTS_ARCHIVE.md` contains historical results shipped in the input ZIP. The farming-report render and historical HTTP smoke test described there were not repeated in this Phase 3 run.
