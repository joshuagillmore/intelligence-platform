import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AxiosError } from 'axios';
import ProjectMembersPanel from '@/components/ProjectMembersPanel';

/**
 * The members panel over a mocked API (contract 3): what an owner and a viewer
 * are offered, the add / change-role / remove flows, the inline rule before
 * the first add, and the backend's 403 and 409 reasons reaching the analyst
 * through the notification path.
 */

const notify = vi.hoisted(() => vi.fn());
vi.mock('@/components/NotificationProvider', () => ({
  useNotifications: () => ({ addNotification: notify }),
}));
vi.mock('@/lib/SessionContext', () => ({
  useSession: () => ({ user: { username: 'alice', role: 'analyst' } }),
}));
vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...real,
    projectsApi: { members: vi.fn(), setMemberRole: vi.fn(), removeMember: vi.fn() },
  };
});

import { projectsApi } from '@/lib/api';
const mockMembers = projectsApi.members as unknown as ReturnType<typeof vi.fn>;
const mockSetRole = projectsApi.setMemberRole as unknown as ReturnType<typeof vi.fn>;
const mockRemove = projectsApi.removeMember as unknown as ReturnType<typeof vi.fn>;

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

const restricted = (myRole: 'owner' | 'editor' | 'viewer' | null) => ({
  data: {
    access: 'restricted',
    my_role: myRole,
    members: [
      { username: 'alice', role: 'owner', added_by: 'admin', added_at: '2026-09-01T00:00:00+00:00' },
      { username: 'bob', role: 'viewer', added_by: 'alice', added_at: '2026-09-02T00:00:00+00:00' },
    ],
  },
});

const open = { data: { access: 'open', my_role: null, members: [] } };

