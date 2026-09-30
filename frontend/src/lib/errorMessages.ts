import { AxiosError } from 'axios';

/** The backend's `detail`, when it is a usable string. FastAPI sends a string
 *  for every HTTPException the routes raise (already sanitised), and a list of
 *  objects for request-validation errors, which falls through to the status. */
function backendDetail(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail !== 'string') return null;
  const trimmed = detail.trim();
  return trimmed ? trimmed : null;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof AxiosError || (error && typeof error === 'object' && 'response' in error)) {
    const axiosErr = error as AxiosError;
    if (!axiosErr.response) {
      return 'Connection error \u2014 check if the backend is running.';
    }
    const detail = backendDetail(axiosErr.response.data);
    if (detail) return detail;
    switch (axiosErr.response.status) {
      case 401:
        return 'Your session has expired or you are not signed in \u2014 sign in again.';
      case 403:
        return 'Access denied \u2014 insufficient permissions.';
      case 429:
        return 'Rate limit exceeded \u2014 try again in a moment.';
      case 500:
        return 'Server error \u2014 the backend encountered an issue.';
      case 502:
      case 503:
      case 504:
        return 'Backend unavailable \u2014 the service may be restarting.';
      default:
        return `Request failed (${axiosErr.response.status}).`;
    }
  }
  if (error instanceof Error) {
    if (error.message.includes('Network Error') || error.message.includes('ERR_CONNECTION')) {
      return 'Connection error \u2014 check if the backend is running.';
    }
    return error.message;
  }
  return 'An unexpected error occurred.';
}
