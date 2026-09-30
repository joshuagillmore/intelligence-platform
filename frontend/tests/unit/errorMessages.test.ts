import { describe, it, expect } from 'vitest';
import { AxiosError } from 'axios';
import { getErrorMessage } from '@/lib/errorMessages';

/**
 * getErrorMessage normalizes assorted failure shapes (Axios errors, plain
 * Errors, unknowns) into user-facing copy. These tests pin the status-code
 * mapping and the non-Axios fallbacks.
 */
function axiosErrorWithStatus(status: number, data: unknown = null): AxiosError {
  const err = new AxiosError('Request failed');
  // Minimal AxiosResponse stub — getErrorMessage reads `.status` and `.data`.
  err.response = {
    status,
    statusText: '',
    data,
    headers: {},
    config: {},
  } as unknown as AxiosError['response'];
  return err;
}

describe('getErrorMessage with a backend detail', () => {
  // The backend's `detail` is already sanitised and says what went wrong;
  // replacing it with "Request failed (409)." threw the useful part away.
  it('shows a string detail from a 4xx', () => {
    expect(getErrorMessage(axiosErrorWithStatus(409, { detail: 'A collection run is already in flight' })))
      .toBe('A collection run is already in flight');
    expect(getErrorMessage(axiosErrorWithStatus(413, { detail: 'File too large' }))).toBe('File too large');
  });

  it('prefers the detail over the generic copy for a mapped status', () => {
    expect(getErrorMessage(axiosErrorWithStatus(503, { detail: 'LLM provider unavailable' })))
      .toBe('LLM provider unavailable');
    expect(getErrorMessage(axiosErrorWithStatus(403, { detail: 'Admin access required' })))
      .toBe('Admin access required');
  });

  it('falls back to the status copy when detail is not a string', () => {
    const validation = { detail: [{ loc: ['body', 'name'], msg: 'field required', type: 'missing' }] };
    expect(getErrorMessage(axiosErrorWithStatus(422, validation))).toBe('Request failed (422).');
    expect(getErrorMessage(axiosErrorWithStatus(500, 'Internal Server Error'))).toContain('Server error');
  });

  it('falls back to the status copy when detail is empty', () => {
    expect(getErrorMessage(axiosErrorWithStatus(429, { detail: '   ' }))).toContain('Rate limit exceeded');
  });
});

describe('getErrorMessage', () => {
  it('does not blame an API key for a 401 (the UI signs in with a session)', () => {
    const msg = getErrorMessage(axiosErrorWithStatus(401));
    expect(msg).not.toMatch(/API key/i);
    expect(msg).toMatch(/sign in/i);
  });

  it('maps known HTTP status codes to friendly copy', () => {
    expect(getErrorMessage(axiosErrorWithStatus(403))).toContain('Access denied');
    expect(getErrorMessage(axiosErrorWithStatus(429))).toContain('Rate limit exceeded');
    expect(getErrorMessage(axiosErrorWithStatus(500))).toContain('Server error');
  });

  it('groups 502/503/504 as a backend-unavailable message', () => {
    for (const status of [502, 503, 504]) {
      expect(getErrorMessage(axiosErrorWithStatus(status))).toContain('Backend unavailable');
    }
  });

  it('includes the raw status for unmapped codes', () => {
    expect(getErrorMessage(axiosErrorWithStatus(418))).toBe('Request failed (418).');
  });

  it('reports a connection error when the Axios error has no response', () => {
    const err = new AxiosError('Network Error');
    expect(getErrorMessage(err)).toContain('check if the backend is running');
  });

  it('detects a plain Network Error', () => {
    expect(getErrorMessage(new Error('Network Error'))).toContain('check if the backend is running');
  });

  it('passes through a generic Error message', () => {
    expect(getErrorMessage(new Error('Something specific broke'))).toBe('Something specific broke');
  });

  it('falls back for a non-Error unknown value', () => {
    expect(getErrorMessage('just a string')).toBe('An unexpected error occurred.');
  });
});
