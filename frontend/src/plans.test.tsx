// @vitest-environment jsdom
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {PlansTeam} from './PlansTeam';
const onWorkspace = vi.fn(); const onTemplatesChanged = vi.fn();
let enabled = false;
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url.endsWith('/billing/plans')) return Response.json({billingEnabled: enabled, plans: [{id: 'free', name: 'Free', monthly_jobs: 5, seats: 1}, {id: 'pro', name: 'Pro', monthly_jobs: 100, seats: 1}, {id: 'team', name: 'Team', monthly_jobs: 500, seats: 5}]});
  if (url.includes('/billing/status')) return Response.json({plan: {id: 'team', name: 'Team', monthly_jobs: 500, seats: 5}, used: 3, remaining: 497, portalAvailable: true});
  if (url.endsWith('/teams')) return Response.json([{id: 'team1', name: 'Research Lab', role: 'owner', active: true}]);
  if (url.endsWith('/members')) return Response.json([{id: 'me', email: 'owner@example.com', role: 'owner'}]);
  if (url.endsWith('/profiles')) return Response.json(init?.method ? {id: 'shared1'} : [{id: 'shared1', name: 'College format'}]);
  if (url.endsWith('/invites')) return Response.json(init?.method ? {token: 'private-invitation-code-123'} : []);
  if (url.endsWith('/accept')) return Response.json({message: 'Joined'});
  if (url.endsWith('/billing/checkout')) return Response.json({detail: 'Manage your existing subscription in the billing portal.'}, {status: 409});
  throw new Error(url);
});
beforeEach(() => {enabled = false; vi.clearAllMocks(); vi.stubGlobal('fetch', fetchMock);});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});
function show(workspace = '') {render(<PlansTeam workspace={workspace} onWorkspace={onWorkspace} profile={{name: 'My format'}} onTemplatesChanged={onTemplatesChanged} refreshKey="" disabled={false}/>);}
it('shows usage and keeps checkout disabled during the pilot', async () => {
  show();
  await screen.findByText(/Payments are not open/);
  fireEvent.click(screen.getByText(/Plans & team/));
  expect(screen.getByText(/3\/500/)).toBeTruthy();
  expect((screen.getByRole('button', {name: 'Choose Pro'}) as HTMLButtonElement).disabled).toBe(true);
});
it('surfaces actionable billing errors', async () => {
  enabled = true; show(); await screen.findByText(/3\/500/);
  fireEvent.click(screen.getByText(/Plans & team/));
  fireEvent.click(screen.getByRole('button', {name: 'Choose Pro'}));
  await screen.findByText('Manage your existing subscription in the billing portal.');
});
it('creates a private invitation and shares the selected format', async () => {
  show('team1'); await screen.findByText('College format'); fireEvent.click(screen.getByText(/Plans & team/));
  fireEvent.change(screen.getByLabelText('Invite email'), {target: {value: 'member@example.com'}});
  fireEvent.click(screen.getByRole('button', {name: 'Create invitation'}));
  await screen.findByDisplayValue('private-invitation-code-123');
  await waitFor(() => expect((screen.getByRole('button', {name: 'Share current format with team'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', {name: 'Share current format with team'}));
  await waitFor(() => expect(onTemplatesChanged).toHaveBeenCalled());
  expect(fetchMock.mock.calls.some(([url, init]) => url.endsWith('/teams/team1/profiles') && init?.body === JSON.stringify({name: 'My format'}))).toBe(true);
});
