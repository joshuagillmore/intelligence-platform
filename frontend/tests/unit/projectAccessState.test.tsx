import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AxiosError } from 'axios';
import ProjectDashboard from '@/app/project/[id]/page';

/**
 * The project dashboard when the backend refuses it (contract 2: 403 "No
 * access to this project"): a distinct no-access state, not the generic
 * "could not load" error, and the project is dropped from the context. Also
 * the header's role chip and open badge when it does load.
 */

const ctx = vi.hoisted(() => ({ setActiveProject: vi.fn(), dropProject: vi.fn() }));
vi.mock('@/lib/ProjectContext', () => ({ useProject: () => ctx }));
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'p1' }),
  useRouter: () => ({ push: vi.fn() }),
}));
const notify = vi.hoisted(() => vi.fn());
vi.mock('@/components/NotificationProvider', () => ({
  useNotifications: () => ({ addNotification: notify }),
}));
vi.mock('@/components/Sidebar', () => ({ default: () => null }));
vi.mock('@/components/PirPanel', () => ({ default: () => null }));

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...real,
    projectsApi: { get: vi.fn(), members: vi.fn(), setMemberRole: vi.fn(), removeMember: vi.fn() },
    graphApi: { statistics: vi.fn(), centrality: vi.fn() },
    timelineApi: { get: vi.fn() },
    reportsApi: { list: vi.fn() },
    collectionPlansApi: { list: vi.fn() },
    exportApi: { stix: vi.fn() },
  };
});

import { projectsApi, graphApi, timelineApi, reportsApi, collectionPlansApi, exportApi } from '@/lib/api';
type Mock = ReturnType<typeof vi.fn>;
const m = {
  get: projectsApi.get as unknown as Mock,
  members: projectsApi.members as unknown as Mock,
  statistics: graphApi.statistics as unknown as Mock,
  centrality: graphApi.centrality as unknown as Mock,
  timeline: timelineApi.get as unknown as Mock,
  reports: reportsApi.list as unknown as Mock,
  plans: collectionPlansApi.list as unknown as Mock,
  stix: exportApi.stix as unknown as Mock,
};

function refused(status: number, detail?: string): AxiosError {
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, null, {
    status,
    statusText: String(status),
    data: detail === undefined ? {} : { detail },
    headers: {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config: {} as any,
  });
}

const project = (extra: Record<string, unknown> = {}) => ({
  id: 'p1',
  name: 'Nightfall',
  description: 'APT infrastructure',
  priority: 'high',
  status: 'active',
  classification_level: 'UNCLASSIFIED',
  entity_count: 3,
  relationship_count: 2,
  document_count: 1,
  ...extra,
});

function projectLoads(extra: Record<string, unknown> = {}) {
  m.get.mockResolvedValue({ data: project(extra) });
  m.statistics.mockResolvedValue({ data: { nodes: 3, edges: 2, components: 1 } });
  m.centrality.mockResolvedValue({ data: [] });
  m.timeline.mockResolvedValue({ data: { events: [] } });
  m.reports.mockResolvedValue({ data: [] });
  m.plans.mockResolvedValue({ data: [] });
}

function everythingRefused() {
  const no = refused(403, 'No access to this project');
  for (const fn of [m.get, m.statistics, m.centrality, m.timeline, m.reports, m.plans]) fn.mockRejectedValue(no);
}