describe('ProjectMembersPanel', () => {
  beforeEach(() => {
    mockMembers.mockReset();
    mockSetRole.mockReset();
    mockRemove.mockReset();
    notify.mockReset();
    vi.restoreAllMocks();
  });

  it('gives an owner the member controls', async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    render(<ProjectMembersPanel projectId="p1" />);

    expect(await screen.findByLabelText('Role for bob')).toBeInTheDocument();
    expect(screen.getByLabelText('Role for alice')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove bob' })).toBeInTheDocument();
    expect(screen.getByLabelText('Username to add')).toBeInTheDocument();
    expect(screen.getByText('You: Owner')).toBeInTheDocument();
    expect(screen.getByText('(you)')).toBeInTheDocument();
    expect(screen.queryByText(/Only an owner of this project/)).not.toBeInTheDocument();
    expect(mockMembers).toHaveBeenCalledWith('p1');
  });

  it('shows a viewer the members read-only, with no controls', async () => {
    mockMembers.mockResolvedValue(restricted('viewer'));
    render(<ProjectMembersPanel projectId="p1" />);

    const list = await screen.findByRole('list', { name: 'Project members' });
    expect(within(list).getByText('bob')).toBeInTheDocument();
    expect(within(list).getByText('Owner')).toBeInTheDocument();
    expect(within(list).getByText('Viewer')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Username to add')).not.toBeInTheDocument();
    expect(screen.getByText(/Only an owner of this project can add, change or remove members/)).toBeInTheDocument();
  });

  it('hides the controls from an editor too', async () => {
    mockMembers.mockResolvedValue(restricted('editor'));
    render(<ProjectMembersPanel projectId="p1" />);
    await screen.findByRole('list', { name: 'Project members' });
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Username to add')).not.toBeInTheDocument();
  });

  it('states the first-member rule before the first add and only offers owner', async () => {
    mockMembers.mockResolvedValue(open);
    const onAccessChange = vi.fn();
    render(<ProjectMembersPanel projectId="p1" onAccessChange={onAccessChange} />);

    const rule = await screen.findByText(/The first member must be an owner/);
    const input = screen.getByLabelText('Username to add');
    // Stated before the form, not discovered from a refusal.
    expect(rule.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const role = screen.getByLabelText('Role for the new member') as HTMLSelectElement;
    expect(role.value).toBe('owner');
    expect(role).toBeDisabled();
    expect(screen.getByText('Open to all analysts')).toBeInTheDocument();
    expect(onAccessChange).toHaveBeenCalledWith('open', null);
  });

  it('adds the first owner, then re-reads the members', async () => {
    mockMembers.mockResolvedValueOnce(open).mockResolvedValueOnce({
      data: {
        access: 'restricted',
        my_role: null,
        members: [{ username: 'carol', role: 'owner', added_by: 'alice', added_at: '2026-10-01T00:00:00+00:00' }],
      },
    });
    mockSetRole.mockResolvedValue({ data: {} });
    const onAccessChange = vi.fn();
    render(<ProjectMembersPanel projectId="p1" onAccessChange={onAccessChange} />);

    fireEvent.change(await screen.findByLabelText('Username to add'), { target: { value: ' carol ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add owner' }));

    await waitFor(() => expect(mockSetRole).toHaveBeenCalledWith('p1', 'carol', 'owner'));
    await waitFor(() => expect(mockMembers).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('carol')).toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'success', title: 'Member added' }));
    // Not an owner and no longer open: the controls go away.
    expect(onAccessChange).toHaveBeenLastCalledWith('restricted', null);
    expect(screen.queryByLabelText('Username to add')).not.toBeInTheDocument();
  });

  it('adds a later member with the chosen role', async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    mockSetRole.mockResolvedValue({ data: {} });
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.change(await screen.findByLabelText('Username to add'), { target: { value: 'dave' } });
    fireEvent.change(screen.getByLabelText('Role for the new member'), { target: { value: 'viewer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }));

    await waitFor(() => expect(mockSetRole).toHaveBeenCalledWith('p1', 'dave', 'viewer'));
    expect(screen.queryByText(/The first member must be an owner/)).not.toBeInTheDocument();
  });

  it("changes a member's role and re-reads the members", async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    mockSetRole.mockResolvedValue({ data: {} });
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.change(await screen.findByLabelText('Role for bob'), { target: { value: 'editor' } });

    await waitFor(() => expect(mockSetRole).toHaveBeenCalledWith('p1', 'bob', 'editor'));
    await waitFor(() => expect(mockMembers).toHaveBeenCalledTimes(2));
  });

  it('removes a member after confirmation', async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    mockRemove.mockResolvedValue({ data: { status: 'removed' } });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Remove bob' }));

    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith('p1', 'bob'));
    await waitFor(() => expect(mockMembers).toHaveBeenCalledTimes(2));
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'success', title: 'Member removed' }));
  });

  it('does nothing when the removal is not confirmed', async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Remove bob' }));
    expect(mockRemove).not.toHaveBeenCalled();
  });

  it("surfaces the backend's 409 when removing the last owner", async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    mockRemove.mockRejectedValue(refused(409, 'A project must keep at least one owner'));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Remove alice' }));

    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith({
        type: 'error',
        title: 'Could not remove alice',
        message: 'A project must keep at least one owner',
      }),
    );
    // Still listed: nothing was patched optimistically.
    expect(screen.getByLabelText('Role for alice')).toHaveValue('owner');
  });

  it("surfaces the backend's 409 when demoting the last owner", async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    mockSetRole.mockRejectedValue(refused(409, 'A project must keep at least one owner'));
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.change(await screen.findByLabelText('Role for alice'), { target: { value: 'viewer' } });

    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', message: 'A project must keep at least one owner' }),
      ),
    );
    expect(screen.getByLabelText('Role for alice')).toHaveValue('owner');
  });

  it("surfaces the backend's 403 on an attempted write, without leaving the panel", async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    mockSetRole.mockRejectedValue(refused(403, 'No access to this project'));
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.change(await screen.findByLabelText('Username to add'), { target: { value: 'eve' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }));

    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith({
        type: 'error',
        title: 'Could not add eve',
        message: 'No access to this project',
      }),
    );
    // A refused write is a notification, not the no-access state.
    expect(screen.getByLabelText('Username to add')).toBeInTheDocument();
  });

  it('names an unknown user from the backend detail', async () => {
    mockMembers.mockResolvedValue(restricted('owner'));
    mockSetRole.mockRejectedValue(refused(404, 'No such user'));
    render(<ProjectMembersPanel projectId="p1" />);

    fireEvent.change(await screen.findByLabelText('Username to add'), { target: { value: 'ghost' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }));

    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'error', message: 'No such user' })),
    );
  });

  it('reports a 403 on load as no access, not as a load error', async () => {
    mockMembers.mockRejectedValue(refused(403, 'No access to this project'));
    const onNoAccess = vi.fn();
    render(<ProjectMembersPanel projectId="p1" onNoAccess={onNoAccess} />);

    expect(await screen.findByText(/You don't have access to this project/)).toBeInTheDocument();
    expect(onNoAccess).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Could not load members/)).not.toBeInTheDocument();
  });

  it('reports any other load failure with a retry', async () => {
    mockMembers.mockRejectedValueOnce(refused(500)).mockResolvedValueOnce(restricted('owner'));
    const onNoAccess = vi.fn();
    render(<ProjectMembersPanel projectId="p1" onNoAccess={onNoAccess} />);

    expect(await screen.findByText(/Could not load members/)).toBeInTheDocument();
    expect(onNoAccess).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByLabelText('Role for bob')).toBeInTheDocument();
  });

  it('refuses a body without a member list instead of showing an empty project', async () => {
    mockMembers.mockResolvedValue({ data: { access: 'restricted', my_role: 'owner' } });
    render(<ProjectMembersPanel projectId="p1" />);
    expect(await screen.findByText(/Unexpected members response shape/)).toBeInTheDocument();
    expect(screen.queryByText(/The first member must be an owner/)).not.toBeInTheDocument();
  });
});
