import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AxiosError } from 'axios';
import ProjectsPage from '@/app/page';

/**
 * The projects list with per-project access: each project's role chip and
 * "Open to all analysts" badge (grid and list views), the signed-in analyst's
 * role in the header, no delete control for an editor or viewer, a 403 on
 * the active project's watchlist dropping that project, and (for an admin)
 * the open-projects banner and the Claim control that restricts one.
 */

const ctx = vi.hoisted(() => ({
  activeProject: null as null | { id: string; name: string },
  setActiveProject: vi.fn(),
  dropProject: vi.fn(),
}));
vi.mock('@/lib/ProjectContext', () => ({ useProject: () => ctx }));
const session = vi.hoisted(() => ({ user: { username: 'alice', role: 'analyst' } as { username: string; role: string } | null }));
vi.mock('@/lib/SessionContext', () => ({ useSession: () => session }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
const notify = vi.hoisted(() => vi.fn());
vi.mock('@/components/NotificationProvider', () => ({
  useNotifications: () => ({ addNotification: notify }),
}));
vi.mock('@/components/Sidebar', () => ({ default: () => null }));

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...real,
    projectsApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn(), batchDelete: vi.fn(), claim: vi.fn() },
    watchlistApi: { list: vi.fn() },
  };
});

import { projectsApi, watchlistApi } from '@/lib/api';
const mockList = projectsApi.list as unknown as ReturnType<typeof vi.fn>;
const mockWatchlist = watchlistApi.list as unknown as ReturnType<typeof vi.fn>;
const mockClaim = projectsApi.claim as unknown as ReturnType<typeof vi.fn>;

const base = {
  description: '',
  priority: 'medium',
  status: 'active',
  classification_level: 'U',
  entity_count: 1,
  relationship_count: 0,
  document_count: 1,
  created_at: '2026-09-01T00:00:00+00:00',
  updated_at: '2026-09-01T00:00:00+00:00',
};

const projects = [
  { ...base, id: 'p1', name: 'Owned', my_role: 'owner', access: 'restricted' },
  { ...base, id: 'p2', name: 'Shared', my_role: 'viewer', access: 'restricted' },
  { ...base, id: 'p3', name: 'Legacy', my_role: null, access: 'open' },
];

function card(name: string): HTMLElement {
  const heading = screen.getByRole('heading', { name });
  return heading.parentElement as HTMLElement;
}

describe('projects list access', () => {
  beforeEach(() => {
    mockList.mockReset();
    mockWatchlist.mockReset();
    mockClaim.mockReset();
    ctx.activeProject = null;
    ctx.setActiveProject.mockReset();
    ctx.dropProject.mockReset();
    session.user = { username: 'alice', role: 'analyst' };
    notify.mockReset();
    mockList.mockResolvedValue({ data: projects });
  });

  it("shows each project's role and marks open projects", async () => {
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Owned' });

    expect(within(card('Owned')).getByText('Owner')).toBeInTheDocument();
    expect(within(card('Shared')).getByText('Viewer')).toBeInTheDocument();
    expect(within(card('Legacy')).getByText('Open to all analysts')).toBeInTheDocument();
    expect(within(card('Owned')).queryByText('Open to all analysts')).not.toBeInTheDocument();
    // An open project's non-member holds no role: no chip, just the badge.
    expect(within(card('Legacy')).queryByText(/^(Owner|Editor|Viewer)$/)).not.toBeInTheDocument();
  });

  it('offers delete only where the analyst may delete', async () => {
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Owned' });

    expect(within(card('Owned')).getByTitle('Delete project')).toBeInTheDocument();
    expect(within(card('Legacy')).getByTitle('Delete project')).toBeInTheDocument();
    expect(within(card('Shared')).queryByTitle('Delete project')).not.toBeInTheDocument();
  });

  it('shows the access column in the list view', async () => {
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Owned' });
    fireEvent.click(screen.getByRole('button', { name: 'List view' }));

    expect(screen.getByRole('columnheader', { name: 'Access' })).toBeInTheDocument();
    const row = screen.getByText('Shared').closest('tr') as HTMLElement;
    expect(within(row).getByText('Viewer')).toBeInTheDocument();
    const legacy = screen.getByText('Legacy').closest('tr') as HTMLElement;
    expect(within(legacy).getByText('Open to all analysts')).toBeInTheDocument();
  });

  it("shows the analyst's role in the header", async () => {
    render(<ProjectsPage />);
    expect(await screen.findByText('alice')).toBeInTheDocument();
    expect(screen.getByText('analyst')).toBeInTheDocument();
  });

  it('says an admin owns every project', async () => {
    session.user = { username: 'root', role: 'admin' };
    render(<ProjectsPage />);
    expect(await screen.findByText('admin (owner of every project)')).toBeInTheDocument();
  });

  it("drops the active project when its watchlist answers 403", async () => {
    ctx.activeProject = { id: 'p9', name: 'Gone' };
    mockWatchlist.mockRejectedValue(
      new AxiosError('Forbidden', 'ERR_BAD_REQUEST', undefined, null, {
        status: 403,
        statusText: 'Forbidden',
        data: { detail: 'No access to this project' },
        headers: {},
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        config: {} as any,
      }),
    );
    render(<ProjectsPage />);

    await waitFor(() => expect(ctx.dropProject).toHaveBeenCalledWith('p9'));
    expect(screen.queryByText(/Could not load this project's watched entities/)).not.toBeInTheDocument();
  });

  it("surfaces the backend's reason when a delete is refused", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    (projectsApi.delete as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new AxiosError('Forbidden', 'ERR_BAD_REQUEST', undefined, null, {
        status: 403,
        statusText: 'Forbidden',
        data: { detail: 'No access to this project' },
        headers: {},
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        config: {} as any,
      }),
    );
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });

    fireEvent.click(within(card('Legacy')).getByTitle('Delete project'));

    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', message: '"Legacy" could not be deleted: No access to this project' }),
      ),
    );
  });
});

