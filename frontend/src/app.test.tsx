// @vitest-environment jsdom
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {App} from './main';

const style = {font: 'Calibri', size: 11, alignment: 'left', lineSpacing: 1.15, before: 0, after: 6};
const profile = {id: 'generic', name: 'Generic university report', page: {size: 'Existing report', top: 1, bottom: 1, left: 1, right: 1, columns: 0}, body: style, headings: {h1: {...style, size: 16}, h2: {...style, size: 14}, h3: style}, extras: {headerText: '', footerText: '', pageNumbers: false, pageNumberPosition: 'footer', imageMaxWidth: 0, startChaptersOnNewPage: false, normalizeTables: true, normalizeCaptions: true, normalizeHeadersFooters: true, centerImages: true, fitImages: true, resetBodyIndents: true}};
const reportFile = () => new File(['test'], 'my-report.docx', {type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'});
let quotaError = false;
let failUpload = false;
let networkFailure = false;
let uploadCount = 0;
let pollCount = 0;
let jobFails = false;
let minPolls = 1;
let pdfEnabled = false;
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url.endsWith('/auth/status')) return Response.json({required: false, authenticated: true, retentionHours: 24});
  if (url.endsWith('/health')) return Response.json({pdfConversion: false, pdfExport: pdfEnabled, retentionHours: 24});
  if (url.endsWith('/profiles')) return Response.json([profile]);
  if (url.endsWith('/uploads') && init?.method === 'POST') {
    uploadCount++;
    if (networkFailure) throw new TypeError('Network offline');
    if (failUpload) return Response.json({detail: 'Please save a valid DOCX.'}, {status: 400});
    return Response.json({id: 'upload-' + uploadCount, name: 'my-report.docx', metrics: {words: 100, tables: 2, images: 1}});
  }
  if (url.endsWith('/learn-profile')) return Response.json({profile: {...profile, id: 'learned', name: 'Learned reference'}, message: 'Saved'});
  if (url.endsWith('/apply') && quotaError) return Response.json({detail: {code: 'quota_exceeded', message: 'Monthly job limit reached. Open Plans & team to upgrade.'}}, {status: 402});
  if (url.endsWith('/apply')) return Response.json({id: 'job-1', kind: 'format', status: 'queued', error: null, outputId: null, report: null}, {status: 202});
  if (url.endsWith('/jobs/job-1')) {
    pollCount++;
    if (jobFails) return Response.json({id: 'job-1', kind: 'format', status: 'failed', error: 'This document is damaged.', outputId: null, report: null});
    if (pollCount < minPolls) return Response.json({id: 'job-1', kind: 'format', status: 'running', error: null, outputId: null, report: null});
    return Response.json({id: 'job-1', kind: 'format', status: 'done', error: null, outputId: 'result-1', report: {changed: {headings: 1, tables: 2, captions: 1, images: 0}, formatting_preview: {body: 'Calibri 11 pt'}, summary: {highlights: ['Different body fonts: 3 → 1'], rows: [{label: 'Body fonts', before: 'Arial, Calibri, Verdana', after: 'Calibri', changed: true}]}, preserved: ['Original upload unchanged'], manual: 'Review in Word.'}});
  }
  if (url.endsWith('/outputs/result-1/pdf')) return Response.json({id: 'job-pdf', kind: 'pdf', status: 'done', error: null, outputId: 'pdf-1', report: {engine: 'libreoffice'}}, {status: 202});
  if (init?.method === 'DELETE') return Response.json({message: 'Deleted'});
  throw new Error('Unexpected request: ' + url);
});

beforeEach(() => {window.history.replaceState({}, '', '/'); quotaError = false; localStorage.setItem('report-ready-auto-format', '0'); failUpload = false; networkFailure = false; uploadCount = 0; pollCount = 0; jobFails = false; minPolls = 1; pdfEnabled = false; fetchMock.mockClear(); vi.stubGlobal('fetch', fetchMock);});
afterEach(() => {cleanup(); window.history.replaceState({}, '', '/'); vi.unstubAllGlobals();});

