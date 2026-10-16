# Report Ready — Phase 1–4 review

Review date: 14 October 2026. This is a code review and local test report, not a production-readiness certification. Paid checkout and subscription support have been removed; the hosted deployment still requires operational verification.

| Roadmap item | Code status | Evidence / remaining work |
| --- | --- | --- |
| 1. SQLAlchemy/Alembic; replace file locks | Present | Database models and three migrations; templates/feedback use transactions. New quota operations use database locks. |
| 2. Email login and Google OAuth | Present | Password login, signed cookies, Google callback and ownership dependencies. Production OAuth configuration remains external. Email verification, password reset, session revocation and distributed rate limits remain launch-hardening work. |
| 3. Object storage and ownership | Present | Local/S3 put/read/delete abstraction; ownership checked for uploads, outputs and jobs. Existing S3 tests use a fake service. |
| 4. Plan retention/history | Present in backend | Per-file `expires_at`; 24h Free retention and cleanup. `/api/jobs` exposes job history, but no complete history browser in UI. |
| 5. Router split and cross-user tests | Present | Auth, documents, templates, jobs, plans, and teams routers. Protected route and ownership tests. |
| 6. One-click default flow | Present | Auto-format on upload; advanced format and cleanup controls collapsed. |
| 7. Worker queue and polling | Present | Database-backed worker claim, status polling, standalone worker mode. Batch upload UI is still future work. |
| 8. Server PDF export | Present | LibreOffice headless backend and Docker installation. Hosted requirements exclude pywin32; desktop fallback is a separate requirements file. Rendering fidelity still needs target-host verification. |
| 9. Before/after summary | Present | Summary generation and frontend comparison rows; not a full page-render comparison. |
| 10. Payments | Removed | No checkout, customer portal, Stripe webhook, paid plans, or Stripe credentials are used. Existing legacy subscription rows do not grant paid entitlements. |
| 11. Job quotas | Present | Atomic five-job Free allowance per UTC calendar month; failed-job release; structured 402 with usage link. Team-workspace jobs share the owner's allowance. |
| 12. Teams, invites, shared templates | Present on Free | Five seats including owner; expiry/revocation/single-use invites; owner template publishing; workspace selector. Invitation codes are manually shared, not emailed. |
| 13. Privacy/terms, encryption, data deletion | Partially implemented | Operator-specific Privacy Notice and Terms are published at `/privacy.html` and `/terms.html`; users can delete their account, live files, jobs, templates and owned team. The policies still need operator/legal review. Verify provider encryption, backup lifecycle and restoration; provider backups/logs are not immediately erased by account deletion. |
| 14. Monitoring, analytics, CI | Partially implemented | GitHub Actions is configured to run backend, PostgreSQL contention and disposable-database dump/restore, LibreOffice integration, frontend, and container-build checks. `/api/health` checks database readiness. Optional Sentry reporting is wired but must be configured and an alert tested in production. No analytics dashboard is supplied. |
| 15. User pilot | Not run | Recruit users, collect formatting failures and retention/activation metrics, and check support workload before public launch. |

## Priority before launch

1. Run the new CI workflow and verify its PostgreSQL, disposable dump/restore, and Docker jobs pass. Separately test restoring the actual production database and bucket together; CI does not use production backups.
2. Have the Privacy Notice and Terms reviewed for the operator's specific legal obligations. Verify provider encryption, backup lifecycle and account-erasure behavior, including retained backups/logs.
3. Configure Sentry only after reviewing its privacy settings, then trigger and confirm a test alert. Verify OAuth/recovery email if enabled and confirm host network/file access is appropriately restricted.
4. Validate representative real reports on the deployed Render service. Check equations, tables, diagrams, headings, preservation and export fidelity; the CI PDF test uses synthetic content.
5. Run a pilot with real users and verify support workload, retention, and document success rates before declaring the service launch-ready.

## Pilot acceptance checklist

- [ ] Document success rate and reasons for manual intervention measured.
- [ ] Cross-user files remain inaccessible; removed team members lose template access.
- [ ] Failed jobs do not consume quota; simultaneous submissions cannot exceed it.
- [ ] Retention expiry, backups and account erasure verified on the hosting provider.
- [ ] Support/contact details and privacy/terms published and reviewed for the operator's legal obligations.
- [ ] Observability and CI pass; database restoration tested.
- [ ] 20–50 pilot users have tried the workflow; launch decision recorded.
