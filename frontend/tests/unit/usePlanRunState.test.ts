import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('@/lib/api', () => ({ collectionPlansApi: { executionStatus: vi.fn() } }));
import { collectionPlansApi } from '@/lib/api';
import { usePlanRunState } from '@/lib/usePlanRunState';
const mockStatus = collectionPlansApi.executionStatus as unknown as ReturnType<typeof vi.fn>;

/** The collection-plans page polls the selected plan only while its run is in flight. */
describe('usePlanRunState', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockStatus.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  async function flush() {
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  }

  it('polls while running, stops when the run ends, and says so once', async () => {
    mockStatus
      .mockResolvedValueOnce({ data: { plan_id: 'p1', status: 'running', job_status: 'queued' } })
      .mockResolvedValueOnce({ data: { plan_id: 'p1', status: 'running', job_status: 'running' } })
      .mockResolvedValue({ data: { plan_id: 'p1', status: 'completed', job_status: 'succeeded' } });
    const ended = vi.fn();
    const { result } = renderHook(() => usePlanRunState('p1', 1000, ended));
    await flush();
    expect(result.current.run?.job_status).toBe('queued');

    await act(async () => { vi.advanceTimersByTime(1000); });
    await flush();
    expect(result.current.run?.job_status).toBe('running');

    await act(async () => { vi.advanceTimersByTime(1000); });
    await flush();
    expect(result.current.run?.status).toBe('completed');
    expect(ended).toHaveBeenCalledTimes(1);

    const calls = mockStatus.mock.calls.length;
    await act(async () => { vi.advanceTimersByTime(5000); });
    await flush();
    expect(mockStatus.mock.calls.length).toBe(calls);
  });

  it('does not poll an idle plan', async () => {
    mockStatus.mockResolvedValue({ data: { plan_id: 'p1', status: 'idle' } });
    renderHook(() => usePlanRunState('p1', 1000));
    await flush();
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(mockStatus).toHaveBeenCalledTimes(1);
  });

  it("drops a previous plan's answer after the selection changes", async () => {
    let resolveFirst: (v: unknown) => void = () => {};
    mockStatus
      .mockImplementationOnce(() => new Promise((r) => { resolveFirst = r; }))
      .mockResolvedValue({ data: { plan_id: 'p2', status: 'idle' } });
    const { result, rerender } = renderHook(({ id }) => usePlanRunState(id, 1000), { initialProps: { id: 'p1' } });
    rerender({ id: 'p2' });
    await flush();
    resolveFirst({ data: { plan_id: 'p1', status: 'running' } });
    await flush();
    expect(result.current.run?.plan_id).toBe('p2');
  });
});
