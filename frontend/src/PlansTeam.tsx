import {useEffect, useRef, useState} from 'react';

type Plan = {id: string; name: string; monthly_jobs: number; seats: number};
type Status = {plan: Plan; used: number; remaining: number; portalAvailable: boolean};
type Team = {id: string; name: string; role: string; active: boolean};
type Member = {id: string; email: string; role: string};
type Invite = {id: string; email: string; expiresAt: string};
async function api<T>(path: string, value?: unknown, method = 'POST'): Promise<T> {
  const r = await fetch('/api' + path, value === undefined ? undefined : {method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
  const data = await r.json();
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Please check the details and try again.');
  return data;
}

export function PlansTeam({workspace, onWorkspace, profile, onTemplatesChanged, refreshKey, disabled}: {
  workspace: string; onWorkspace: (id: string) => void; profile: unknown; onTemplatesChanged: () => void; refreshKey: string; disabled: boolean;
}) {
  const [catalog, setCatalog] = useState<{plans: Plan[]; billingEnabled: boolean} | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [shared, setShared] = useState<{id: string; name: string}[]>([]);
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [token, setToken] = useState('');
  const [code, setCode] = useState(''); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  const loadGeneration = useRef(0);
  const team = teams.find(t => t.id === workspace);
  async function reload() {
    const generation = ++loadGeneration.current;
    const [c, t] = await Promise.all([api<{plans: Plan[]; billingEnabled: boolean}>('/billing/plans'), api<Team[]>('/teams')]);
    const selected = t.find(x => x.id === workspace);
    const s = await api<Status>('/billing/status' + (selected?.active ? '?team_id=' + encodeURIComponent(workspace) : ''));
    const [m, i, p] = workspace && selected ? await Promise.all([
      api<Member[]>(`/teams/${workspace}/members`),
      selected.role === 'owner' ? api<Invite[]>(`/teams/${workspace}/invites`) : Promise.resolve([]),
      selected.active ? api<{id: string; name: string}[]>(`/teams/${workspace}/profiles`) : Promise.resolve([]),
    ]) : [[], [], []];
    if (generation !== loadGeneration.current) return;
    setCatalog(c); setStatus(s); setTeams(t); setMembers(m); setInvites(i); setShared(p);
    if (workspace && !selected) { onWorkspace(''); setMessage('Team access changed. Switched to your personal workspace.'); }
    else if (selected && !selected.active) setMessage('This team subscription is inactive. Choose Personal for new jobs.');
  }
  useEffect(() => { void reload().catch(e => setMessage(e.message)); return () => {loadGeneration.current++;}; }, [workspace, refreshKey]);
  async function act(fn: () => Promise<void>) {
    if (busy || disabled) return;
    setBusy(true); setMessage('');
    try { await fn(); await reload(); } catch (e) { setMessage(e instanceof Error ? e.message : 'Please try again.'); }
    finally { setBusy(false); }
  }
  async function redirect(path: string, body: unknown) {
    const {url} = await api<{url: string}>(path, body);
    const target = new URL(url);
    if (target.protocol !== 'https:' || !['checkout.stripe.com', 'billing.stripe.com'].includes(target.hostname)) throw new Error('Unexpected billing address.');
    window.location.assign(url);
  }
  return <details id="plans" className="panel plans-panel" open={window.location.hash === '#plans' || undefined}>
    <summary>Plans &amp; team {status && <span>· {status.plan.name} · {status.used}/{status.plan.monthly_jobs} jobs this month</span>}</summary>
    <fieldset disabled={busy || disabled}>
      {new URLSearchParams(window.location.search).get('billing') === 'success' && <p>Checkout returned successfully. Refresh plan &amp; usage while your payment is confirmed.</p>}
      {new URLSearchParams(window.location.search).get('billing') === 'cancelled' && <p>Checkout was closed. No plan change has been applied here.</p>}
      <p>Formatting and PDF export each use one job. Failed jobs do not count. Limits reset on the first of each month (UTC).</p>
      {catalog && !catalog.billingEnabled && <p className="notice info">Payments are not open yet. You can use the Free allowance during the pilot.</p>}
      <div className="plan-grid">{catalog?.plans.map(p => <section className="plan-card" key={p.id}>
        <h3>{p.name}</h3><p>{p.monthly_jobs} jobs/month · {p.seats} {p.seats === 1 ? 'seat' : 'seats'}</p>
        {p.id !== 'free' && <button type="button" disabled={!catalog.billingEnabled} onClick={() => void act(() => redirect('/billing/checkout', {plan: p.id}))}>Choose {p.name}</button>}
      </section>)}</div>
      <p>Prices are shown at checkout. Team includes one workspace and a shared quota, including the owner's personal jobs. Documents stay private to the uploader.</p>
      <button type="button" onClick={() => void act(reload)}>Refresh plan &amp; usage</button>{' '}
      {status?.portalAvailable && <button type="button" onClick={() => void act(() => redirect('/billing/portal', {}))}>Manage billing</button>}
      <label className="field"><span>Workspace for new jobs</span><select value={workspace} onChange={e => {onWorkspace(e.target.value); setCode('');}}><option value="">Personal</option>{teams.map(t => <option key={t.id} value={t.id}>{t.name}{t.active ? '' : ' (subscription inactive)'}</option>)}</select></label>
      {!workspace && status?.plan.id === 'team' && !teams.some(t => t.role === 'owner') && <div className="team-row"><input aria-label="New team name" maxLength={120} placeholder="Team name" value={name} onChange={e => setName(e.target.value)}/><button type="button" disabled={!name.trim()} onClick={() => void act(async () => {await api('/teams', {name}); setName(''); setMessage('Team created. Select it in the workspace list.');})}>Create team</button></div>}
      <div className="team-row"><input aria-label="Invitation code" placeholder="Paste your invitation code" value={token} onChange={e => setToken(e.target.value)}/><button type="button" disabled={!token.trim()} onClick={() => void act(async () => {await api('/teams/accept', {token: token.trim()}); setToken(''); setMessage('Team joined. Select it in the workspace list.');})}>Join team</button></div>
      {team && <section><h3>{team.name}</h3><ul>{members.map(m => <li key={m.id}>{m.email} · {m.role} {team.role === 'owner' && m.role !== 'owner' && <button type="button" onClick={() => void act(async () => {await api(`/teams/${workspace}/members/${m.id}`, {}, 'DELETE');})}>Remove member</button>}</li>)}</ul>
        {team.role === 'owner' && <><div className="team-row"><input aria-label="Invite email" type="email" placeholder="Colleague's email" value={email} onChange={e => setEmail(e.target.value)}/><button type="button" disabled={!team.active || !email.trim()} onClick={() => void act(async () => {const result = await api<{token: string}>(`/teams/${workspace}/invites`, {email}); setCode(result.token); setEmail('');})}>Create invitation</button></div>
        {code && <label className="field"><span>Share this one-time code privately (expires in 7 days)</span><input readOnly value={code} onFocus={e => e.target.select()}/></label>}
        <ul>{invites.map(i => <li key={i.id}>{i.email} · pending <button type="button" onClick={() => void act(async () => {await api(`/teams/${workspace}/invites/${i.id}`, {}, 'DELETE');})}>Revoke invitation</button></li>)}</ul>
        <button type="button" disabled={!team.active} onClick={() => void act(async () => {await api(`/teams/${workspace}/profiles`, profile); onTemplatesChanged(); setMessage('Current format copied to your team templates.');})}>Share current format with team</button></>}
        <h4>Shared templates</h4><ul>{shared.map(p => <li key={p.id}>{p.name} {team.role === 'owner' && <button type="button" onClick={() => void act(async () => {await api(`/teams/${workspace}/profiles/${p.id}`, {}, 'DELETE'); onTemplatesChanged();})}>Delete shared template</button>}</li>)}</ul>
      </section>}
      {message && <p role="status">{message}</p>}
    </fieldset>
  </details>;
}