async function chooseReport() {
  const input = await screen.findByLabelText('Upload your report');
  fireEvent.change(input, {target: {files: [reportFile()]}});
  await screen.findByRole('heading', {name: 'my-report.docx'});
}

describe('report workflow', () => {
  it('recovers from a failed upload and enables another attempt', async () => {
    render(<App/>); failUpload = true;
    fireEvent.change(await screen.findByLabelText('Upload your report'), {target: {files: [reportFile()]}});
    await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toContain('valid DOCX');
    expect((screen.getByLabelText('Upload your report') as HTMLInputElement).disabled).toBe(false);
    failUpload = false; await chooseReport();
    expect(screen.getByRole('button', {name: 'Format my report'})).toBeTruthy();
  });
  it('recovers when the network request throws', async () => {
    render(<App/>); networkFailure = true;
    fireEvent.change(await screen.findByLabelText('Upload your report'), {target: {files: [reportFile()]}});
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('local service'));
    expect((screen.getByLabelText('Upload your report') as HTMLInputElement).disabled).toBe(false);
  });
  it('invalidates downloads when formatting settings change', async () => {
    render(<App/>); await chooseReport();
    fireEvent.click(screen.getByRole('button', {name: 'Format my report'}));
    await screen.findByRole('button', {name: 'Download DOCX'});
    fireEvent.change(screen.getByLabelText('Body font'), {target: {value: 'Arial'}});
    expect(screen.queryByRole('button', {name: 'Download DOCX'})).toBeNull();
    expect(screen.getByRole('button', {name: 'Format my report'})).toBeTruthy();
  });
  it('learns a reference without replacing the active report', async () => {
    render(<App/>); await chooseReport();
    fireEvent.change(screen.getByLabelText('Use a reference DOCX'), {target: {files: [new File(['reference'], 'senior.docx')]}});
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Reference template saved'));
    expect(screen.getByRole('heading', {name: 'my-report.docx'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: 'Format my report'}));
    await screen.findByRole('button', {name: 'Download DOCX'});
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/uploads/upload-1/apply')).toBe(true);
  });
});

describe('queued formatting', () => {
  it('formats right after upload, polls the job and shows before and after', async () => {
    localStorage.setItem('report-ready-auto-format', '1'); minPolls = 2;
    render(<App/>);
    fireEvent.change(await screen.findByLabelText('Upload your report'), {target: {files: [reportFile()]}});
    await screen.findByRole('button', {name: 'Download DOCX'}, {timeout: 5000});
    expect(screen.getByText('Different body fonts: 3 → 1')).toBeTruthy();
    expect(screen.getByRole('row', {name: /Body fonts Arial, Calibri, Verdana Calibri/})).toBeTruthy();
    expect(pollCount).toBeGreaterThanOrEqual(2);
  });
  it('remembers turning automatic formatting off', async () => {
    localStorage.setItem('report-ready-auto-format', '1');
    render(<App/>); fireEvent.click(await screen.findByLabelText('Format automatically after upload'));
    expect(localStorage.getItem('report-ready-auto-format')).toBe('0');
    await chooseReport(); expect(screen.getByRole('button', {name: 'Format my report'})).toBeTruthy();
  });
  it('shows the job error and keeps the upload when formatting fails', async () => {
    jobFails = true; render(<App/>); await chooseReport();
    fireEvent.click(screen.getByRole('button', {name: 'Format my report'}));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('damaged'));
    expect(screen.getByRole('heading', {name: 'my-report.docx'})).toBeTruthy();
    expect(screen.getByRole('button', {name: 'Format my report'})).toBeTruthy();
  });
  it('exports a PDF through a queued job', async () => {
    pdfEnabled = true; vi.stubGlobal('URL', Object.assign(URL, {createObjectURL: () => 'blob:x', revokeObjectURL: () => undefined}));
    const downloads: string[] = [];
    const base = fetchMock.getMockImplementation()!;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/outputs/pdf-1/document')) { downloads.push(url); return new Response('%PDF-', {status: 200}); }
      return base(url, init);
    }));
    render(<App/>); await chooseReport();
    fireEvent.click(screen.getByRole('button', {name: 'Format my report'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Download PDF'}, {timeout: 5000}));
    await waitFor(() => expect(downloads).toEqual(['/api/outputs/pdf-1/document']), {timeout: 5000});
  });
});

