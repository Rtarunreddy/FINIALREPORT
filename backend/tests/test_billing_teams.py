"""Free-plan quotas and team integration contracts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from app.db_models import Job, Subscription, TeamInvite, UsageEvent, User, utcnow
from conftest import sign_up
from test_infra import docx_bytes


def upload(c):
    return c.post('/api/uploads', files={'file': ('r.docx', docx_bytes())}).json()['id']


def test_paid_billing_routes_are_removed_and_only_free_plan_is_available(cloud):
    c = sign_up(cloud.app)
    assert c.get('/api/plans').json()['plans'] == [{'id': 'free', 'name': 'Free', 'monthly_jobs': 5, 'seats': 5}]
    assert c.get('/api/plans/usage').json()['plan']['id'] == 'free'
    for path in ('/api/billing/plans', '/api/billing/status'):
        assert c.get(path).status_code == 404
    for path in ('/api/billing/checkout', '/api/billing/portal', '/api/billing/webhook'):
        assert c.post(path).status_code in (404, 405)


def test_legacy_subscription_cannot_grant_paid_access(cloud):
    c = sign_up(cloud.app)
    with cloud.app.state.session_factory() as db:
        user = db.scalar(select(User))
        db.add(Subscription(owner_type="user", owner_id=user.id, stripe_sub_id="legacy-sub", plan="pro", status="active", current_period_end=utcnow()+timedelta(days=30)))
        db.commit()
    assert c.get('/api/plans/usage').json()['plan']['id'] == 'free'
    assert c.get('/api/auth/status').json()['retentionHours'] == 24


def test_quota_atomic_reservations_and_failed_refund(cloud):
    c = sign_up(cloud.app); doc = upload(c)
    cloud.app.state.settings.max_active_jobs = 100
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: c.post(f'/api/uploads/{doc}/apply', json={}), range(8)))
    assert sorted(r.status_code for r in results) == [202]*5 + [402]*3
    assert c.get('/api/plans/usage').json()['used'] == 5
    failed = next(r.json()['id'] for r in results if r.status_code == 202)
    with cloud.app.state.session_factory() as db:
        db.get(Job, failed).status = 'failed'; db.commit()
    assert c.get('/api/plans/usage').json()['remaining'] == 1
    assert c.post(f'/api/uploads/{doc}/apply', json={}).status_code == 202
    cloud.app.state.runner.run_pending()
    assert c.get('/api/plans/usage').json()['used'] == 5  # completion does not double-charge


def test_quota_month_boundary_and_local_bypass(cloud, client):
    c = sign_up(cloud.app); doc = upload(c)
    assert c.post(f'/api/uploads/{doc}/apply', json={}).status_code == 202
    with cloud.app.state.session_factory() as db:
        db.scalar(select(UsageEvent)).created_at = utcnow().replace(day=1)-timedelta(days=1); db.commit()
    assert c.get('/api/plans/usage').json()['used'] == 0
    doc = upload(client); client.app.state.settings.max_active_jobs = 100
    for _ in range(7): assert client.post(f'/api/uploads/{doc}/apply', json={}).status_code == 202


@pytest.fixture
def team(cloud):
    owner = sign_up(cloud.app)
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
    assert owner.get('/api/plans/usage').json()['used'] == 1
    assert member.get('/api/plans/usage').json()['used'] == 0
    assert owner.get(f'/api/uploads/{doc}').status_code == 404
    assert owner.get(f"/api/jobs/{result.json()['id']}").status_code == 404
    member.app.state.runner.run_pending()
    assert owner.get('/api/plans/usage').json()['used'] == 1
    assert member.get('/api/auth/status').json()['retentionHours'] == 24
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


def test_removed_member_does_not_disable_free_team(team):
    owner, member, outsider, tid = team
    members = owner.get(f'/api/teams/{tid}/members').json()
    member_id = next(m['id'] for m in members if m['role'] == 'member')
    assert outsider.delete(f'/api/teams/{tid}/members/{member_id}').status_code == 404
    assert owner.delete(f'/api/teams/{tid}/members/{member_id}').status_code == 200
    assert member.get(f'/api/teams/{tid}/profiles').status_code == 404
    assert owner.get(f'/api/teams/{tid}/profiles').status_code == 200
    assert owner.get(f'/api/teams/{tid}/members').status_code == 200
    assert owner.post(f'/api/teams/{tid}/invites', json={'email': 'new@example.com'}).status_code == 201


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
    assert c.get('/api/plans/usage').json()['used'] == 2


def test_team_quota_is_shared_with_owner_personal_jobs(team, monkeypatch):
    from app.plans import PLANS, Plan
    owner, member, outsider, tid = team
    monkeypatch.setitem(PLANS, 'free', Plan('free', 'Free', 2, 5))
    a, b = upload(owner), upload(member)
    assert owner.post(f'/api/uploads/{a}/apply', json={}).status_code == 202
    assert member.post(f'/api/uploads/{b}/apply', json={'teamId': tid}).status_code == 202
    assert member.post(f'/api/uploads/{b}/apply', json={'teamId': tid}).status_code == 402
    assert owner.post(f'/api/uploads/{a}/apply', json={}).status_code == 402
    assert outsider.get('/api/plans/usage', params={'team_id': tid}).status_code == 404


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
