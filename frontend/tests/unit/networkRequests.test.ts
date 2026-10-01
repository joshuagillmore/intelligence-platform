import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  createRequestSequencer,
  useDebouncedValue,
} from '@/app/network/graphFilters';

/**
 * Request hygiene for the network page (findings P-4, P-5): a keystroke must
 * not fan out requests, and a slow response must not overwrite a newer one.
 * (P-12's per-document evidence loop is gone: one GET /entities/{id}/documents
 * replaced it; see readEntityDocuments.test.ts.)
 */

afterEach(() => {
  vi.useRealTimers();
});

describe('createRequestSequencer', () => {
  it('only the latest token is current', () => {
    const seq = createRequestSequencer();
    const first = seq.next();
    expect(seq.isCurrent(first)).toBe(true);
    const second = seq.next();
    expect(seq.isCurrent(first)).toBe(false);
    expect(seq.isCurrent(second)).toBe(true);
  });

  it('drops a slow response that lands after a newer one', async () => {
    const seq = createRequestSequencer();
    const applied: string[] = [];
    const request = (value: string, ms: number) => {
      const token = seq.next();
      return new Promise<void>(resolve => setTimeout(() => {
        if (seq.isCurrent(token)) applied.push(value);
        resolve();
      }, ms));
    };
    vi.useFakeTimers();
    const slow = request('ac', 50);   // typed "ac", slow server
    const fast = request('acm', 10);  // typed "acm", fast server
    await vi.advanceTimersByTimeAsync(60);
    await Promise.all([slow, fast]);
    expect(applied).toEqual(['acm']);
  });
});

describe('useDebouncedValue', () => {
  it('holds the value until it has been still for the delay', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useDebouncedValue(v, 300), {
      initialProps: { v: '' },
    });
    rerender({ v: 'a' });
    rerender({ v: 'ac' });
    rerender({ v: 'acm' });
    act(() => { vi.advanceTimersByTime(299); });
    expect(result.current).toBe('');
    act(() => { vi.advanceTimersByTime(1); });
    expect(result.current).toBe('acm');
  });

  it('restarts the wait on every change, so typing emits one value', () => {
    vi.useFakeTimers();
    const seen: string[] = [];
    const { rerender } = renderHook(({ v }) => {
      const d = useDebouncedValue(v, 300);
      if (seen[seen.length - 1] !== d) seen.push(d);
      return d;
    }, { initialProps: { v: '' } });
    for (const v of ['a', 'ac', 'acm', 'acme']) {
      rerender({ v });
      act(() => { vi.advanceTimersByTime(200); });
    }
    act(() => { vi.advanceTimersByTime(300); });
    expect(seen).toEqual(['', 'acme']);
  });
});