describe('open projects for an admin', () => {
  const twoOpen = [
    ...projects,
    { ...base, id: 'p4', name: 'Orphan', my_role: null, access: 'open' },
  ];

  function conflict(detail: string) {
    return new AxiosError('Conflict', 'ERR_BAD_REQUEST', undefined, null, {
      status: 409,
      statusText: 'Conflict',
      data: { detail },
      headers: {},
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      config: {} as any,
    });
  }

  beforeEach(() => {
    mockList.mockReset();
    mockWatchlist.mockReset();
    mockClaim.mockReset();
    vi.restoreAllMocks();
    notify.mockReset();
    ctx.activeProject = null;
    session.user = { username: 'root', role: 'admin' };
    // An admin's rows: owner everywhere, and `access` says which are open.
    mockList.mockResolvedValue({
      data: twoOpen.map((p) => ({ ...p, my_role: 'owner' })),
    });
  });

  it('tells an admin how many projects are open and offers to claim each', async () => {
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });

    expect(screen.getByRole('status')).toHaveTextContent(
      '2 open projects: anyone signed in can use them. Claim them to restrict access.',
    );
    expect(within(card('Legacy')).getByRole('button', { name: 'Claim Legacy' })).toBeInTheDocument();
    expect(within(card('Orphan')).getByRole('button', { name: 'Claim Orphan' })).toBeInTheDocument();
    expect(within(card('Owned')).queryByRole('button', { name: /^Claim/ })).not.toBeInTheDocument();
  });

  it('words the banner for a single open project', async () => {
    mockList.mockResolvedValue({ data: projects.map((p) => ({ ...p, my_role: 'owner' })) });
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });

    expect(screen.getByRole('status')).toHaveTextContent(
      '1 open project: anyone signed in can use it. Claim it to restrict access.',
    );
  });

  it('shows no banner when nothing is open', async () => {
    mockList.mockResolvedValue({
      data: projects.map((p) => ({ ...p, my_role: 'owner', access: 'restricted' })),
    });
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });

    expect(screen.queryByText(/open projects?:/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Claim/ })).not.toBeInTheDocument();
  });

  it('shows a non-admin neither the banner nor the control', async () => {
    session.user = { username: 'alice', role: 'analyst' };
    mockList.mockResolvedValue({ data: twoOpen });
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });

    expect(screen.queryByText(/open projects?:/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Claim/ })).not.toBeInTheDocument();
    // The per-project badge is unchanged.
    expect(within(card('Legacy')).getByText('Open to all analysts')).toBeInTheDocument();
  });

  it('claims a project and re-reads the list', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockClaim.mockResolvedValue({
      data: { username: 'root', role: 'owner', added_by: 'root', added_at: '2026-10-02T00:00:00+00:00' },
    });
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });
    expect(mockList).toHaveBeenCalledTimes(1);

    // After the claim, the backend reports Legacy restricted.
    mockList.mockResolvedValue({
      data: twoOpen.map((p) => ({ ...p, my_role: 'owner', access: p.id === 'p3' ? 'restricted' : p.access })),
    });
    fireEvent.click(within(card('Legacy')).getByRole('button', { name: 'Claim Legacy' }));

    await waitFor(() => expect(mockClaim).toHaveBeenCalledWith('p3'));
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(within(card('Legacy')).queryByRole('button', { name: 'Claim Legacy' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('status')).toHaveTextContent('1 open project');
    expect(within(card('Legacy')).queryByText('Open to all analysts')).not.toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'success', title: 'Project claimed' }));
  });

  it('claims from the list view too', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockClaim.mockResolvedValue({ data: {} });
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });
    fireEvent.click(screen.getByRole('button', { name: 'List view' }));

    const row = screen.getByText('Orphan').closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Claim Orphan' }));

    await waitFor(() => expect(mockClaim).toHaveBeenCalledWith('p4'));
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
  });

  it('does nothing when the admin cancels', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });

    fireEvent.click(within(card('Legacy')).getByRole('button', { name: 'Claim Legacy' }));

    expect(mockClaim).not.toHaveBeenCalled();
    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it("reports the backend's reason when a claim is refused", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockClaim.mockRejectedValue(conflict('This project already has members, so it cannot be claimed'));
    render(<ProjectsPage />);
    await screen.findByRole('heading', { name: 'Legacy' });

    fireEvent.click(within(card('Legacy')).getByRole('button', { name: 'Claim Legacy' }));

    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'error',
          title: 'Could not claim "Legacy"',
          message: 'This project already has members, so it cannot be claimed',
        }),
      ),
    );
    expect(mockList).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(within(card('Legacy')).getByRole('button', { name: 'Claim Legacy' })).not.toBeDisabled(),
    );
  });
});
