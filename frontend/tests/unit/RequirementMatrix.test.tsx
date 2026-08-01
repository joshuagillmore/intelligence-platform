import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import PirPanel from '@/components/PirPanel';

/**
 * Per-element collection state in the PIR panel.
 *
 * Collection now re-tasks itself at whatever the planned sources left
 * unanswered, and the assessor records why each element is still open. None of
 * that was visible: the panel listed the criteria as flat bullets, so an
 * analyst could not tell an element the system tried and abandoned from one it
 * never attempted — which is the difference between "collect more" and "this
 * is not findable".
 */

vi.mock('@/lib/api', () => ({
  pirsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    requirements: vi.fn(),
  },
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { pirsApi } from '@/lib/api';
const mockList = pirsApi.list as unknown as ReturnType<typeof vi.fn>;
const mockRequirements = pirsApi.requirements as unknown as ReturnType<typeof vi.fn>;

const EEIS = ['Which vessels?', 'On what dates?', 'What tactics?'];

const pir = {
  id: 'pir-1',
  project_id: 'proj-1',
  title: 'Maritime activity',
  // Deliberately shares no wording with the EEIs below, so a query matching an
  // element cannot also match the requirement's own text.
  text: 'Characterise recent coercive activity in the disputed area.',
  refined_text: '',
  eeis: EEIS,
  priority: 'high',
  status: 'PARTIAL',
  created_by: 'analyst',
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
  plan_count: 0,
  plans: [],
};

const requirements = {
  pir_id: 'pir-1',
  project_id: 'proj-1',
  total: 3,
  counts: { satisfied: 1, unmet: 1, pending: 1 },
  elements: [
    {
      ordinal: 0, text: EEIS[0], status: 'satisfied', attempts: 1,
      queries_tried: ['CCG hull numbers'], missing: '', confidence: 'high',
    },
    {
      ordinal: 1, text: EEIS[1], status: 'unmet', attempts: 2,
      queries_tried: ['incident dates'], missing: 'no dates in the collected sources',
      confidence: 'high',
    },
    {
      ordinal: 2, text: EEIS[2], status: 'pending', attempts: 0,
      queries_tried: [], missing: '', confidence: '',
    },
  ],
};

function setup() {
  return render(<PirPanel projectId="proj-1" />);
}

describe('RequirementMatrix', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ data: [pir] });
    mockRequirements.mockResolvedValue({ data: requirements });
  });

  it('shows how many elements are answered', async () => {
    setup();
    expect(await screen.findByText(/1\/3 answered/)).toBeInTheDocument();
  });

  it('distinguishes an abandoned element from an open one', async () => {
    // The distinction the whole loop turns on: "gave up" means collection tried
    // and stopped, "open" means it was never attempted. Both appear in the
    // summary line and again on the element itself, which is intended.
    setup();
    await screen.findByText(/1\/3 answered/);
    expect(screen.getAllByText(/gave up/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/\bopen\b/).length).toBeGreaterThanOrEqual(1);
  });

  it("surfaces the assessor's reason for a gap", async () => {
    setup();
    expect(
      await screen.findByText(/no dates in the collected sources/),
    ).toBeInTheDocument();
  });

  it('reports how many attempts an abandoned element cost', async () => {
    setup();
    expect(await screen.findByText(/after 2/)).toBeInTheDocument();
  });

  it('does not show a gap reason for a satisfied element', async () => {
    setup();
    await screen.findByText(/1\/3 answered/);
    expect(screen.queryByText(/missing:.*CCG/)).not.toBeInTheDocument();
  });

  it('still lists the criteria when the state cannot be loaded', async () => {
    // A requirement's criteria must stay readable if the endpoint is down;
    // losing them entirely would be worse than losing the status colouring.
    mockRequirements.mockRejectedValue(new Error('endpoint down'));
    setup();
    for (const eei of EEIS) {
      expect(await screen.findByText(new RegExp(eei))).toBeInTheDocument();
    }
  });

  it('falls back to the plain list when no elements are returned', async () => {
    mockRequirements.mockResolvedValue({
      data: { ...requirements, total: 0, elements: [], counts: { satisfied: 0, unmet: 0, pending: 0 } },
    });
    setup();
    expect(await screen.findByText(new RegExp(EEIS[0]))).toBeInTheDocument();
    expect(screen.queryByText(/answered/)).not.toBeInTheDocument();
  });

  it('requests state for the PIR it is rendering', async () => {
    setup();
    await waitFor(() => expect(mockRequirements).toHaveBeenCalledWith('pir-1'));
  });
});
