# Version 3.2 (Phase 3: monetization)

- Added a server-side plan catalogue with provisional Free/Pro/Team limits.
- Added Stripe Checkout and customer portal routes, raw-body signature verification, transactional webhook receipts and current-subscription synchronization. New purchases are disabled by default.
- Reserved monthly quota atomically at enqueue; failed jobs release quota, worker completion does not double-charge, and the UI offers an upgrade action.
- Added one owned Team workspace, five-seat membership including pending invites, email-bound one-time invitation codes, revoke/remove controls and shared template publishing.
- Added the Plans & team panel and workspace selection; document ownership stays private.
- Added migration 0003 and preserved existing foreign-key links during SQLite batch upgrades.
- Paid retention now checks current entitlements; pywin32 moved to optional desktop requirements.
- Added Phase 3 setup, Phase 1–4 review and updated validation notes. Stripe sandbox/production deployment and Phase 4 work remain outstanding.

# Version 3.1 (Phase 2: product)

- Job queue: formatting and PDF export run as database-backed jobs (queued, running, done, failed) claimed atomically by worker threads or by a separate `python -m app.worker` process. `POST .../apply` returns at once with a job id; `GET /api/jobs/{id}` reports progress. Stuck jobs are failed after 15 minutes, a user can have at most 5 active jobs, and deleting an upload cancels its queued jobs.
- One-click formatting: `apply` needs no body (built-in default) or accepts `templateId`. The web app formats right after upload by default; the choice is a remembered checkbox.
- Before and after: every formatted report includes a comparison of body fonts, sizes, alignment, line spacing, heading styles and page margins, with plain-language highlights such as "Different body fonts: 3 → 1".
- PDF export on the server with LibreOffice (private profile per conversion, timeout, content check). Microsoft Word remains a fallback on Windows. Identical export requests reuse the finished or in-progress PDF.
- `GET /api/jobs` lists recent jobs for the signed-in user. Migration 0002 adds the queue columns.
- Dockerfile with LibreOffice and metric-compatible fonts; `render.yaml` now deploys the Docker image.

# Version 3 (Phase 1: SaaS foundation)

- Accounts: email and password sign-up (scrypt hashes, signed HttpOnly session cookie, login throttling) and optional Google sign-in. The shared access password is gone.
- Database: SQLAlchemy models and an Alembic migration for users, teams, templates, documents, jobs, usage events, subscriptions and feedback. SQLite by default, Postgres through DATABASE_URL. Migrations run on startup.
- Ownership: every upload, output, report and template belongs to a user; other users receive 404. Templates are private per account and cannot be overwritten by another user.
- Storage: files live behind a storage interface (local folder or S3-compatible bucket) under opaque keys; original file names are kept only in the database.
- Retention: expiry is stored per document and depends on plan (24 hours free, 90 days paid by default). Expired files are deleted from storage and become unreachable immediately.
- History: each format run is stored as a job with its change report; format, learn and export actions are recorded as usage events.
- Backend split into routers (auth, documents, templates, jobs, misc). The Windows launcher runs in local single-user mode.
- Sign-in, account creation and sign-out screens in the web app.

# Version 2 changes

- Format table-cell text, nested tables, captions, title styles and picture paragraphs that the previous version skipped.
- Reset stray body indents and align headings while preserving real list numbering, bold/italic emphasis, hyperlinks and native equations.
- Fit inline pictures to the current section, column or cell. Keep image proportions and section orientation.
- Preserve table-header colors and merged cells; allow fixed-height rows to grow rather than clip text.
- Avoid duplicate added headers, footers and page numbers in linked sections or repeated formatting runs.
- Validate settings and uploads, reject invalid file identifiers and return clear errors for missing outputs or unsupported input.
- Verify actual body content and embedded asset bytes, not just counts.
- Learn a reference format through a separate upload without replacing the active report. Fix exact line-height handling.
- Add editable font, spacing, margin, page and heading settings, optional cleanup controls and reusable templates.
- Clear stale outputs after settings change; restore controls after failed uploads or network requests.
- Show the formatting plan and output summary accurately instead of calling a text summary a visual preview.
- Provide a single-window Windows launcher, isolated Python environment and prebuilt interface. Install dependencies only when setup is needed or requirements change.
- Make PDF conversion optional; improve Windows Word export cleanup and error handling.
- Add regression tests and fix the sample pipeline so it does not depend on a missing external image.
