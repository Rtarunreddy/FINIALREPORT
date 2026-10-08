"""Phase 3 integration contracts. Stripe transport is mocked; signatures are real."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from app.db_models import BillingEvent, Job, Subscription, TeamInvite, UsageEvent, User, utcnow
from app import stripe_client
from conftest import sign_up
from test_infra import docx_bytes


def grant(app, email, plan="team", status="active", days=30):
    with app.state.session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        db.add(Subscription(owner_type="user", owner_id=user.id, stripe_sub_id="sub_"+user.id, plan=plan, status=status, current_period_end=utcnow()+timedelta(days=days)))
        db.commit(); return user.id


def upload(c):
    return c.post('/api/uploads', files={'file': ('r.docx', docx_bytes())}).json()['id']


def signed(c, event, timestamp=None, secret="whsec_test"):
    stamp = int(time.time()) if timestamp is None else timestamp
    raw = json.dumps(event).encode()
    signature = hmac.new(secret.encode(), str(stamp).encode()+b'.'+raw, hashlib.sha256).hexdigest()
    return c.post('/api/billing/webhook', content=raw, headers={'stripe-signature': f't={stamp},v1={signature}', 'content-type': 'application/json'})


@pytest.fixture
def billing(cloud, monkeypatch):
    s = cloud.app.state.settings
    s.billing_enabled = True; s.stripe_secret_key = 'sk_test_fake'; s.stripe_webhook_secret = 'whsec_test'
    s.stripe_pro_price = 'price_pro'; s.stripe_team_price = 'price_team'
    c = sign_up(cloud.app)
    with cloud.app.state.session_factory() as db:
        u = db.scalar(select(User)); u.stripe_customer_id = 'cus_a'; db.commit()
    api = Mock()
    api.v1.checkout.sessions.create.return_value = SimpleNamespace(id='cs_1', url='https://checkout.stripe.com/test')
    api.v1.checkout.sessions.retrieve.return_value = SimpleNamespace(id='cs_1', status='open', url='https://checkout.stripe.com/test', metadata={'plan': 'pro'})
    api.v1.billing_portal.sessions.create.return_value = SimpleNamespace(url='https://billing.stripe.com/test')
    api.v1.subscriptions.retrieve.return_value = {'id': 'sub_a', 'customer': 'cus_a', 'status': 'active', 'items': {'data': [{'price': {'id': 'price_pro'}, 'current_period_end': int(time.time())+86400}]}}
    monkeypatch.setattr(stripe_client, 'client', lambda s: api)
    return c, api


def event(ident='evt_1', kind='customer.subscription.updated'):
    return {'id': ident, 'type': kind, 'livemode': False, 'data': {'object': {'id': 'sub_a', 'customer': 'cus_a', 'status': 'active'}}}


def test_billing_disabled_by_default(cloud):
    c = sign_up(cloud.app)
    assert c.get('/api/billing/plans').json()['billingEnabled'] is False
    assert c.post('/api/billing/checkout', json={'plan': 'pro'}).status_code == 503


def test_checkout_price_allowlist_reuse_and_portal(billing):
    c, api = billing
    assert c.post('/api/billing/checkout', json={'plan': 'arbitrary_price'}).status_code == 400
    for _ in range(2): assert c.post('/api/billing/checkout', json={'plan': 'pro'}).status_code == 200
    assert api.v1.checkout.sessions.create.call_count == 1
    payload = api.v1.checkout.sessions.create.call_args.args[0]
    assert payload['line_items'] == [{'price': 'price_pro', 'quantity': 1}]
    assert payload['customer'] == 'cus_a'
    assert c.post('/api/billing/portal').status_code == 200
    assert api.v1.billing_portal.sessions.create.call_args.args[0]['customer'] == 'cus_a'
    assert c.get('/api/billing/status').json()['plan']['id'] == 'free'  # redirect creates no entitlement


def test_customer_created_before_checkout(billing):
    c, api = billing
    with c.app.state.session_factory() as db:
        db.scalar(select(User)).stripe_customer_id = None; db.commit()
    api.v1.customers.create.return_value = SimpleNamespace(id='cus_new')
    assert c.post('/api/billing/checkout', json={'plan': 'pro'}).status_code == 200
    assert api.v1.checkout.sessions.create.call_args.args[0]['customer'] == 'cus_new'


def test_webhook_invalid_and_expired_signatures(billing):
    c, api = billing
    assert signed(c, event(), secret='wrong').status_code == 400
    assert signed(c, event(), timestamp=int(time.time())-400).status_code == 400
    assert c.post('/api/billing/webhook', content=b'{}').status_code == 400
    api.v1.subscriptions.retrieve.assert_not_called()


def test_webhook_duplicate_and_out_of_order(billing):
    c, api = billing
    assert signed(c, event()).status_code == 200
    assert c.get('/api/billing/status').json()['plan']['id'] == 'pro'
    assert signed(c, event()).status_code == 200
    assert api.v1.subscriptions.retrieve.call_count == 1
    api.v1.subscriptions.retrieve.return_value['status'] = 'canceled'
    # Stale active payload cannot restore access: handler reads current Stripe state.
    assert signed(c, event('evt_old')).status_code == 200
    assert c.get('/api/billing/status').json()['plan']['id'] == 'free'
    with c.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(BillingEvent)) == 2
        assert db.scalar(select(Subscription)).status == 'canceled'


@pytest.mark.parametrize('status', ['past_due', 'unpaid', 'incomplete', 'paused', 'canceled'])
def test_nonactive_subscription_has_no_paid_entitlement(billing, status):
    c, api = billing; api.v1.subscriptions.retrieve.return_value['status'] = status
    assert signed(c, event()).status_code == 200
    assert c.get('/api/billing/status').json()['plan']['id'] == 'free'


def test_webhook_unknown_price_and_customer_mismatch(billing):
    c, api = billing
    api.v1.subscriptions.retrieve.return_value['items']['data'][0]['price']['id'] = 'price_unknown'
    assert signed(c, event()).status_code == 200
    assert c.get('/api/billing/status').json()['plan']['id'] == 'free'
    api.v1.subscriptions.retrieve.return_value['customer'] = 'cus_other'
    assert signed(c, event('evt_2')).status_code == 400


def test_webhook_retry_on_transport_failure(billing):
    import stripe
    c, api = billing; api.v1.subscriptions.retrieve.side_effect = stripe.APIConnectionError('offline')
    assert signed(c, event()).status_code == 503
    with c.app.state.session_factory() as db: assert db.get(BillingEvent, 'evt_1') is None
    api.v1.subscriptions.retrieve.side_effect = None
    assert signed(c, event()).status_code == 200


def test_existing_subscription_uses_portal(billing):
    c, api = billing; signed(c, event())
    assert c.post('/api/billing/checkout', json={'plan': 'team'}).status_code == 409
    api.v1.checkout.sessions.create.assert_not_called()


def test_expired_subscription_reverts_to_free(cloud):
    c = sign_up(cloud.app); grant(cloud.app, 'a@example.com', 'pro', days=-1)
    assert c.get('/api/billing/status').json()['plan']['id'] == 'free'
    assert c.get('/api/auth/status').json()['retentionHours'] == 24


def test_quota_atomic_reservations_and_failed_refund(cloud):
    c = sign_up(cloud.app); doc = upload(c)
    cloud.app.state.settings.max_active_jobs = 100
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: c.post(f'/api/uploads/{doc}/apply', json={}), range(8)))
    assert sorted(r.status_code for r in results) == [202]*5 + [402]*3
    assert c.get('/api/billing/status').json()['used'] == 5
    failed = next(r.json()['id'] for r in results if r.status_code == 202)
    with cloud.app.state.session_factory() as db:
        db.get(Job, failed).status = 'failed'; db.commit()
    assert c.get('/api/billing/status').json()['remaining'] == 1
    assert c.post(f'/api/uploads/{doc}/apply', json={}).status_code == 202
    cloud.app.state.runner.run_pending()
    assert c.get('/api/billing/status').json()['used'] == 5  # completion does not double-charge


def test_quota_month_boundary_and_local_bypass(cloud, client):
    c = sign_up(cloud.app); doc = upload(c)
    assert c.post(f'/api/uploads/{doc}/apply', json={}).status_code == 202
    with cloud.app.state.session_factory() as db:
        db.scalar(select(UsageEvent)).created_at = utcnow().replace(day=1)-timedelta(days=1); db.commit()
    assert c.get('/api/billing/status').json()['used'] == 0
    doc = upload(client); client.app.state.settings.max_active_jobs = 100
    for _ in range(7): assert client.post(f'/api/uploads/{doc}/apply', json={}).status_code == 202


@pytest.fixture
def team(cloud):
    owner = sign_up(cloud.app); grant(cloud.app, 'a@example.com')
    member = sign_up(cloud.app, 'b@example.com')
    outsider = sign_up(cloud.app, 'c@example.com')
    response = owner.post('/api/teams', json={'name': 'Lab'})
    assert response.status_code == 201
    tid = response.json()['id']
    token = owner.post(f'/api/teams/{tid}/invites', json={'email': 'b@example.com'}).json()['token']
    assert outsider.post('/api/teams/accept', json={'token': token}).status_code == 403
    assert member.post('/api/teams/accept', json={'token': token}).status_code == 200
    assert member.post('/api/teams/accept', json={'token': token}).status_code == 403
    return owner, member, outsider, tid


def test_team_access_shared_templates_and_private_documents(team):
    owner, member, outsider, tid = team
    profile = owner.get('/api/profiles').json()[0]
    saved = owner.post(f'/api/teams/{tid}/profiles', json=profile)
    assert saved.status_code == 200
    profile_id = saved.json()['id']
    assert member.get(f'/api/teams/{tid}/profiles').json()[0]['id'] == profile_id
    assert outsider.get(f'/api/teams/{tid}/profiles').status_code == 404
    assert member.post(f'/api/teams/{tid}/profiles', json=profile).status_code == 403
    doc = upload(member)
    assert member.post(f'/api/uploads/{doc}/apply', json={'templateId': profile_id}).status_code == 403
    result = member.post(f'/api/uploads/{doc}/apply', json={'templateId': profile_id, 'teamId': tid})
    assert result.status_code == 202
    assert owner.get('/api/billing/status').json()['used'] == 1
    assert member.get('/api/billing/status').json()['used'] == 0
    assert owner.get(f'/api/uploads/{doc}').status_code == 404
    assert owner.get(f"/api/jobs/{result.json()['id']}").status_code == 404
    member.app.state.runner.run_pending()
    assert owner.get('/api/billing/status').json()['used'] == 1
    assert member.get('/api/auth/status').json()['retentionHours'] == 24*90
    assert owner.post('/api/teams', json={'name': 'Second'}).status_code == 409


def test_revocation_expiry_and_seat_limit(team):
    owner, member, outsider, tid = team
    for i in range(3):
        assert owner.post(f'/api/teams/{tid}/invites', json={'email': f'{i}@example.com'}).status_code == 201
    assert owner.post(f'/api/teams/{tid}/invites', json={'email': 'full@example.com'}).status_code == 409
    invitations = owner.get(f'/api/teams/{tid}/invites').json()
    assert owner.delete(f"/api/teams/{tid}/invites/{invitations[0]['id']}").status_code == 200
    invite = owner.post(f'/api/teams/{tid}/invites', json={'email': 'c@example.com'}).json()
    with owner.app.state.session_factory() as db:
        db.get(TeamInvite, invite['id']).expires_at = utcnow()-timedelta(seconds=1); db.commit()
    assert outsider.post('/api/teams/accept', json={'token': invite['token']}).status_code == 403
    invite = owner.post(f'/api/teams/{tid}/invites', json={'email': 'c@example.com'}).json()
    owner.delete(f"/api/teams/{tid}/invites/{invite['id']}")
    assert outsider.post('/api/teams/accept', json={'token': invite['token']}).status_code == 404


def test_removed_member_and_downgraded_team(team):
    owner, member, outsider, tid = team
    members = owner.get(f'/api/teams/{tid}/members').json()
    member_id = next(m['id'] for m in members if m['role'] == 'member')
    assert outsider.delete(f'/api/teams/{tid}/members/{member_id}').status_code == 404
    assert owner.delete(f'/api/teams/{tid}/members/{member_id}').status_code == 200
    assert member.get(f'/api/teams/{tid}/profiles').status_code == 404
    with owner.app.state.session_factory() as db:
        db.scalar(select(Subscription)).status = 'canceled'; db.commit()
    assert owner.get(f'/api/teams/{tid}/profiles').status_code == 403
    assert owner.get(f'/api/teams/{tid}/members').status_code == 200
    assert owner.post(f'/api/teams/{tid}/invites', json={'email': 'new@example.com'}).status_code == 403


def test_pdf_quota_reservation_and_reuse(cloud, monkeypatch):
    from app import pdf_export
    c = sign_up(cloud.app); doc = upload(c)
    job = c.post(f'/api/uploads/{doc}/apply', json={}).json()
    cloud.app.state.runner.run_pending()
    out = c.get('/api/jobs/'+job['id']).json()['outputId']
    monkeypatch.setattr(pdf_export, 'available', lambda s: True)
    first = c.post(f'/api/outputs/{out}/pdf')
    second = c.post(f'/api/outputs/{out}/pdf')
    assert first.status_code == second.status_code == 202
    assert first.json()['id'] == second.json()['id']
    assert c.get('/api/billing/status').json()['used'] == 2


def test_team_quota_is_shared_with_owner_personal_jobs(team, monkeypatch):
    from app.plans import PLANS, Plan
    owner, member, outsider, tid = team
    monkeypatch.setitem(PLANS, 'team', Plan('team', 'Team', 2, 5))
    a, b = upload(owner), upload(member)
    assert owner.post(f'/api/uploads/{a}/apply', json={}).status_code == 202
    assert member.post(f'/api/uploads/{b}/apply', json={'teamId': tid}).status_code == 202
    assert member.post(f'/api/uploads/{b}/apply', json={'teamId': tid}).status_code == 402
    assert owner.post(f'/api/uploads/{a}/apply', json={}).status_code == 402
    assert outsider.get('/api/billing/status', params={'team_id': tid}).status_code == 404


def test_switching_checkout_plan_expires_old_session(billing):
    c, api = billing
    assert c.post('/api/billing/checkout', json={'plan': 'pro'}).status_code == 200
    assert c.post('/api/billing/checkout', json={'plan': 'team'}).status_code == 200
    api.v1.checkout.sessions.expire.assert_called_once_with('cs_1')
    assert api.v1.checkout.sessions.create.call_args.args[0]['line_items'][0]['price'] == 'price_team'


def test_phase2_upgrade_preserves_job_usage_links(tmp_path):
    from alembic import command
    from app.db import alembic_config, make_engine
    from sqlalchemy import text
    url = f'sqlite:///{tmp_path / "upgrade.db"}'
    config = alembic_config(url)
    command.upgrade(config, '0002')
    engine = make_engine(url)
    with engine.begin() as con:
        con.execute(text("INSERT INTO users (id,email,plan_id,created_at) VALUES ('user1','old@example.com','free',CURRENT_TIMESTAMP)"))
        con.execute(text("INSERT INTO jobs (id,user_id,kind,status,created_at) VALUES ('job1','user1','format','done',CURRENT_TIMESTAMP)"))
        con.execute(text("INSERT INTO usage_events (user_id,event,job_id,created_at) VALUES ('user1','format','job1',CURRENT_TIMESTAMP)"))
    command.upgrade(config, 'head')
    command.check(config)
    with engine.connect() as con:
        assert con.execute(text('SELECT job_id FROM usage_events')).scalar_one() == 'job1'
        assert con.execute(text('SELECT email FROM users')).scalar_one() == 'old@example.com'
        assert not con.execute(text('PRAGMA foreign_key_check')).all()
    command.downgrade(config, '0002')
    with engine.connect() as con:
        assert con.execute(text('SELECT job_id FROM usage_events')).scalar_one() == 'job1'
    engine.dispose()
