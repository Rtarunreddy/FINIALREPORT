// @vitest-environment jsdom
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {PlansTeam} from './PlansTeam';
const onWorkspace = vi.fn(); const onTemplatesChanged = vi.fn();
let teams = [{id: 'team1', name: 'Research Lab', role: 'owner'}];
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url.endsWith('/plans')) return Response.json({plans: [{id: 'free', name: 'Free', monthly_jobs: 5, seats: 5}]});
  if (url.includes('/plans/usage')) return Response.json({plan: {id: 'free', name: 'Free', monthly_jobs: 5, seats: 5}, used: 3, remaining: 2});
  if (url.endsWith('/teams') && init?.method === 'POST') return Response.json({id: 'team2', name: 'Study group'});
  if (url.endsWith('/teams')) return Response.json(teams);
  if (url.endsWith('/members')) return Response.json([{id: 'me', email: 'owner@example.com', role: 'owner'}]);
  if (url.endsWith('/profiles')) return Response.json(init?.method ? {id: 'shared1'} : [{id: 'shared1', name: 'College format'}]);
  if (url.endsWith('/invites')) return Response.json(init?.method ? {token: 'private-invitation-code-123'} : []);
  if (url.endsWith('/accept')) return Response.json({message: 'Joined'});
  throw new Error(url);
});
beforeEach(() => {teams = [{id: 'team1', name: 'Research Lab', role: 'owner'}]; vi.clearAllMocks(); vi.stubGlobal('fetch', fetchMock);});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});
function show(workspace = '') {render(<PlansTeam workspace={workspace} onWorkspace={onWorkspace} profile={{name: 'My format'}} onTemplatesChanged={onTemplatesChanged} refreshKey="" disabled={false}/>);}
it('shows the free allowance without paid plans or checkout', async () => {
  show();
  await screen.findByText(/Free accounts get 5 jobs per UTC calendar month/);
  fireEvent.click(screen.getByText(/Usage & team/));
  expect(screen.getByText(/3\/5/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: /Choose/})).toBeNull();
  expect(fetchMock.mock.calls.some(([url]) => url.includes('/billing/'))).toBe(false);
});
it('creates a private invitation and shares the selected format', async () => {
  show('team1'); await screen.findByText('College format'); fireEvent.click(screen.getByText(/Usage & team/));
  fireEvent.change(screen.getByLabelText('Invite email'), {target: {value: 'member@example.com'}});
  fireEvent.click(screen.getByRole('button', {name: 'Create invitation'}));
  await screen.findByDisplayValue('private-invitation-code-123');
  await waitFor(() => expect((screen.getByRole('button', {name: 'Share current format with team'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', {name: 'Share current format with team'}));
  await waitFor(() => expect(onTemplatesChanged).toHaveBeenCalled());
  expect(fetchMock.mock.calls.some(([url, init]) => url.endsWith('/teams/team1/profiles') && init?.body === JSON.stringify({name: 'My format'}))).toBe(true);
});
it('allows a free user to create a team', async () => {
  teams = [];
  show(); await screen.findByText(/5 jobs per UTC calendar month/);
  fireEvent.click(screen.getByText(/Usage & team/));
  fireEvent.change(screen.getByLabelText('New team name'), {target: {value: 'Study group'}});
  fireEvent.click(screen.getByRole('button', {name: 'Create team'}));
  await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url.endsWith('/teams') && init?.method === 'POST')).toBe(true));
});
