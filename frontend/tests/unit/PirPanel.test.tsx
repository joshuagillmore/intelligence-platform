import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import PirPanel from '@/components/PirPanel';

// Mock the axios API client — PirPanel only uses `pirsApi`.
vi.mock('@/lib/api', () => ({
  pirsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    requirements: vi.fn(),
  },
}));

// The panel routes to /collections for the "Collect" action.
const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push }),
}));

import { pirsApi } from '@/lib/api';
const mockList = pirsApi.list as unknown as ReturnType<typeof vi.fn>;
const mockCreate = pirsApi.create as unknown as ReturnType<typeof vi.fn>;
const mockUpdate = pirsApi.update as unknown as ReturnType<typeof vi.fn>;

const samplePir = {
  id: 'pir-1',
  project_id: 'proj-1',
  title: 'Actor infrastructure',
  text: 'What infrastructure does the actor use for C2?',
  refined_text: '',
  eeis: [],
  priority: 'high',
  status: 'OPEN',
  created_by: 'analyst',
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
  plan_count: 1,
  plans: [
    { id: 'plan-1', name: 'PIR: C2 infrastructure', status: 'ACTIVE', source_count: 3, records_acquired: 12, created_at: '' },
  ],
};

describe('PirPanel', () => {
  beforeEach(() => {
    mockList.mockReset();
    mockCreate.mockReset();
    mockUpdate.mockReset();
    nav.push.mockReset();
  });

  it('lists the project requirements with status and the plans they drove', async () => {
    mockList.mockResolvedValue({ data: [samplePir] });
    render(<PirPanel projectId="proj-1" />);

    await waitFor(() => expect(mockList).toHaveBeenCalledWith('proj-1'));
    expect(await screen.findByText('Actor infrastructure')).toBeInTheDocument();
    expect(screen.getByText('What infrastructure does the actor use for C2?')).toBeInTheDocument();
    // The chain forward: the collection plan raised against this PIR.
    expect(screen.getByText(/PIR: C2 infrastructure/)).toBeInTheDocument();
    // 1 outstanding of 1 — OPEN counts as outstanding.
    expect(screen.getByText(/1 outstanding of 1/)).toBeInTheDocument();
  });

  it('prompts the analyst when the project has no requirements', async () => {
    mockList.mockResolvedValue({ data: [] });
    render(<PirPanel projectId="proj-1" />);
    expect(await screen.findByText(/No requirements yet/)).toBeInTheDocument();
  });

  it('creates a requirement and reloads the list', async () => {
    mockList.mockResolvedValue({ data: [] });
    mockCreate.mockResolvedValue({ data: samplePir });
    render(<PirPanel projectId="proj-1" />);

    fireEvent.click(await screen.findByText('New PIR'));
    fireEvent.change(screen.getByPlaceholderText(/The intelligence question/), {
      target: { value: 'Who funds the network?' },
    });
    fireEvent.click(screen.getByText('Add requirement'));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith(expect.objectContaining({
      project_id: 'proj-1',
      text: 'Who funds the network?',
      priority: 'medium',
      status: 'OPEN',
    })));
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
  });

  it('marks a requirement satisfied', async () => {
    mockList.mockResolvedValue({ data: [samplePir] });
    mockUpdate.mockResolvedValue({ data: { ...samplePir, status: 'SATISFIED' } });
    render(<PirPanel projectId="proj-1" />);

    const statusSelect = await screen.findByLabelText('PIR status');
    fireEvent.change(statusSelect, { target: { value: 'SATISFIED' } });

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith('pir-1', { status: 'SATISFIED' }));
  });

  it('hands the requirement to the collection workflow', async () => {
    mockList.mockResolvedValue({ data: [samplePir] });
    render(<PirPanel projectId="proj-1" />);

    fireEvent.click(await screen.findByRole('button', { name: /Collect/ }));
    expect(nav.push).toHaveBeenCalledWith('/collections?pir=pir-1');
  });
});
