import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type { PlanExecutionStatus } from '@/lib/api';
import { canCancelRun, executeNotice, isRunStopping, runBadge } from '@/lib/planRun';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  collectionPlansApi: { cancel: vi.fn() },
}));
import { collectionPlansApi } from '@/lib/api';
import { CancelRunButton, PlanRunBadge, RunDetails } from '@/components/PlanRunStatus';
const mockCancel = collectionPlansApi.cancel as unknown as ReturnType<typeof vi.fn>;

/**
 * Collection runs are jobs now (worker package): a queued run and a cancelled
 * run that is still winding down both read `running`, told apart by
 * `job_status`; POST /cancel stops a live run, and each run carries its own
 * degraded outcomes.
 */
const run = (over: Partial<PlanExecutionStatus>): PlanExecutionStatus => ({ plan_id: 'p1', status: 'idle', ...over });

describe('runBadge', () => {
  it.each([
    [run({ status: 'running', job_status: 'running' }), 'Collecting'],
    [run({ status: 'running', job_status: 'queued' }), 'Queued'],
    [run({ status: 'running', job_status: 'cancelled' }), 'Stopping'],
    [run({ status: 'stalled', seconds_since_heartbeat: 600 }), 'Stalled'],
    [run({ status: 'failed', error: 'Neo4j unavailable' }), 'Failed'],
    [run({ status: 'cancelled' }), 'Cancelled'],
  ])('labels %o as %s', (r, label) => {
    expect(runBadge(r)?.label).toBe(label);
  });

  it('shows nothing for an idle plan or a completed run', () => {
    expect(runBadge(run({ status: 'idle' }))).toBeNull();
    expect(runBadge(run({ status: 'completed' }))).toBeNull();
    expect(runBadge(undefined)).toBeNull();
  });

  it('says how long a stalled run has been silent, from its heartbeat', () => {
    expect(runBadge(run({ status: 'stalled', seconds_since_heartbeat: 600, seconds_since_last_event: 60 }))?.title)
      .toMatch(/^Silent for 10 min/);
  });

  it('gives a failed run its error', () => {
    expect(runBadge(run({ status: 'failed', error: 'Neo4j unavailable' }))?.title).toBe('Neo4j unavailable');
  });
});

describe('canCancelRun / isRunStopping', () => {
  it('offers cancel for a live, queued or stalled run but not one already stopping', () => {
    expect(canCancelRun(run({ status: 'running', job_status: 'running' }))).toBe(true);
    expect(canCancelRun(run({ status: 'running', job_status: 'queued' }))).toBe(true);
    expect(canCancelRun(run({ status: 'stalled' }))).toBe(true);
    expect(canCancelRun(run({ status: 'running', job_status: 'cancelled' }))).toBe(false);
    expect(canCancelRun(run({ status: 'completed' }))).toBe(false);
    expect(canCancelRun(null)).toBe(false);
    expect(isRunStopping(run({ status: 'running', job_status: 'cancelled' }))).toBe(true);
    expect(isRunStopping(run({ status: 'cancelled', job_status: 'cancelled' }))).toBe(false);
  });
});

describe('executeNotice', () => {
  it('is silent when the run simply started', () => {
    expect(executeNotice({ execution_status: 'started', message: 'Agentic execution started with 3 source(s).', warnings: [] })).toBeNull();
  });

  it('says why nothing runs, with the warnings', () => {
    expect(executeNotice({
      execution_status: 'no_executable_sources',
      message: 'Plan activated but no automated sources found.',
      warnings: ['1 file_upload source(s) require manual upload'],
    })).toBe('Plan activated but no automated sources found. 1 file_upload source(s) require manual upload.');
  });

  it('says a run is waiting for a worker, and what the budget left out', () => {
    expect(executeNotice({
      execution_status: 'queued', message: 'Agentic execution started with 5 source(s). Queued for a collection worker.',
      sources_over_budget: 2, warnings: [],
    })).toBe('Agentic execution started with 5 source(s). Queued for a collection worker. 2 source(s) exceed this run\'s source limit.');
  });
});

describe('PlanRunBadge', () => {
  it('renders the label with the reason as its title', () => {
    render(<PlanRunBadge run={run({ status: 'running', job_status: 'cancelled', message: 'Cancelling; the run stops before its next source' })} />);
    expect(screen.getByText('Stopping')).toHaveAttribute('title', 'Cancelling; the run stops before its next source');
  });
});

describe('CancelRunButton', () => {
  beforeEach(() => {
    mockCancel.mockReset();
  });

  it('is absent when there is nothing to cancel', () => {
    render(<CancelRunButton planId="p1" run={run({ status: 'completed' })} onCancelled={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
  });

  it('cancels the run without toggling the header it sits in', async () => {
    const result = { plan_id: 'p1', job_id: 'j1', status: 'cancelled', previous_status: 'running', stopping: true, message: 'Cancelled' };
    mockCancel.mockResolvedValue({ data: result });
    const onCancelled = vi.fn();
    const onHeaderClick = vi.fn();
    render(
      <div onClick={onHeaderClick}>
        <CancelRunButton planId="p1" run={run({ status: 'running', job_status: 'running' })} onCancelled={onCancelled} onError={vi.fn()} />
      </div>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(onCancelled).toHaveBeenCalledWith(result));
    expect(mockCancel).toHaveBeenCalledWith('p1');
    expect(onHeaderClick).not.toHaveBeenCalled();
  });

  it("reports the backend's reason when there is nothing live to cancel", async () => {
    mockCancel.mockRejectedValue(new AxiosError('Conflict', 'ERR_BAD_REQUEST', undefined, null, {
      status: 409, statusText: 'Conflict', data: { detail: 'No collection run is in flight for this plan' }, headers: {},
      config: {} as InternalAxiosRequestConfig,
    }));
    const onError = vi.fn();
    render(<CancelRunButton planId="p1" run={run({ status: 'stalled' })} onCancelled={vi.fn()} onError={onError} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith('Could not cancel the run: No collection run is in flight for this plan'));
  });
});

describe('RunDetails', () => {
  it("lists the run's degraded outcomes by subsystem", () => {
    render(<RunDetails run={run({ status: 'completed', degraded: { extraction: { llm_timeout: 2, llm_unparsed: 1 }, collection: { fetch_failed: 4 } } })} />);
    expect(screen.getByText('Degraded this run')).toBeInTheDocument();
    expect(screen.getByText('Collection')).toBeInTheDocument();
    expect(screen.getByText(/llm_timeout 2, llm_unparsed 1/)).toBeInTheDocument();
  });

  it('says why a run failed', () => {
    render(<RunDetails run={run({ status: 'failed', error: 'Neo4j unavailable', degraded: {} })} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Run failed: Neo4j unavailable');
  });

  it('renders nothing for a clean run', () => {
    const { container } = render(<RunDetails run={run({ status: 'completed', degraded: {} })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