describe('sign-in', () => {
  it('asks for email and password, then shows the workspace', async () => {
    let signedIn = false;
    const calls: {url: string; body: string}[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/status')) return Response.json({required: true, authenticated: signedIn, retentionHours: 24, user: null, googleEnabled: true});
      if (url.endsWith('/auth/register')) { signedIn = true; calls.push({url, body: String(init?.body)}); return Response.json({authenticated: true, user: {email: 'new@example.com', plan: 'free'}}); }
      if (url.endsWith('/health')) return Response.json({pdfConversion: false, pdfExport: false, retentionHours: 24});
      if (url.endsWith('/profiles')) return Response.json([profile]);
      throw new Error('Unexpected request: ' + url);
    }));
    render(<App/>);
    expect(await screen.findByText('Continue with Google')).toBeTruthy();
    fireEvent.click(screen.getByText('Create an account'));
    fireEvent.change(screen.getByLabelText(/Email/), {target: {value: 'new@example.com'}});
    fireEvent.change(screen.getByLabelText(/Password/), {target: {value: 'correct horse battery'}});
    fireEvent.click(screen.getByRole('button', {name: 'Create account'}));
    expect(await screen.findByLabelText('Upload your report')).toBeTruthy();
    expect(JSON.parse(calls[0].body)).toEqual({email: 'new@example.com', password: 'correct horse battery'});
    expect(screen.getByText(/new@example.com/)).toBeTruthy();
  });

  it('requests a generic password recovery email', async () => {
    const calls: {url: string; body: string}[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/status')) return Response.json({required: true, authenticated: false, retentionHours: 24, passwordResetEnabled: true});
      if (url.endsWith('/auth/password-reset/request')) { calls.push({url, body: String(init?.body)}); return Response.json({message: 'If an account with that email can reset a password, instructions will be sent shortly.'}); }
      throw new Error('Unexpected request: ' + url);
    }));
    render(<App/>);
    fireEvent.click(await screen.findByRole('button', {name: 'Forgot password?'}));
    fireEvent.change(screen.getByLabelText('Email'), {target: {value: 'ada@example.com'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send recovery email'}));
    expect((await screen.findByRole('status')).textContent).toContain('instructions will be sent shortly');
    expect(JSON.parse(calls[0].body)).toEqual({email: 'ada@example.com'});
  });

  it('submits a password reset from the emailed token link', async () => {
    window.history.replaceState({}, '', '/#token=one-time-token');
    let submitted: unknown;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/status')) return Response.json({required: true, authenticated: false, retentionHours: 24, passwordResetEnabled: true});
      if (url.endsWith('/auth/password-reset/confirm')) { submitted = JSON.parse(String(init?.body)); return Response.json({message: 'Your password has been reset. You can now sign in.'}); }
      throw new Error('Unexpected request: ' + url);
    }));
    render(<App/>);
    fireEvent.change(await screen.findByLabelText('New password (10+ characters)'), {target: {value: 'a brand new password'}});
    fireEvent.change(screen.getByLabelText('Confirm new password'), {target: {value: 'a brand new password'}});
    fireEvent.click(screen.getByRole('button', {name: 'Reset password'}));
    expect((await screen.findByRole('status')).textContent).toContain('You can now sign in');
    expect(submitted).toEqual({token: 'one-time-token', password: 'a brand new password'});
    expect(window.location.search).toBe('');
  });
});



it('shows an upgrade action when monthly quota is exhausted', async () => {
  quotaError = true; render(<App/>); await chooseReport();
  fireEvent.click(screen.getByRole('button', {name: 'Format my report'}));
  await screen.findByRole('link', {name: 'View plans and upgrade'});
  expect(screen.getByRole('alert').textContent).toContain('Monthly job limit reached');
  expect(screen.getByRole('heading', {name: 'my-report.docx'})).toBeTruthy();
});
