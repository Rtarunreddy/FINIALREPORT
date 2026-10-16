import {useEffect, useRef, useState} from 'react';

type Plan = {id: string; name: string; monthly_jobs: number; seats: number};
type Status = {plan: Plan; used: number; remaining: number};
type Team = {id: string; name: string; role: string};
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
  const [catalog, setCatalog] = useState<{plans: Plan[]} | null>(null);
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
    const [c, t] = await Promise.all([api<{plans: Plan[]}>('/plans'), api<Team[]>('/teams')]);
    const selected = t.find(x => x.id === workspace);
    const s = await api<Status>('/plans/usage' + (selected ? '?team_id=' + encodeURIComponent(workspace) : ''));
    const [m, i, p] = workspace && selected ? await Promise.all([
      api<Member[]>(`/teams/${workspace}/members`),
      selected.role === 'owner' ? api<Invite[]>(`/teams/${workspace}/invites`) : Promise.resolve([]),
      api<{id: string; name: string}[]>(`/teams/${workspace}/profiles`),
    ]) : [[], [], []];
    if (generation !== loadGeneration.current) return;
    setCatalog(c); setStatus(s); setTeams(t); setMembers(m); setInvites(i); setShared(p);
    if (workspace && !selected) { onWorkspace(''); setMessage('Team access changed. Switched to your personal workspace.'); }
  }
  useEffect(() => { void reload().catch(e => setMessage(e.message)); return () => {loadGeneration.current++;}; }, [workspace, refreshKey]);
  async function act(fn: () => Promise<void>) {
    if (busy || disabled) return;
    setBusy(true); setMessage('');
    try { await fn(); await reload(); } catch (e) { setMessage(e instanceof Error ? e.message : 'Please try again.'); }
    finally { setBusy(false); }
  }
  return <details id="plans" className="panel plans-panel" open={window.location.hash === '#plans' || undefined}>
    <summary>Usage &amp; team {status && <span>· {status.plan.name} · {status.used}/{status.plan.monthly_jobs} jobs this month</span>}</summary>
    <fieldset disabled={busy || disabled}>
      <p>Formatting and PDF export each use one job. Free accounts get {catalog?.plans[0]?.monthly_jobs ?? 5} jobs per UTC calendar month. Failed jobs do not count.</p>
      <p>Teams are free, with up to 5 members. Jobs in a team workspace share the owner's monthly allowance; personal documents remain private.</p>
      <button type="button" onClick={() => void act(reload)}>Refresh usage</button>
      <label className="field"><span>Workspace for new jobs</span><select value={workspace} onChange={e => {onWorkspace(e.target.value); setCode('');}}><option value="">Personal</option>{teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
      {!workspace && !teams.some(t => t.role === 'owner') && <div className="team-row"><input aria-label="New team name" maxLength={120} placeholder="Team name" value={name} onChange={e => setName(e.target.value)}/><button type="button" disabled={!name.trim()} onClick={() => void act(async () => {await api('/teams', {name}); setName(''); setMessage('Team created. Select it in the workspace list.');})}>Create team</button></div>}
      <div className="team-row"><input aria-label="Invitation code" placeholder="Paste your invitation code" value={token} onChange={e => setToken(e.target.value)}/><button type="button" disabled={!token.trim()} onClick={() => void act(async () => {await api('/teams/accept', {token: token.trim()}); setToken(''); setMessage('Team joined. Select it in the workspace list.');})}>Join team</button></div>
      {team && <section><h3>{team.name}</h3><ul>{members.map(m => <li key={m.id}>{m.email} · {m.role} {team.role === 'owner' && m.role !== 'owner' && <button type="button" onClick={() => void act(async () => {await api(`/teams/${workspace}/members/${m.id}`, {}, 'DELETE');})}>Remove member</button>}</li>)}</ul>
        {team.role === 'owner' && <><div className="team-row"><input aria-label="Invite email" type="email" placeholder="Colleague's email" value={email} onChange={e => setEmail(e.target.value)}/><button type="button" disabled={!email.trim()} onClick={() => void act(async () => {const result = await api<{token: string}>(`/teams/${workspace}/invites`, {email}); setCode(result.token); setEmail('');})}>Create invitation</button></div>
        {code && <label className="field"><span>Share this one-time code privately (expires in 7 days)</span><input readOnly value={code} onFocus={e => e.target.select()}/></label>}
        <ul>{invites.map(i => <li key={i.id}>{i.email} · pending <button type="button" onClick={() => void act(async () => {await api(`/teams/${workspace}/invites/${i.id}`, {}, 'DELETE');})}>Revoke invitation</button></li>)}</ul>
        <button type="button" onClick={() => void act(async () => {await api(`/teams/${workspace}/profiles`, profile); onTemplatesChanged(); setMessage('Current format copied to your team templates.');})}>Share current format with team</button></>}
        <h4>Shared templates</h4><ul>{shared.map(p => <li key={p.id}>{p.name} {team.role === 'owner' && <button type="button" onClick={() => void act(async () => {await api(`/teams/${workspace}/profiles/${p.id}`, {}, 'DELETE'); onTemplatesChanged();})}>Delete shared template</button>}</li>)}</ul>
      </section>}
      {message && <p role="status">{message}</p>}
    </fieldset>
  </details>;
}
