import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { readDegraded, readDegradedCounts, subsystemLabel, processLabel, type DegradedBody } from '@/lib/degraded';

vi.mock('@/lib/api', () => ({ adminApi: { degraded: vi.fn() } }));
import { adminApi } from '@/lib/api';
import DegradedCard from '@/components/DegradedCard';
const mockDegraded = adminApi.degraded as unknown as ReturnType<typeof vi.fn>;

/**
 * GET /api/admin/degraded (contract 3): `{since, processes: {api, worker},
 * total, history_available}` over the last 24 hours, each count map holding
 * only subsystems that degraded at least once. The card shows each process's
 * total, then one row per subsystem with the combined total, its split by
 * process and its top three reasons; it says plainly when nothing degraded,
 * and says so when the stored counts could not be read rather than passing
 * off the API's own counts as the whole picture.
 */
const SINCE = '2026-10-01T21:00:00+00:00';

/** What the API and the worker each counted, and their sum. */
const TWO_PROCESSES: DegradedBody = {
  since: SINCE,
  processes: {
    api: { extraction: { llm_timeout: 5, llm_unparsed: 4 }, enrichment: { provider_error: 3 } },
    worker: { extraction: { llm_timeout: 4, provider_error: 2, rate_limited: 1 }, collection: { source_failed: 2 } },
  },
  total: {
    extraction: { llm_timeout: 9, llm_unparsed: 4, provider_error: 2, rate_limited: 1 },
    enrichment: { provider_error: 3 },
    collection: { source_failed: 2 },
  },
  history_available: true,
};

/** The table could not be read: the API's unflushed counts only. */
const API_ONLY: DegradedBody = {
  since: SINCE,
  processes: { api: { llm: { report_call_failed: 1 } }, worker: {} },
  total: { llm: { report_call_failed: 1 } },
  history_available: false,
};

const NOTHING: DegradedBody = {
  since: SINCE,
  processes: { api: {}, worker: {} },
  total: {},
  history_available: true,
};

describe('readDegraded', () => {
  it('combines the processes, ordered by count, with each subsystem split by process', () => {
    const snap = readDegraded(TWO_PROCESSES);
    expect(snap.since).toBe(SINCE);
    expect(snap.historyAvailable).toBe(true);
    expect(snap.subsystems.map((s) => [s.subsystem, s.total, s.byProcess])).toEqual([
      ['extraction', 16, { api: 9, worker: 7 }],
      ['enrichment', 3, { api: 3, worker: 0 }],
      ['collection', 2, { api: 0, worker: 2 }],
    ]);
    expect(snap.subsystems[0].reasons.map((r) => r.reason)).toEqual([
      'llm_timeout', 'llm_unparsed', 'provider_error', 'rate_limited',
    ]);
  });

  it("keeps each process's own counts", () => {
    const { processes } = readDegraded(TWO_PROCESSES);
    expect(processes.api.total).toBe(12);
    expect(processes.worker.total).toBe(9);
    expect(processes.worker.subsystems.map((s) => [s.subsystem, s.total])).toEqual([
      ['extraction', 7], ['collection', 2],
    ]);
  });

  it('reads empty maps as nothing degraded', () => {
    const snap = readDegraded(NOTHING);
    expect(snap.subsystems).toEqual([]);
    expect(snap.processes).toEqual({ api: { total: 0, subsystems: [] }, worker: { total: 0, subsystems: [] } });
  });

  it('says when the stored counts were unavailable', () => {
    const snap = readDegraded(API_ONLY);
    expect(snap.historyAvailable).toBe(false);
    expect(snap.processes.api.total).toBe(1);
    expect(snap.processes.worker.total).toBe(0);
  });

  it('ignores non-count values instead of inventing totals', () => {
    const snap = readDegraded({
      ...NOTHING,
      processes: { api: { llm: { x: 'many', y: 0, z: 2 }, topics: [] }, worker: {} },
      total: { llm: { x: 'many', y: 0, z: 2 }, topics: [] },
    });
    expect(snap.subsystems).toEqual([
      { subsystem: 'llm', total: 2, reasons: [{ reason: 'z', count: 2 }], byProcess: { api: 2, worker: 0 } },
    ]);
  });

  it.each([
    ['null', null],
    ['a string', 'nope'],
    ['an array', [1, 2]],
    ['the per-process body that preceded it', { since: SINCE, extraction: { llm_timeout: 2 } }],
    ['a body without the worker', { ...NOTHING, processes: { api: {} } }],
    ['a body without history_available', { since: SINCE, processes: { api: {}, worker: {} }, total: {} }],
  ])('throws on %s rather than reporting "nothing degraded"', (_label, bad) => {
    expect(() => readDegraded(bad)).toThrow(/Unexpected degraded-outcomes response shape/);
  });

  it("reads a single count map, such as one run's own, and nothing as nothing", () => {
    expect(readDegradedCounts({ collection: { source_failed: 1 }, extraction: { nlp_fallback: 2 } })).toEqual([
      { subsystem: 'extraction', total: 2, reasons: [{ reason: 'nlp_fallback', count: 2 }] },
      { subsystem: 'collection', total: 1, reasons: [{ reason: 'source_failed', count: 1 }] },
    ]);
    expect(readDegradedCounts(null)).toEqual([]);
    expect(readDegradedCounts(undefined)).toEqual([]);
    expect(readDegradedCounts({})).toEqual([]);
  });

  it('names the known subsystems and the processes', () => {
    expect(subsystemLabel('attack_mapping')).toBe('ATT&CK mapping');
    expect(subsystemLabel('llm')).toBe('LLM');
    expect(subsystemLabel('new_thing')).toBe('new thing');
    expect(processLabel('api')).toBe('API');
    expect(processLabel('worker')).toBe('Worker');
  });
});

