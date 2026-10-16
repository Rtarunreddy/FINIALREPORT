# Hosted deployment — Report Ready 3.3

The hosted app runs without paid plans, checkout, subscriptions, or Stripe configuration. Users receive five formatting/PDF jobs per UTC calendar month. Free teams support up to five members and use their owner's shared five-job allowance. Members' personal jobs use their own Free allowance. Documents remain private to their uploader.

Legacy subscription records and database columns are retained only for schema compatibility and do not grant access. If any real subscriptions were created in an earlier deployment, cancel them with the payment provider directly; deploying this version cannot cancel recurring charges.

## Render deployment

The Render Blueprint in `render.yaml` provisions a Postgres database and a Docker web service with LibreOffice for PDF export. Before deploying, provide the following values in Render's environment settings:

- `REPORT_READY_S3_BUCKET`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` for durable S3-compatible file storage. Set `REPORT_READY_S3_ENDPOINT` for R2 or another compatible service.
- `REPORT_READY_PUBLIC_URL` set to the app's HTTPS URL.
- `REPORT_READY_SESSION_SECRET` generated and stored by Render; keep it stable across deploys.
- Optional Google OAuth credentials and a verified Resend sender for password recovery.
- Optional `SENTRY_DSN` for Sentry error monitoring. Configure it only after reviewing your Sentry project's data retention, access and privacy settings; default personal-identifying data is disabled in the SDK.

Keep `REPORT_READY_COOKIE_SECURE=true`. Never put credentials in source files, frontend variables, or chat. Keep the database and object-storage backups enabled and test restoring both together.

## Run locally on Windows

For the desktop app, run `start.bat`. For an account-based local service, install `backend\requirements-dev.txt`, set `REPORT_READY_LOCAL_MODE=0`, provide a random 48+ character `REPORT_READY_SESSION_SECRET`, then start Uvicorn from `backend`:

```powershell
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The app applies Alembic migrations on startup by default. Back up the database and stored files before upgrading an existing installation.

## Teams and quotas

- A user can own one team with up to five total seats, counting the owner and pending invitations.
- The owner's personal jobs and jobs submitted to the owner's team share one five-job monthly quota.
- Team members' personal jobs are charged to their own Free allowance.
- Failed/cancelled jobs release their reservation; successfully completed jobs count for that UTC month.
- Invitations are one-time, email-bound codes that expire after seven days. The owner shares each code privately; the app does not send invitation emails.
- Team membership shares templates and quota only. Uploaded files, outputs, and job history remain private.

## Donations

The top-right Donate button is intentionally disabled until the operator chooses and configures a donation destination. No payment provider or donation URL is currently integrated.

## Deployment verification limitations

Automated backend/frontend tests and the production frontend build verify repository behavior, not the hosted provider setup. CI exercises PostgreSQL migrations and quota contention against a disposable database, plus a synthetic LibreOffice conversion; it does not prove that a production snapshot restores or that real user documents render correctly on Render.

Before public launch, an operator must still verify the actual Render database and bucket configuration, encryption and backup policies, restore both from a production-like backup, verify OAuth/recovery email if enabled, check HTTPS/session behavior, test representative DOCX/PDF files on the deployed service, configure and exercise error monitoring, review the published privacy notice and terms, and run the documented pilot. Keep a dated record of who ran each check and its result. A successful health endpoint or CI run alone is not a production-readiness certification.
