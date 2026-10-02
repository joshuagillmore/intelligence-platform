import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AxiosError } from 'axios';
import ProjectsPage from '@/app/page';

/**
 * The projects list with per-project access: each project's role chip and
 * "Open to all analysts" badge (grid and list views), the signed-in analyst's
 * role in the header, no delete control for an editor or viewer, and a 403 on
 * the active project's watchlist dropping that project.
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
    projectsApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn(), batchDelete: vi.fn() },
    watchlistApi: { list: vi.fn() },
  };
});

import { projectsApi, watchlistApi } from '@/lib/api';
const mockList = projectsApi.list as unknown as ReturnType<typeof vi.fn>;
const mockWatchlist = watchlistApi.list as unknown as ReturnType<typeof vi.fn>;

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
