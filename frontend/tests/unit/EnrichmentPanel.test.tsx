import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import EnrichmentPanel from '@/components/EnrichmentPanel';

vi.mock('@/lib/api', () => ({
  enrichmentApi: { getCached: vi.fn(), investigate: vi.fn() },
}));

import { enrichmentApi } from '@/lib/api';
const getCached = enrichmentApi.getCached as unknown as ReturnType<typeof vi.fn>;
const investigate = enrichmentApi.investigate as unknown as ReturnType<typeof vi.fn>;

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

describe('EnrichmentPanel cached status', () => {
  beforeEach(() => {
    getCached.mockReset();
    investigate.mockReset();
  });

  it('does not label a provider "cached" when its payload is null (a cache miss)', async () => {
    getCached.mockResolvedValue({ data: { cached: { geoip: null, dns: null, rdap: null } } });
    render(<EnrichmentPanel entityId="ip-1" entityType="IPAddress" />);
    await waitFor(() => expect(getCached).toHaveBeenCalledWith('ip-1'));
    // Let the effect's promise settle.
    await act(async () => {});
    expect(screen.queryByText(/geoip: cached/)).toBeNull();
    expect(screen.queryByText(/dns: cached/)).toBeNull();
    expect(screen.getByText(/No enrichment yet/)).toBeInTheDocument();
  });

  it('shows only the providers that actually have a cached payload', async () => {
    getCached.mockResolvedValue({ data: { cached: { geoip: { country: 'NL' }, dns: null } } });
    render(<EnrichmentPanel entityId="ip-1" entityType="IPAddress" />);
    expect(await screen.findByText(/geoip: cached/)).toBeInTheDocument();
    expect(screen.queryByText(/dns:/)).toBeNull();
  });
});

describe('EnrichmentPanel provider outcomes', () => {
  beforeEach(() => {
    getCached.mockReset();
    investigate.mockReset();
  });

  // A provider that failed or was skipped is neither "ok" nor "cached", and
  // the analyst needs the reason (Tor mode, rate limit, lookup failed).
  it('shows error and skipped providers as their own chips, with the reason', async () => {
    getCached.mockResolvedValue({ data: { cached: {} } });
    investigate.mockResolvedValue({
      data: {
        providers: {
          geoip: { status: 'skipped', reason: 'not used over Tor' },
          nvd: { status: 'error', reason: 'lookup failed' },
          dns: { status: 'ok' },
        },
      },
    });
    render(<EnrichmentPanel entityId="ip-1" entityType="IPAddress" />);
    fireEvent.click(screen.getByRole('button', { name: /Investigate/ }));

    const skipped = await screen.findByText(/geoip: skipped/);
    expect(skipped).toHaveTextContent('not used over Tor');
    expect(screen.getByText(/nvd: error/)).toHaveTextContent('lookup failed');
    expect(screen.getByText(/dns: ok/)).toBeInTheDocument();
    expect(screen.queryByText(/geoip: (ok|cached)/)).toBeNull();
    // Distinct styling: a skip is not painted as a failure, nor as success.
    expect(skipped.className).not.toBe(screen.getByText(/nvd: error/).className);
    expect(skipped.className).not.toBe(screen.getByText(/dns: ok/).className);
  });
});

describe('EnrichmentPanel CVSS', () => {
  beforeEach(() => {
    getCached.mockReset();
    getCached.mockResolvedValue({ data: { cached: {} } });
  });

  // `severity` is now the combined KEV/NVD rating; beside the CVSS score the
  // panel must show NVD's own rating, not KEV's "critical".
  it('labels the CVSS score with cvss_severity, not the combined severity', () => {
    render(
      <EnrichmentPanel
        entityId="cve-1"
        entityType="Vulnerability"
        properties={{ cvss_score: 7.5, cvss_severity: 'high', severity: 'critical', known_exploited: true }}
      />,
    );
    expect(screen.getByText(/7\.5 \(high\)/)).toBeInTheDocument();
    expect(screen.queryByText(/7\.5 \(critical\)/)).toBeNull();
  });

  it('shows the bare score when NVD gave no rating', () => {
    render(
      <EnrichmentPanel
        entityId="cve-2"
        entityType="Vulnerability"
        properties={{ cvss_score: 5.1, severity: 'critical' }}
      />,
    );
    expect(screen.getByText(/5\.1/)).toBeInTheDocument();
    expect(screen.queryByText(/\(critical\)/)).toBeNull();
  });
});

describe('EnrichmentPanel when the entity changes', () => {
  beforeEach(() => {
    getCached.mockReset();
    investigate.mockReset();
  });

  it('does not carry the previous entity\'s provider status to the next one', async () => {
    getCached.mockImplementation(async (id: string) =>
      id === 'ip-a'
        ? { data: { cached: { geoip: { country: 'NL' } } } }
        : { data: { cached: {} } },
    );
    const { rerender } = render(<EnrichmentPanel entityId="ip-a" entityType="IPAddress" />);
    expect(await screen.findByText(/geoip: cached/)).toBeInTheDocument();

    rerender(<EnrichmentPanel entityId="ip-b" entityType="IPAddress" />);
    await waitFor(() => expect(getCached).toHaveBeenCalledWith('ip-b'));
    await act(async () => {});
    expect(screen.queryByText(/geoip: cached/)).toBeNull();
  });

  it('ignores a run that finishes after the analyst moved to another entity', async () => {
    getCached.mockResolvedValue({ data: { cached: {} } });
    const run = deferred<{ data: { providers: Record<string, { status: string }> } }>();
    investigate.mockReturnValue(run.promise);
    const onEnriched = vi.fn();

    const { rerender } = render(
      <EnrichmentPanel entityId="ip-a" entityType="IPAddress" onEnriched={onEnriched} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Investigate/ }));
    expect(investigate).toHaveBeenCalledWith('ip-a');

    rerender(<EnrichmentPanel entityId="ip-b" entityType="IPAddress" onEnriched={onEnriched} />);
    await act(async () => {
      run.resolve({ data: { providers: { geoip: { status: 'ok' } } } });
    });

    expect(screen.queryByText(/geoip: ok/)).toBeNull();
    expect(onEnriched).not.toHaveBeenCalled();
    // The new entity's button is usable, not stuck on the old run's busy state.
    expect(screen.getByRole('button', { name: /^Investigate$/ })).not.toBeDisabled();
  });

  it('applies a run that finishes while the same entity is still shown', async () => {
    getCached.mockResolvedValue({ data: { cached: {} } });
    investigate.mockResolvedValue({ data: { providers: { geoip: { status: 'ok' } } } });
    const onEnriched = vi.fn();
    render(<EnrichmentPanel entityId="ip-a" entityType="IPAddress" onEnriched={onEnriched} />);
    fireEvent.click(screen.getByRole('button', { name: /Investigate/ }));
    expect(await screen.findByText(/geoip: ok/)).toBeInTheDocument();
    expect(onEnriched).toHaveBeenCalledTimes(1);
  });
});
