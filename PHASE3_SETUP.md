# Phase 3 — billing, quotas and teams

This package adds monetization code to Phase 2. It does not enable payments, deploy the app, send invitations, or configure a Stripe account. Start with Stripe sandbox credentials. Keep live checkout disabled until the 20–50-user pilot and launch-readiness work are complete.

## Run locally

For the existing single-user desktop formatter, run `start.bat`. It remains quota-free and hides billing/team UI. The bundled frontend is already built.

To test accounts and Phase 3 on Windows PowerShell, from the extracted project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
$env:REPORT_READY_LOCAL_MODE='0'
$env:REPORT_READY_SESSION_SECRET = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$env:REPORT_READY_COOKIE_SECURE='false'
$env:REPORT_READY_PUBLIC_URL='http://127.0.0.1:8000'
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and register an account. Expand **Plans & team**. The `.env.example` file is a reference, not automatically loaded: set values in the shell or your host's environment settings. Keep a stable session secret on your hosted installation.

## Existing Phase 2 data

Back up your database and stored files together with the app stopped. Install updated requirements. Startup applies Alembic migration `0003`; the manual alternative is `cd backend` then `alembic upgrade head` with the correct `DATABASE_URL`. Migration adds a Checkout session pointer, webhook receipts, invitations and a team reference on jobs; it preserves existing accounts, templates, files and jobs. Existing completed-job usage in the current month counts toward the new limits.

For local storage, retain the entire `backend/data` directory, including the SQLite database and `files` tree. Do not copy legacy JSON files expecting automatic import. For hosted installations, keep using the same Postgres database and S3 bucket.

## Proposed plan rules — editable before launch

| Plan | Jobs per UTC calendar month | Seats | Retention for new files |
| --- | ---: | ---: | --- |
| Free | 5 | 1 | 24 hours |
| Pro | 100 | 1 | 90 days |
| Team | 500 pooled | 5 including owner | 90 days for active members |

Limits are defined in `backend/app/plans.py`. Prices are intentionally not invented: configure recurring Stripe Prices in your chosen currency and review the amount at Checkout. Team is a flat-price workspace, not per-seat metering. One Team subscription belongs to its owner account and provides one team; `subscriptions.owner_type` is `user`. The pre-existing team billing columns are reserved for future organization-owned billing.

Each format or PDF-export job costs one unit. A DOCX plus a PDF normally costs two. Queued and running jobs reserve quota; failed/cancelled jobs release it automatically. Successful jobs remain counted after files expire or are deleted. PDF requests that reuse an existing result do not consume another unit. Uploads, audits, learning a reference format and PDF-to-DOCX conversion are not charged in this phase; add separate abuse controls before public launch. The desktop launcher bypasses quotas; never enable local mode on a public service.

Team jobs use the owner's pool. Owner personal jobs use the same pool. A member's personal jobs use that member's own plan. Removing a member does not remove prior team usage. Retention is assigned when each file is created: subscription changes do not rewrite existing expiry dates or restore expired files. Paid access requires an active/trialing subscription with a future period end; past-due, unpaid, paused, incomplete, cancelled or expired subscriptions fall back to Free. There is no grace period in this implementation.

## Stripe sandbox setup

1. Create two recurring prices in Stripe sandbox, one for Pro and one for Team. Use one subscription item, fixed quantity 1. Do not enable editable quantity or unrelated products in the customer portal.
2. Set `STRIPE_SECRET_KEY`, `STRIPE_PRO_PRICE_ID`, `STRIPE_TEAM_PRICE_ID` and `REPORT_READY_PUBLIC_URL`. Never place secrets in frontend code or commit them.
3. Configure a **snapshot** webhook endpoint at `/api/billing/webhook` for `customer.subscription.created`, `customer.subscription.updated` and `customer.subscription.deleted`. Set its signing secret as `STRIPE_WEBHOOK_SECRET`.
4. For local testing, run `stripe listen --events customer.subscription.created,customer.subscription.updated,customer.subscription.deleted --forward-to localhost:8000/api/billing/webhook`. Use the signing secret printed by that listener.
5. Activate the Stripe customer portal. Restrict product changes to the two configured recurring Prices. Set immediate or period-end downgrade behavior deliberately; the app follows the actual subscription item and status.
6. Set `REPORT_READY_BILLING_ENABLED=true` **only in your sandbox deployment** and restart. Choose Pro or Team from the app. Existing subscribers use **Manage billing** for changes and cancellation.
7. Complete Stripe's sandbox checkout. The redirect itself never grants a plan. Signed webhooks synchronize `subscriptions`, and **Refresh plan & usage** displays the entitlement.
8. Test subscription renewal, upgrade, scheduled cancellation, completed cancellation, failed payment/recovery, duplicate events and delayed events. Verify that no card details enter your app.

The handler uses Stripe SDK signature verification on the raw request body with a five-minute tolerance. It records event IDs transactionally and retrieves current subscription state under a per-customer database lock, rather than trusting delayed event snapshots. Transient Stripe retrieval failures return a retryable response. Access to Checkout is off by default; portal access and webhook processing remain available when new purchases are disabled so existing subscriptions can still be managed.

No real Stripe API calls were made during development. Account eligibility, price configuration, portal behavior and real sandbox delivery still require testing with your account before live use. The code uses `stripe==14.4.1`.

## Teams and templates

After a Team sandbox subscription is active:

1. In the Personal workspace, create a team, then select it.
2. Enter a colleague's email and create an invitation. Copy the one-time code and share it privately yourself. The app does not send email.
3. The recipient registers/signs in using the invited email, pastes the code and clicks **Join team**. Possession of the private code and the matching account email are both required. Codes are hashed in the database, expire after seven days and work once.
4. The owner uses **Share current format with team** to copy the selected settings. Members choose shared formats from the normal template list. Only the owner can publish/delete shared templates or invite/remove other members; members can leave through the API.
5. Pending invites reserve seats. Revoke an invitation or remove a member to free a seat. Reinviting the same email replaces the old code.

Uploaded documents, outputs and job history remain private to their uploader. Team membership shares templates and quota, not document content. A team whose owner loses the Team plan cannot start team jobs or use shared templates. The owner can still review membership and revoke invitations. There is no owner transfer, team deletion or admin-role editor in this phase.

## API summary

- `GET /api/billing/plans`: public catalogue, no secrets or payment details.
- `GET /api/billing/status?team_id=...`: authenticated allowance and usage.
- `POST /api/billing/checkout` with `{"plan":"pro"}` or `{"plan":"team"}`.
- `POST /api/billing/portal`: current user's portal URL.
- `POST /api/billing/webhook`: Stripe-signed endpoint, no browser login.
- `GET/POST /api/teams`: list memberships/create one owned team.
- `GET /api/teams/{id}/members`; `DELETE /api/teams/{id}/members/{user_id}`.
- `GET/POST /api/teams/{id}/invites`; `DELETE /api/teams/{id}/invites/{invite_id}`.
- `POST /api/teams/accept` with `{"token":"..."}`.
- `GET/POST /api/teams/{id}/profiles`; `DELETE /api/teams/{id}/profiles/{profile_id}`.
- Formatting accepts optional `teamId`; shared `templateId` requires the matching team context. Every job still requires ownership of its source document.

## Validation commands

```text
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm test
npm run build
```

See `TEST_RESULTS.md` for this build's results and `PHASE_REVIEW.md` for remaining launch work.

Official implementation references: https://docs.stripe.com/webhooks , https://docs.stripe.com/api/checkout/sessions/create?lang=python , https://docs.stripe.com/api/customer_portal/sessions/create?lang=python .
