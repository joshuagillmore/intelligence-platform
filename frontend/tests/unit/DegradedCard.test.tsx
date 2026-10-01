import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { readDegraded, subsystemLabel } from '@/lib/degraded';

vi.mock('@/lib/api', () => ({ adminApi: { degraded: vi.fn() } }));
import { adminApi } from '@/lib/api';
import DegradedCard from '@/components/DegradedCard';
const mockDegraded = adminApi.degraded as unknown as ReturnType<typeof vi.fn>;

/**
 * GET /api/admin/degraded (contract 10): `{since, <subsystem>: {<reason>:
 * count}}`, only subsystems that degraded at least once. The card shows one row
 * per subsystem with its total and top three reasons, and says plainly when
 * nothing degraded rather than showing an empty box.
 */
const SINCE = '2026-09-30T21:00:00+00:00';

describe('readDegraded', () => {
  it('totals each subsystem and orders subsystems and reasons by count', () => {
    const snap = readDegraded({
      since: SINCE,
      embeddings: { width_mismatch: 1 },
      extraction: { llm_unparsed: 4, llm_timeout: 9, provider_error: 2 },
    });
    expect(snap.since).toBe(SINCE);
    expect(snap.subsystems.map((s) => [s.subsystem, s.total])).toEqual([['extraction', 15], ['embeddings', 1]]);
    expect(snap.subsystems[0].reasons.map((r) => r.reason)).toEqual(['llm_timeout', 'llm_unparsed', 'provider_error']);
  });

  it('reads a body with only `since` as nothing degraded', () => {
    expect(readDegraded({ since: SINCE }).subsystems).toEqual([]);
  });

  it('ignores non-count values instead of inventing totals', () => {
    const snap = readDegraded({ since: SINCE, llm: { x: 'many', y: 0, z: 2 }, topics: [] });
    expect(snap.subsystems).toEqual([{ subsystem: 'llm', total: 2, reasons: [{ reason: 'z', count: 2 }] }]);
  });

  it.each([null, 'nope', [1, 2]])('throws on %j rather than reporting "nothing degraded"', (bad) => {
    expect(() => readDegraded(bad)).toThrow(/Unexpected degraded-outcomes response shape/);
  });

  it('names the known subsystems', () => {
    expect(subsystemLabel('attack_mapping')).toBe('ATT&CK mapping');
    expect(subsystemLabel('llm')).toBe('LLM');
    expect(subsystemLabel('new_thing')).toBe('new thing');
  });
});

describe('DegradedCard', () => {
  // Braces: a function returned from beforeEach is run as a teardown, and
  // mockReset() returns the mock, which would be called once more after each test.
  beforeEach(() => {
    mockDegraded.mockReset();
  });

  it('shows one row per subsystem with its total and top three reasons', async () => {
    mockDegraded.mockResolvedValue({
      data: {
        since: SINCE,
        extraction: { llm_timeout: 9, llm_unparsed: 4, provider_error: 2, rate_limited: 1 },
        enrichment: { provider_error: 3 },
      },
    });
    render(<DegradedCard />);
    const list = await screen.findByRole('list', { name: 'Degraded outcomes by subsystem' });
    const rows = within(list).getAllByRole('listitem').filter((li) => li.parentElement === list);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Extraction')).toBeInTheDocument();
    expect(within(rows[0]).getByText('16')).toBeInTheDocument();
    expect(within(rows[0]).getByText('llm_timeout')).toBeInTheDocument();
    expect(within(rows[0]).queryByText('rate_limited')).toBeNull();
    expect(within(rows[0]).getByText('+1 more reason')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Enrichment')).toBeInTheDocument();
    expect(screen.getByText(/^Since /)).toBeInTheDocument();
  });

  it('says so when nothing degraded', async () => {
    mockDegraded.mockResolvedValue({ data: { since: SINCE } });
    render(<DegradedCard />);
    expect(await screen.findByText(/^No degraded outcomes since /)).toBeInTheDocument();
  });

  it('reports a failed load instead of an empty card', async () => {
    mockDegraded.mockRejectedValue(new Error('boom'));
    render(<DegradedCard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load: boom');
    expect(screen.queryByText(/No degraded outcomes/)).toBeNull();
  });
});
