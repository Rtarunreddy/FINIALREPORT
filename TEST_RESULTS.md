# Validation — Report Ready 3.3

Checked locally on Windows with Python 3.11.9 and Node 24.18.0. Report prepared 14 October 2026. These results describe repository checks, not a production certification.

| Check | Result |
| --- | --- |
| Backend suite (`python -m pytest -q`) | 93 passed, 4 skipped |
| Frontend component suite (`npm test`) | 18 passed across 2 files |
| TypeScript and Vite production build | Passed; bundled interface rebuilt |
| Alembic schema/model alignment and downgrade | Passed within backend suite |
| Upgrade of populated Phase 2 SQLite data | Passed; job/usage foreign-key links preserved, downgrade also checked |
| Concurrent Free quota submissions | 8 simultaneous requests: 5 admitted, 3 rejected; failed job restores capacity |
| Billing removal | Legacy checkout, portal, and webhook routes no longer process requests; only Free plan is available |
| Team access and limits | Free team creation, single-use/expired/revoked invites, five-seat limit, member removal, shared templates, private documents, and pooled Free quota passed |
| Account deletion | Password/email confirmation, removal of owned files and records, owned-team cleanup, retained member accounts, and signed-out session passed locally |
| Privacy and terms | Corrected Report Ready pages are included in the frontend build; operator/legal review remains required |
| CI and readiness monitoring | Workflow added for PostgreSQL contention and disposable dump/restore, LibreOffice integration, frontend checks, and container build; health endpoint checks DB readiness; optional Sentry integration added |
| Donation UI | Top-right Donate button is visible and disabled pending a destination |

The suite retains the formatting, ownership, authentication, queue, PDF adapter, storage, and retention checks. Failed jobs release quota and successful completion does not double-count reservations. Existing subscription rows do not grant paid entitlement or longer retention.

Not exercised locally: PostgreSQL (the optional integration test was skipped because no test database was configured), the disposable CI dump/restore, real S3 deployment or bucket recovery, Windows launcher/Word COM, target-host LibreOffice rendering, production backup restoration, configured production Sentry alerts, or a user pilot. The new GitHub Actions workflow has not run because these changes have not been pushed. No live Render deployment was checked in this validation; an earlier check reported version 3.2.0, so verify the deployed version before relying on it. Docker is not installed locally, so the container image was not built here. Frontend tests use a simulated DOM; the local PDF end-to-end test was skipped without LibreOffice and synthetic CI conversion cannot certify real-document pagination.

One upstream Starlette/httpx test-client deprecation warning was reported; tests passed. jsdom reports that document navigation is unimplemented for an existing download test; actual browser downloads were not exercised here.

`TEST_RESULTS_ARCHIVE.md` contains historical results shipped in the input ZIP. The farming-report render and historical HTTP smoke test described there were not repeated in this Phase 3 run.
