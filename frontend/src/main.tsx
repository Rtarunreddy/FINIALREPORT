import {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './styles.css';
import {PlansTeam} from './PlansTeam';

const API = '/api';
type Alignment = 'left' | 'center' | 'right' | 'justify';
type TextStyle = {font: string; size: number; alignment: Alignment; lineSpacing: number; before: number; after: number; bold?: boolean};
type Extras = {headerText: string; footerText: string; pageNumbers: boolean; pageNumberPosition: 'header' | 'footer'; imageMaxWidth: number; startChaptersOnNewPage: boolean; normalizeTables: boolean; normalizeCaptions: boolean; normalizeHeadersFooters: boolean; centerImages: boolean; fitImages: boolean; resetBodyIndents: boolean};
type Profile = {id?: string | null; name: string; page: {size: string; top: number; bottom: number; left: number; right: number; columns: number}; body: TextStyle; headings: Record<'h1' | 'h2' | 'h3', TextStyle>; extras: Extras};
type Uploaded = {id: string; name: string; convertedFrom?: string; metrics: Record<string, number>};
type Finding = {title: string; why: string; action: string};
type Audit = {passed: string[]; issues: Finding[]; review: Finding[]; warning: string};
type SummaryRow = {label: string; before: string; after: string; changed: boolean};
type Summary = {rows: SummaryRow[]; highlights: string[]};
type Result = {id: string; report: {changed: Record<string, number>; formatting_preview: Record<string, string>; preserved: string[]; manual: string; summary?: Summary}};
type Job = {id: string; kind: 'format' | 'pdf'; status: 'queued' | 'running' | 'done' | 'failed'; error: string | null; outputId: string | null; report: (Result['report'] & {note?: string; pages?: number}) | null};
type Health = {pdfConversion: boolean; pdfExport: boolean; retentionHours: number};
type Auth = {required: boolean; authenticated: boolean; retentionHours: number; user?: {email: string; plan: string} | null; googleEnabled?: boolean; passwordResetEnabled?: boolean};
const base: TextStyle = {font: 'Times New Roman', size: 12, alignment: 'justify', lineSpacing: 1.5, before: 0, after: 6};
const fallback: Profile = {id: 'generic', name: 'Generic university report', page: {size: 'Existing report', top: 1, bottom: 1, left: 1.25, right: 1, columns: 0}, body: base,
  headings: {h1: {...base, size: 16, alignment: 'left', lineSpacing: 1.15, before: 18, after: 10, bold: true}, h2: {...base, size: 14, alignment: 'left', lineSpacing: 1.15, before: 14, after: 8, bold: true}, h3: {...base, alignment: 'left', lineSpacing: 1.15, before: 10, bold: true}},
  extras: {headerText: '', footerText: '', pageNumbers: false, pageNumberPosition: 'footer', imageMaxWidth: 0, startChaptersOnNewPage: false, normalizeTables: true, normalizeCaptions: true, normalizeHeadersFooters: true, centerImages: true, fitImages: true, resetBodyIndents: true}};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(API + path, {...init, signal: AbortSignal.timeout(180000)}); }
  catch { throw new Error('The local service did not respond. Check the Report Ready window, then try again.'); }
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = value?.detail;
    const error = new Error(typeof detail === 'string' ? detail : detail?.message ? detail.message : Array.isArray(detail) ? detail.map((d: {loc: string[]; msg: string}) => `${d.loc.slice(2).join(' ')}: ${d.msg}`).join('; ') : 'That step could not be completed. Please try again.');
    throw Object.assign(error, {code: detail?.code});
  }
  if (!value) throw new Error('The service returned an unexpected response. Restart Report Ready and try again.');
  return value as T;
}
const jsonPost = (value: unknown): RequestInit => ({method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
function readPreference(key: string, fallbackValue: boolean) { try { const v = localStorage.getItem(key); return v === null ? fallbackValue : v === '1'; } catch { return fallbackValue; } }
function savePreference(key: string, value: boolean) { try { localStorage.setItem(key, value ? '1' : '0'); } catch { /* storage can be unavailable */ } }
// Poll a queued job until it finishes. The first check is immediate; later checks back off to every 2 s at most.
async function waitForJob(start: Job, onStatus: (status: Job['status']) => void): Promise<Job> {
  let job = start; const deadline = Date.now() + 10 * 60 * 1000; let delay = 250;
  for (;;) {
    onStatus(job.status);
    if (job.status === 'done') return job;
    if (job.status === 'failed') throw new Error(job.error || 'This job could not be completed. Please try again.');
    if (Date.now() > deadline) throw new Error('This is taking longer than expected. Check back in a few minutes; your original file is unchanged.');
    await sleep(delay); delay = Math.min(2000, delay + 250);
    job = await request<Job>(`/jobs/${job.id}`);
  }
}

function NumberField({label, value, min = 0, max = 72, step = .5, onChange}: {label: string; value: number; min?: number; max?: number; step?: number; onChange: (v: number) => void}) {
  return <label className="field"><span>{label}</span><input type="number" min={min} max={max} step="any" value={value} onChange={e => onChange(Number(e.target.value))}/></label>;
}

export function App() {
  const [quotaExceeded, setQuotaExceeded] = useState(false);
  const [workspace, setWorkspace] = useState('');
  const [templatesVersion, setTemplatesVersion] = useState(0);
  const [auth, setAuth] = useState<Auth | null>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [email, setEmail] = useState('');
  const [creating, setCreating] = useState(false);
  const [forgotPassword, setForgotPassword] = useState(false);
  const [resetToken, setResetToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
  const [authSubmitted, setAuthSubmitted] = useState(false);
  const [file, setFile] = useState<Uploaded | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profile, setProfile] = useState<Profile>(structuredClone(fallback));
  const [health, setHealth] = useState<Health | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [rating, setRating] = useState(0);
  const [reviewComment, setReviewComment] = useState('');
  const [reviewSent, setReviewSent] = useState(false);
  const [notice, setNotice] = useState({text: 'Choose your report to begin. Your original file stays unchanged.', error: false});
  const [busy, setBusy] = useState('');
  const [autoFormat, setAutoFormat] = useState(() => readPreference('report-ready-auto-format', true));
  const [dragging, setDragging] = useState(false);
  const locked = useRef(false);
  const settings = useRef<HTMLFormElement>(null);

  const say = (text: string, error = false) => setNotice({text, error});
  async function run(label: string, task: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true; setBusy(label); setQuotaExceeded(false);
    try { await task(); }
    catch (error) { setQuotaExceeded((error as {code?: string})?.code === 'quota_exceeded'); say(error instanceof Error ? error.message : 'Something went wrong. Please try again.', true); }
    finally { locked.current = false; setBusy(''); }
  }
  useEffect(() => {
    let active = true;
    request<Auth>('/auth/status')
      .then(status => { if (active) setAuth(status); })
      .catch(error => { if (active) say(error.message, true); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!auth?.authenticated) return;
    let active = true;
    Promise.all([request<Profile[]>('/profiles').then(async items => workspace ? [...items, ...await request<Profile[]>(`/teams/${workspace}/profiles`)] : items), request<Health>('/health')])
      .then(([items, capabilities]) => { if (active) { setProfiles(items); setHealth(capabilities); } })
      .catch(error => { if (active) say(error.message, true); });
    return () => { active = false; };
  }, [auth?.authenticated, workspace, templatesVersion]);

  function signIn(event: React.FormEvent) {
    event.preventDefault();
    void run(creating ? 'Creating your account…' : 'Signing in…', async () => {
      const response = await request<{authenticated: boolean; user?: Auth['user']}>(creating ? '/auth/register' : '/auth/login', jsonPost({email, password}));
      if (!response.authenticated) throw new Error('Sign-in could not be completed.');
      setPassword('');
      setAuth(current => ({required: true, retentionHours: 24, ...current, authenticated: true, user: response.user ?? null}));
      say('Signed in. Uploaded copies are automatically deleted after the retention period.');
    });
  }

  function requestPasswordReset(event: React.FormEvent) {
    event.preventDefault();
    setAuthSubmitted(false);
    void run('Sending recovery instructions…', async () => {
      const response = await request<{message: string}>('/auth/password-reset/request', jsonPost({email}));
      setAuthSubmitted(true);
      say(response.message);
    });
  }

  function resetPassword(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) { say('The passwords do not match.', true); return; }
    setAuthSubmitted(false);
    void run('Resetting your password…', async () => {
      const response = await request<{message: string}>('/auth/password-reset/confirm', jsonPost({token: resetToken, password}));
      setPassword(''); setConfirmPassword(''); setResetToken(''); setForgotPassword(false); setCreating(false);
      window.history.replaceState({}, '', window.location.pathname);
      setAuthSubmitted(true);
      say(response.message);
    });
  }

  function signOut() {
    void run('Signing out…', async () => {
      await request('/auth/logout', jsonPost({}));
      setAuth(current => current ? {...current, authenticated: false, user: null} : current);
      setProfiles([]); setFile(null); setWorkspace(''); change(structuredClone(fallback));
    });
  }

  function change(next: Profile) { setProfile(next); setAudit(null); setResult(null); say('Settings updated. Format your report to create a new copy.'); }
  function extra<K extends keyof Extras>(key: K, value: Extras[K]) { change({...profile, extras: {...profile.extras, [key]: value}}); }
  async function upload(f: File): Promise<Uploaded> {
    if (!/\.(docx|pdf)$/i.test(f.name)) throw new Error('Please choose a DOCX or PDF file.');
    if (f.size > 25 * 1024 * 1024) throw new Error('This file is over the 25 MB limit.');
    const data = new FormData(); data.append('file', f);
    return request<Uploaded>('/uploads', {method: 'POST', body: data});
  }
  function progress(status: Job['status'], label: string) { setBusy(status === 'queued' ? 'Waiting for a free worker…' : label); }
  async function formatUploaded(id: string): Promise<Result> {
    const queued = await request<Job>(`/uploads/${id}/apply`, jsonPost({profile, teamId: workspace || null}));
    const job = await waitForJob(queued, status => progress(status, 'Formatting report…'));
    if (!job.outputId || !job.report) throw new Error('The formatted copy is not available. Please try again.');
    setReviewSent(false); setRating(0); setReviewComment('');
    return {id: job.outputId, report: job.report};
  }
  function chooseFile(f?: File) {
    if (!f) return;
    void run('Uploading report…', async () => {
      const uploaded = await upload(f); setFile(uploaded); setAudit(null); setResult(null);
      if (autoFormat && /\.docx$/i.test(uploaded.name) && settings.current?.reportValidity() !== false) {
        setResult(await formatUploaded(uploaded.id)); say('Formatting complete. Download your DOCX and check the pages in Word.');
      } else say(uploaded.name.toLowerCase().endsWith('.pdf') ? 'PDF uploaded. Convert it to DOCX to continue.' : 'Report ready. Choose a template, then format your report.');
    });
  }
  function learn(f?: File) {
    if (!f) return;
    void run('Learning reference format…', async () => {
      if (!/\.docx$/i.test(f.name)) throw new Error('Choose a DOCX reference report.');
      const reference = await upload(f);
      try {
        const learned = await request<{profile: Profile; message: string}>(`/uploads/${reference.id}/learn-profile`, {method: 'POST'});
        change(learned.profile); setTemplatesVersion(v => v + 1);
        say('Reference template saved and selected. Your report is ready to format with it.');
      } finally { await request(`/uploads/${reference.id}`, {method: 'DELETE'}).catch(() => undefined); }
    });
  }
  function format(checkOnly = false) {
    if (!file || !settings.current?.reportValidity()) return;
    void run(checkOnly ? 'Checking report…' : 'Formatting report…', async () => {
      if (checkOnly) { setAudit(await request<Audit>(`/uploads/${file.id}/audit`, jsonPost({profile, teamId: workspace || null}))); say('The formatting plan is ready below.'); }
      else { setResult(await formatUploaded(file.id)); say('Formatting complete. Download your DOCX and check the pages in Word.'); }
    });
  }
  function download(kind: 'document' | 'pdf' | 'report') {
    if (!result) return;
    void run(kind === 'pdf' ? 'Preparing PDF…' : 'Preparing download…', async () => {
      let outputId = result.id;
      if (kind === 'pdf') {
        const queued = await request<Job>(`/outputs/${result.id}/pdf`, {method: 'POST'});
        const job = await waitForJob(queued, status => progress(status, 'Exporting PDF…'));
        if (!job.outputId) throw new Error('The PDF is not available. Please try again.');
        outputId = job.outputId;
      }
      const response = await fetch(`${API}/outputs/${outputId}/${kind === 'report' ? 'report' : 'document'}`, {signal: AbortSignal.timeout(180000)});
      if (!response.ok) { const value = await response.json().catch(() => ({})); throw new Error(value.detail || 'Download failed. Please try again.'); }
      const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = kind === 'report' ? 'formatting-changes.json' : `formatted-report.${kind === 'pdf' ? 'pdf' : 'docx'}`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
      say(kind === 'pdf' ? 'PDF ready. It is rendered on our server, so check line breaks in the DOCX if exact pagination matters.' : 'Download ready. Your original report remains unchanged.');
    });
  }
  function submitReview(event: React.FormEvent) {
    event.preventDefault();
    if (!rating) { say('Choose a rating before sending your review.', true); return; }
    void run('Sending review…', async () => {
      const response = await request<{message: string}>('/reviews', jsonPost({rating, comment: reviewComment}));
      setReviewSent(true); say(response.message);
    });
  }
  const isPdf = file?.name.toLowerCase().endsWith('.pdf');
  const toggleOptions: [keyof Extras, string][] = [['normalizeTables', 'Align and format table text'], ['normalizeCaptions', 'Format figure and table captions'], ['resetBodyIndents', 'Remove stray body indents'], ['centerImages', 'Center standalone inline images'], ['fitImages', 'Fit images inside page and column margins'], ['normalizeHeadersFooters', 'Align existing headers and footers'], ['startChaptersOnNewPage', 'Start Heading 1 chapters on a new page']];
  if (!auth) return <main><div className="empty"><h1>Report Ready</h1><p>Connecting to the service…</p></div></main>;
  if (auth.required && !auth.authenticated && resetToken) return <main><div className="empty"><h1>Reset your password</h1><p>Choose a new password for your Report Ready account.</p><form onSubmit={resetPassword} className="login"><label className="field"><span>New password (10+ characters)</span><input autoFocus required minLength={10} maxLength={128} type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)}/></label><label className="field"><span>Confirm new password</span><input required minLength={10} maxLength={128} type="password" autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}/></label><button className="primary" disabled={!!busy}>Reset password</button></form>{(authSubmitted || notice.error) && <p className={`notice ${notice.error ? 'error' : 'success'}`} role={notice.error ? 'alert' : 'status'}>{notice.text}</p>}<p><button type="button" className="link" onClick={() => {setResetToken(''); window.history.replaceState({}, '', window.location.pathname);}}>Return to sign in</button></p></div></main>;
  if (auth.required && !auth.authenticated) return <main><div className="empty"><h1>Report Ready</h1><p>{forgotPassword ? 'Enter your account email and we’ll send recovery instructions if an account is eligible.' : creating ? 'Create an account to format your reports.' : 'Sign in to format your reports.'}</p>{forgotPassword ? <form onSubmit={requestPasswordReset} className="login"><label className="field"><span>Email</span><input autoFocus required type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)}/></label><button className="primary" disabled={!!busy}>Send recovery email</button></form> : <form onSubmit={signIn} className="login"><label className="field"><span>Email</span><input autoFocus required type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)}/></label><label className="field"><span>Password{creating ? ' (10+ characters)' : ''}</span><input required type="password" minLength={creating ? 10 : undefined} autoComplete={creating ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)}/></label><button className="primary" disabled={!!busy}>{creating ? 'Create account' : 'Sign in'}</button></form>}{!forgotPassword && auth.googleEnabled && <p><a href="/api/auth/google/login">Continue with Google</a></p>}{auth.passwordResetEnabled && !creating && <p><button type="button" className="link" onClick={() => {setForgotPassword(true); setPassword(''); setAuthSubmitted(false);}}>Forgot password?</button></p>}<p><button type="button" className="link" onClick={() => {setCreating(value => !value); setForgotPassword(false); setPassword(''); setAuthSubmitted(false);}}>{creating ? 'I already have an account' : 'Create an account'}</button></p>{(authSubmitted || notice.error) && <p className={`notice ${notice.error ? 'error' : 'success'}`} role={notice.error ? 'alert' : 'status'}>{notice.text}</p>}</div></main>;
  return <main>
    <header><div className="brand"><span className="mark" aria-hidden="true">¶</span><div><h1>Report Ready</h1><p>Clean, consistent reports in a few steps.</p></div></div><span className="local">Files delete after {auth.retentionHours >= 48 ? Math.round(auth.retentionHours / 24) + ' days' : auth.retentionHours + ' hours'}{auth.required && auth.user && <> · {auth.user.email} · <button type="button" className="link" onClick={signOut}>Sign out</button></>}</span></header>
    {auth.required && <PlansTeam workspace={workspace} onWorkspace={id => {setWorkspace(id); change(structuredClone(fallback));}} profile={profile} onTemplatesChanged={() => setTemplatesVersion(v => v + 1)} refreshKey={busy} disabled={!!busy}/> }
    <div className={`notice ${notice.error ? 'error' : 'info'}`} role={notice.error ? 'alert' : 'status'} aria-live="polite">{busy || notice.text}{quotaExceeded && <p><a href="#plans" onClick={() => {const panel = document.getElementById('plans') as HTMLDetailsElement | null; if (panel) panel.open = true;}}>View plans and upgrade</a></p>}</div>
    <div className="workspace" aria-busy={!!busy}>
      <aside><section className="panel"><h2>1 · Add your report</h2>
        <label className={`drop${dragging ? ' dragging' : ''}`} onDragOver={e => {e.preventDefault(); if (!busy) setDragging(true);}} onDragLeave={() => setDragging(false)} onDrop={e => {e.preventDefault(); setDragging(false); if (!busy) chooseFile(e.dataTransfer.files[0]);}}>
          <input aria-label="Upload your report" type="file" disabled={!!busy} accept=".docx,.pdf" onChange={e => {chooseFile(e.target.files?.[0]); e.target.value = '';}}/>
          <strong>{file ? 'Choose another report' : 'Drop your report here'}</strong><small>Or browse files · DOCX or PDF · up to 25 MB</small>
        </label>
        <label className="check"><input type="checkbox" checked={autoFormat} onChange={e => {setAutoFormat(e.target.checked); savePreference('report-ready-auto-format', e.target.checked);}}/>Format automatically after upload</label>
        {file && <button className="text-button" disabled={!!busy} onClick={() => void run('Deleting uploaded copy…', async () => {
          await request(`/uploads/${file.id}`, {method: 'DELETE'});
          if (file.convertedFrom) await request(`/uploads/${file.convertedFrom}`, {method: 'DELETE'}).catch(() => undefined);
          setFile(null); setResult(null); setAudit(null); say('The uploaded copy and its outputs were deleted. Your original file is unchanged.');
        })}>Delete uploaded copy and outputs</button>}
      </section>
      <form ref={settings} onSubmit={e => {e.preventDefault(); format();}}>
        <fieldset disabled={!!busy}><section className="panel"><h2>2 · Choose a format</h2>
          <label className="field"><span>Template</span><select value={profile.id || ''} onChange={e => {const found = profiles.find(p => p.id === e.target.value); if (found) change(structuredClone(found));}}>
            <option value="">Custom settings</option>{profiles.map(p => <option key={p.id} value={p.id || ''}>{p.name}</option>)}
          </select></label>
          <p className="hint">{profile.body.font} · {profile.body.size} pt · {profile.body.lineSpacing} line spacing</p>
          <label className="reference-upload quiet"><span>Use a reference DOCX</span><input aria-label="Use a reference DOCX" type="file" accept=".docx" onChange={e => {learn(e.target.files?.[0]); e.target.value = '';}}/></label>
          <p className="help">Learn a senior report’s body, headings and margins without replacing your report.</p>
        </section>
        <section className="panel"><details><summary>Adjust format</summary><div className="disclosure-body">
          <label className="field"><span>Body font</span><input required maxLength={80} value={profile.body.font} onChange={e => change({...profile, id: null, body: {...profile.body, font: e.target.value}})}/></label>
          <div className="field-grid"><NumberField label="Size (pt)" min={8} max={48} value={profile.body.size} onChange={v => change({...profile, id: null, body: {...profile.body, size: v}})}/><NumberField label="Line spacing" min={1} max={3} step={.05} value={profile.body.lineSpacing} onChange={v => change({...profile, id: null, body: {...profile.body, lineSpacing: v}})}/></div>
          <label className="field"><span>Body alignment</span><select value={profile.body.alignment} onChange={e => change({...profile, id: null, body: {...profile.body, alignment: e.target.value as Alignment}})}>{['left', 'justify', 'center', 'right'].map(x => <option key={x}>{x}</option>)}</select></label>
          <div className="field-grid">{(['before', 'after'] as const).map(key => <NumberField key={key} label={`Space ${key} (pt)`} value={profile.body[key]} onChange={v => change({...profile, id: null, body: {...profile.body, [key]: v}})}/>)}</div>
          <label className="field"><span>Paper size</span><select value={profile.page.size} onChange={e => change({...profile, id: null, page: {...profile.page, size: e.target.value}})}>{['Existing report', 'A4', 'Letter'].map(x => <option key={x}>{x}</option>)}</select></label>
          <label className="field"><span>Columns</span><select value={profile.page.columns} onChange={e => change({...profile, id: null, page: {...profile.page, columns: Number(e.target.value)}})}><option value={0}>Keep existing</option><option value={1}>One</option><option value={2}>Two</option></select></label>
          <div className="field-grid">{(['top', 'bottom', 'left', 'right'] as const).map(key => <NumberField key={key} label={`${key} margin (in)`} min={.2} max={3} step={.05} value={profile.page[key]} onChange={v => change({...profile, id: null, page: {...profile.page, [key]: v}})}/>)}</div>
          {(['h1', 'h2', 'h3'] as const).map((key, i) => <details key={key} className="heading-settings"><summary>Heading {i + 1}</summary>
            <label className="field"><span>Font</span><input required maxLength={80} value={profile.headings[key].font} onChange={e => change({...profile, id: null, headings: {...profile.headings, [key]: {...profile.headings[key], font: e.target.value}}})}/></label>
            <NumberField label="Size (pt)" value={profile.headings[key].size} min={8} max={48} onChange={v => change({...profile, id: null, headings: {...profile.headings, [key]: {...profile.headings[key], size: v}}})}/>
            <label className="field"><span>Alignment</span><select value={profile.headings[key].alignment} onChange={e => change({...profile, id: null, headings: {...profile.headings, [key]: {...profile.headings[key], alignment: e.target.value as Alignment}}})}>{['left', 'center', 'right', 'justify'].map(x => <option key={x}>{x}</option>)}</select></label>
          </details>)}
          <label className="field"><span>Template name</span><input required maxLength={80} value={profile.name} onChange={e => change({...profile, name: e.target.value})}/></label>
          <button type="button" className="quiet full" onClick={() => {if (settings.current?.reportValidity()) void run('Saving template…', async () => {const saved = await request<Profile>('/profiles', jsonPost({...profile, id: null})); change(saved); setTemplatesVersion(v => v + 1); say('Your template is saved for future reports.');});}}>Save as a new template</button>
        </div></details></section>
        <section className="panel"><details><summary>Cleanup and finishing touches</summary><div className="disclosure-body">
          {toggleOptions.map(([key, label]) => <label className="check" key={key}><input type="checkbox" checked={!!profile.extras[key]} onChange={e => extra(key, e.target.checked)}/>{label}</label>)}
          <NumberField label="Maximum image width (in; 0 = auto)" max={20} step={.1} value={profile.extras.imageMaxWidth} onChange={v => extra('imageMaxWidth', v)}/>
          <label className="field"><span>Add header text (optional)</span><input maxLength={240} value={profile.extras.headerText} onChange={e => extra('headerText', e.target.value)}/></label>
          <label className="field"><span>Add footer text (optional)</span><input maxLength={240} value={profile.extras.footerText} onChange={e => extra('footerText', e.target.value)}/></label>
          <p className="help">Existing header and footer wording stays in place. Leave these blank to keep it.</p>
          <label className="check"><input type="checkbox" checked={profile.extras.pageNumbers} onChange={e => extra('pageNumbers', e.target.checked)}/>Add a page number if missing</label>
          {profile.extras.pageNumbers && <label className="field"><span>Page number position</span><select value={profile.extras.pageNumberPosition} onChange={e => extra('pageNumberPosition', e.target.value as 'header' | 'footer')}><option value="footer">Footer</option><option value="header">Header</option></select></label>}
        </div></details></section></fieldset>
      </form></aside>
      <section className="stage"><ol className="steps" aria-label="Progress"><li className={file ? 'done' : 'active'}><span className="dot">1</span>Upload</li><li className={file && !result ? 'active' : ''}><span className="dot">2</span>Format</li><li className={result ? 'active' : ''}><span className="dot">3</span>Download</li></ol>
      {!file ? <div className="empty"><h2>Your report, consistently formatted</h2><p>Upload your DOCX, choose a template and create a clean copy. Body text, headings, tables, captions and inline images are handled together.</p><p className="hint">For the closest match, use a reference DOCX and review the learned settings. Custom layouts still need a final check in Word.</p></div> : <>
        <h2 className="filename">{file.name}</h2><p className="hint">{file.metrics.words.toLocaleString()} words · {file.metrics.tables || 0} tables · {file.metrics.imageOccurrences ?? file.metrics.images} images</p>
        {isPdf ? <><p>PDF conversion can change layout. A DOCX original gives the best result.</p><button className="primary" disabled={!!busy} onClick={() => void run('Converting PDF…', async () => {const converted = await request<Uploaded>(`/uploads/${file.id}/convert-to-docx`, {method: 'POST'}); setFile(converted); setResult(null); setAudit(null); say('Converted to DOCX. Choose a template and format your report.');})}>Convert PDF to DOCX</button>{health && !health.pdfConversion && <p className="help">Run enable-pdf.bat once to enable this optional feature.</p>}</> : <>
          {!result && <div className="actions"><button className="primary" disabled={!!busy} onClick={() => format()}>Format my report</button><button className="quiet" disabled={!!busy} onClick={() => format(true)}>Check formatting plan</button></div>}
          {audit && !result && <div className="audit"><h3>What will be formatted</h3>{audit.issues.map(x => <div className="finding" key={x.title}><strong>{x.title}</strong><p>{x.action}</p></div>)}{audit.review.length > 0 && <h3>Review in Word</h3>}{audit.review.map(x => <div className="finding" key={x.title}><strong>{x.title}</strong><p>{x.action}</p></div>)}<p className="help">{audit.warning}</p></div>}
          {result && <><h3>Your formatted copy is ready</h3><div className="report"><p>{result.report.formatting_preview.body}</p><div className="summary"><b>{result.report.changed.headings} headings</b><b>{result.report.changed.tables} tables</b><b>{result.report.changed.captions} captions</b><b>{result.report.changed.images} images resized</b></div><ul>{result.report.preserved.map(x => <li key={x}>{x}</li>)}</ul></div>{result.report.summary && result.report.summary.rows.length > 0 && <div className="compare"><h3>Before and after</h3>{result.report.summary.highlights.length > 0 && <ul className="highlights">{result.report.summary.highlights.map(x => <li key={x}>{x}</li>)}</ul>}<table><thead><tr><th>Setting</th><th>Before</th><th>After</th></tr></thead><tbody>{result.report.summary.rows.map(row => <tr key={row.label} className={row.changed ? 'changed' : ''}><th scope="row">{row.label}</th><td>{row.before}</td><td>{row.after}</td></tr>)}</tbody></table></div>}<p className="hint">{result.report.manual}</p>
            <div className="actions"><button className="primary" disabled={!!busy} onClick={() => download('document')}>Download DOCX</button>{health?.pdfExport && <button className="quiet" disabled={!!busy} onClick={() => download('pdf')}>Download PDF</button>}<button className="quiet" disabled={!!busy} onClick={() => download('report')}>Download change report</button></div>
            {!health?.pdfExport && <p className="help">PDF export is not available here. Open the DOCX in Word and choose Save as PDF.</p>}
            <button className="text-button" disabled={!!busy} onClick={() => {setResult(null); setAudit(null); say('Adjust the settings and format again.');}}>Adjust and format again</button>
            <section className="review" aria-labelledby="review-heading"><h3 id="review-heading">Review Report Ready</h3>{reviewSent ? <p>Thanks for helping improve the app.</p> : <form onSubmit={submitReview}><p className="help">How was your experience?</p><div className="rating" role="radiogroup" aria-label="Your rating">{[1, 2, 3, 4, 5].map(value => <button type="button" key={value} className={rating >= value ? 'selected' : ''} aria-label={`${value} star${value === 1 ? '' : 's'}`} aria-pressed={rating === value} onClick={() => setRating(value)}>★</button>)}</div><label className="field"><span>Optional comment</span><textarea maxLength={1000} value={reviewComment} onChange={e => setReviewComment(e.target.value)} placeholder="What worked well, or what could improve?"/></label><button className="quiet" disabled={!!busy}>Send review</button></form>}</section>
          </>}
        </>}
      </>}
      </section>
    </div>
  </main>;
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<App/>);
