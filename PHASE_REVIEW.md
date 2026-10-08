# Report Ready — Phase 1–4 review

Review date: 8 October 2026. This is a code review and local test report, not a production-readiness certification. Phase 3 is implemented in this package; live billing has not been enabled.

| Roadmap item | Code status | Evidence / remaining work |
| --- | --- | --- |
| 1. SQLAlchemy/Alembic; replace file locks | Present | Database models and three migrations; templates/feedback use transactions. New quota operations use database locks. |
| 2. Email login and Google OAuth | Present | Password login, signed cookies, Google callback and ownership dependencies. Production OAuth configuration remains external. Email verification, password reset, session revocation and distributed rate limits remain launch-hardening work. |
| 3. Object storage and ownership | Present | Local/S3 put/read/delete abstraction; ownership checked for uploads, outputs and jobs. Existing S3 tests use a fake service. |
| 4. Plan retention/history | Present in backend | Per-file `expires_at`; 24h Free and 90-day paid default; cleanup. Phase 3 checks current subscription entitlement. No complete history browser in UI yet; `/api/jobs` exposes job history. |
| 5. Router split and cross-user tests | Present | Auth, documents, templates, jobs; new billing/teams routers. Protected route and ownership tests. |
| 6. One-click default flow | Present | Auto-format on upload; advanced format and cleanup controls collapsed. |
| 7. Worker queue and polling | Present | Database-backed worker claim, status polling, standalone worker mode. Batch upload UI is still future work. |
| 8. Server PDF export | Present | LibreOffice headless backend and Docker installation. Hosted requirements exclude pywin32; desktop fallback is a separate requirements file. Rendering fidelity still needs target-host verification. |
| 9. Before/after summary | Present | Summary generation and frontend comparison rows; not a full page-render comparison. |
| 10. Stripe billing | Added in Phase 3 | Checkout, portal, verified/idempotent webhook receipts, subscription synchronization, fixed server-side price map. Sandbox account tests still needed. |
| 11. Job quotas and upgrade prompt | Added in Phase 3 | Atomic usage reservations; failed-job release; structured 402 with UI upgrade link; pooled team quota. Calendar-month policy documented. |
| 12. Teams, invites, shared templates | Added in Phase 3 | Five seats including owner; expiry/revocation/single-use invites; owner template publishing; workspace selector. Invitation codes are manually shared, not emailed. |
| 13. Privacy/terms, encryption, data deletion | Not implemented | Write operator-specific policies; implement account erasure including files, jobs, memberships and subscription lifecycle. Configure and verify encrypted database, object storage and backups. Ordinary upload deletion is not account erasure. |
| 14. Monitoring, analytics, CI | Not complete | Existing logging, usage records and automated tests are present. No production error-monitoring integration, analytics dashboard or CI workflow supplied. The older “26 tests” estimate is outdated; see current results. |
| 15. 20–50-user pilot | Not run | Recruit users, collect formatting failures and retention/activation metrics, check support workload and willingness to pay before enabling live billing. |

## Priority before launch

1. Run actual Stripe sandbox checkout/portal/webhook tests, including renewal and cancellation, with your account's approved prices.
2. Verify Postgres under concurrent quota/invitation traffic and run the migration against a restored Phase 2 production snapshot. SQLite migration and concurrent quota tests pass locally; Postgres integration was not exercised here.
3. Complete privacy/terms/account erasure, configure encryption and backup recovery, and prevent paid-account deletion from leaving an active billable Stripe subscription.
4. Add CI for backend/frontend checks, production monitoring, and abuse controls for uploads, reference-learning, conversion and registration. Sandbox LibreOffice and restrict outbound/file access as appropriate to the deployment.
5. Pilot with 20–50 users using real university reports and reference templates. Check equations, tables, diagrams, headings, preservation and export fidelity; do not assume every document formats correctly.
6. Confirm pricing and limits. Current 5/100/500 quotas and five Team seats are provisional defaults, not validated business decisions.

## Pilot acceptance checklist

- [ ] Document success rate and reasons for manual intervention measured.
- [ ] Cross-user files remain inaccessible; removed team members lose template access.
- [ ] Failed jobs do not consume quota; simultaneous submissions cannot exceed it.
- [ ] Signed subscription events update plan state; invalid signatures rejected.
- [ ] Renewal, payment failure/recovery and cancellation match the chosen policy.
- [ ] Retention expiry, backups and account erasure verified on the hosting provider.
- [ ] Support/contact details, privacy/terms and billing/refund policy published.
- [ ] Observability and CI pass; database restoration tested.
- [ ] 20–50 pilot users have tried the workflow; launch decision recorded.
- [ ] Only then configure live keys/prices and enable new purchases.