describe('DegradedCard', () => {
  // Braces: a function returned from beforeEach is run as a teardown, and
  // mockReset() returns the mock, which would be called once more after each test.
  beforeEach(() => {
    mockDegraded.mockReset();
  });

  async function rowsOf(name: string) {
    const list = await screen.findByRole('list', { name });
    return within(list).getAllByRole('listitem').filter((li) => li.parentElement === list);
  }

  it('shows each process, then one combined row per subsystem with its split and top three reasons', async () => {
    mockDegraded.mockResolvedValue({ data: TWO_PROCESSES });
    render(<DegradedCard />);

    const processes = await rowsOf('Degraded outcomes by process');
    expect(processes.map((li) => li.textContent)).toEqual(['API12', 'Worker9']);

    const rows = await rowsOf('Degraded outcomes by subsystem');
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText('Extraction')).toBeInTheDocument();
    expect(within(rows[0]).getByText('16')).toBeInTheDocument();
    expect(within(rows[0]).getByText('API 9 · Worker 7')).toBeInTheDocument();
    expect(within(rows[0]).getByText('llm_timeout')).toBeInTheDocument();
    expect(within(rows[0]).queryByText('rate_limited')).toBeNull();
    expect(within(rows[0]).getByText('+1 more reason')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Enrichment')).toBeInTheDocument();
    expect(within(rows[1]).getByText('API 3 · Worker 0')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Collection')).toBeInTheDocument();
    expect(within(rows[2]).getByText('API 0 · Worker 2')).toBeInTheDocument();

    expect(screen.getByText(/^Last 24 hours \(since /)).toBeInTheDocument();
    expect(screen.queryByRole('note')).toBeNull();
  });

  it("notes when stored counts are unavailable and does not pass the API's counts off as the worker's", async () => {
    mockDegraded.mockResolvedValue({ data: API_ONLY });
    render(<DegradedCard />);

    expect(await screen.findByRole('note')).toHaveTextContent(
      'Stored counts unavailable: showing this API process only.',
    );
    const processes = await rowsOf('Degraded outcomes by process');
    expect(processes.map((li) => li.textContent)).toEqual(['API1', 'Workerunavailable']);
    const rows = await rowsOf('Degraded outcomes by subsystem');
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText('LLM')).toBeInTheDocument();
    expect(within(rows[0]).queryByText(/Worker/)).toBeNull();
  });

  it('does not say "no degraded outcomes" when only the API process could be read', async () => {
    mockDegraded.mockResolvedValue({
      data: { ...API_ONLY, processes: { api: {}, worker: {} }, total: {} },
    });
    render(<DegradedCard />);

    expect(await screen.findByRole('note')).toHaveTextContent('Stored counts unavailable');
    expect(screen.getByText('Nothing counted by this API process since its last flush.')).toBeInTheDocument();
    expect(screen.queryByText(/No degraded outcomes/)).toBeNull();
  });

  it('says so when nothing degraded', async () => {
    mockDegraded.mockResolvedValue({ data: NOTHING });
    render(<DegradedCard />);
    expect(await screen.findByText(/^No degraded outcomes in the last 24 hours \(since /)).toBeInTheDocument();
    expect(screen.queryByRole('note')).toBeNull();
    expect(screen.queryByRole('list', { name: 'Degraded outcomes by process' })).toBeNull();
  });

  it('reports a failed load instead of an empty card', async () => {
    mockDegraded.mockRejectedValue(new Error('boom'));
    render(<DegradedCard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load: boom');
    expect(screen.queryByText(/No degraded outcomes/)).toBeNull();
  });

  it('reports a body of the old shape instead of an empty card', async () => {
    mockDegraded.mockResolvedValue({ data: { since: SINCE, extraction: { llm_timeout: 2 } } });
    render(<DegradedCard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Unexpected degraded-outcomes response shape.');
    expect(screen.queryByText(/No degraded outcomes/)).toBeNull();
  });
});