describe('project dashboard access', () => {
  beforeEach(() => {
    for (const fn of Object.values(m)) fn.mockReset();
    ctx.setActiveProject.mockReset();
    ctx.dropProject.mockReset();
    notify.mockReset();
  });

  it('renders a distinct no-access state for a 403, and drops the project', async () => {
    everythingRefused();
    render(<ProjectDashboard />);

    expect(await screen.findByRole('heading', { name: "You don't have access to this project" })).toBeInTheDocument();
    expect(screen.getByText(/restricted to its members/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Choose a project/ })).toHaveAttribute('href', '/');
    // Not the generic failure, whose Retry cannot help here.
    expect(screen.queryByText(/Could not load this project/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    expect(ctx.dropProject).toHaveBeenCalledWith('p1');
    expect(ctx.setActiveProject).not.toHaveBeenCalled();
    expect(m.members).not.toHaveBeenCalled();
  });

  it('treats a 403 from any of its reads as no access', async () => {
    projectLoads();
    m.statistics.mockRejectedValue(refused(403, 'No access to this project'));
    render(<ProjectDashboard />);

    expect(await screen.findByRole('heading', { name: "You don't have access to this project" })).toBeInTheDocument();
    expect(ctx.dropProject).toHaveBeenCalledWith('p1');
  });

  it('keeps the generic error for other failures', async () => {
    projectLoads();
    m.get.mockRejectedValue(refused(500));
    render(<ProjectDashboard />);

    expect(await screen.findByText(/Could not load this project/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByText("You don't have access to this project")).not.toBeInTheDocument();
    expect(ctx.dropProject).not.toHaveBeenCalled();
  });

  it("shows the analyst's role in the header", async () => {
    projectLoads({ my_role: 'editor', access: 'restricted' });
    m.members.mockResolvedValue({
      data: { access: 'restricted', my_role: 'editor', members: [{ username: 'alice', role: 'owner' }] },
    });
    render(<ProjectDashboard />);

    expect(await screen.findByText('Your role: Editor')).toBeInTheDocument();
    expect(screen.queryByText('Open to all analysts')).not.toBeInTheDocument();
    expect(ctx.setActiveProject).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1', my_role: 'editor' }));
  });

  it('marks an open project in the header', async () => {
    projectLoads({ my_role: null, access: 'open' });
    m.members.mockResolvedValue({ data: { access: 'open', my_role: null, members: [] } });
    render(<ProjectDashboard />);

    expect(await screen.findByRole('heading', { name: 'Project Overview' })).toBeInTheDocument();
    // In the header, and again in the members panel.
    await waitFor(() => expect(screen.getAllByText('Open to all analysts').length).toBeGreaterThanOrEqual(1));
    expect(screen.queryByText(/Your role:/)).not.toBeInTheDocument();
  });

  it('switches to the no-access state when the members list is refused', async () => {
    projectLoads({ my_role: 'viewer', access: 'restricted' });
    m.members.mockRejectedValue(refused(403, 'No access to this project'));
    render(<ProjectDashboard />);

    expect(await screen.findByRole('heading', { name: "You don't have access to this project" })).toBeInTheDocument();
    expect(screen.getByText(/Nightfall/)).toBeInTheDocument();
    expect(ctx.dropProject).toHaveBeenCalledWith('p1');
  });

  it('switches to the no-access state when the export is refused', async () => {
    projectLoads({ my_role: 'owner', access: 'restricted' });
    m.members.mockResolvedValue({ data: { access: 'restricted', my_role: 'owner', members: [] } });
    m.stix.mockRejectedValue(refused(403, 'No access to this project'));
    render(<ProjectDashboard />);

    fireEvent.click(await screen.findByRole('button', { name: 'Export Report' }));

    expect(await screen.findByRole('heading', { name: "You don't have access to this project" })).toBeInTheDocument();
    expect(notify).not.toHaveBeenCalledWith(expect.objectContaining({ title: 'Export Failed' }));
  });

  it('follows an access change made in the members panel', async () => {
    projectLoads({ my_role: null, access: 'open' });
    // The page loaded it open; by the time the panel asks, an owner was added.
    m.members.mockResolvedValue({
      data: { access: 'restricted', my_role: 'owner', members: [{ username: 'alice', role: 'owner' }] },
    });
    render(<ProjectDashboard />);

    expect(await screen.findByText('Your role: Owner')).toBeInTheDocument();
    expect(screen.queryByText('Open to all analysts')).not.toBeInTheDocument();
  });
});
