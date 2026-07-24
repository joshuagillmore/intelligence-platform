import { describe, it, expect } from 'vitest';
import { AxiosError } from 'axios';
import { getErrorMessage } from '@/lib/errorMessages';

/**
 * getErrorMessage normalizes assorted failure shapes (Axios errors, plain
 * Errors, unknowns) into user-facing copy. These tests pin the status-code
 * mapping and the non-Axios fallbacks.
 */
function axiosErrorWithStatus(status: number): AxiosError {
  const err = new AxiosError('Request failed');
  // Minimal AxiosResponse stub — getErrorMessage only reads `.status`.
  err.response = {
    status,
    statusText: '',
    data: null,
    headers: {},
    config: {},
  } as unknown as AxiosError['response'];
  return err;
}

describe('getErrorMessage', () => {
  it('maps known HTTP status codes to friendly copy', () => {
    expect(getErrorMessage(axiosErrorWithStatus(401))).toContain('Authentication failed');
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
