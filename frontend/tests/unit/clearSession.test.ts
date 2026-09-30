import { describe, it, expect, beforeEach } from 'vitest';
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios';
import api, { clearSession } from '@/lib/api';

/**
 * A browser on an analyst workstation is shared. When a session ends (sign
 * out, an expired token, or the next analyst signing in) nothing the previous
 * analyst saw may survive: the token and identity, the selected project, and
 * the assistant threads, which hold RAG answers and verbatim source excerpts.
 */
function installLocalStorage() {
  const data = new Map<string, string>();
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
      setItem: (k: string, v: string) => { data.set(k, String(v)); },
      removeItem: (k: string) => { data.delete(k); },
      clear: () => data.clear(),
      key: (i: number) => [...data.keys()][i] ?? null,
      get length() { return data.size; },
    },
  });
  return data;
}

function seedSession() {
  localStorage.setItem('auth_token', 'eyJ.previous.analyst');
  localStorage.setItem('auth_user', 'analyst1');
  localStorage.setItem('auth_role', 'admin');
  localStorage.setItem('activeProject', JSON.stringify({ id: 'p1', name: 'Nightfall' }));
  localStorage.setItem('assistant_thread:p1', '[{"id":"m1","role":"assistant","content":"excerpt"}]');
  localStorage.setItem('assistant_thread:_none', '[]');
  localStorage.setItem('mindmap-layout', 'radial');
}

describe('clearSession', () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = installLocalStorage();
    seedSession();
  });

  it('removes the token, identity, selected project and every assistant thread', () => {
    clearSession();
    for (const key of ['auth_token', 'auth_user', 'auth_role', 'activeProject', 'assistant_thread:p1', 'assistant_thread:_none']) {
      expect(store.has(key), key).toBe(false);
    }
  });

  it('keeps unrelated per-browser preferences', () => {
    clearSession();
    expect(store.get('mindmap-layout')).toBe('radial');
  });

  it('does not throw when storage is unavailable', () => {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() { throw new Error('SecurityError'); },
    });
    expect(() => clearSession()).not.toThrow();
  });
});

describe('401 interceptor', () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = installLocalStorage();
    seedSession();
    // Already on /login, so the interceptor does not try to navigate (jsdom
    // cannot); the session must be cleared either way.
    window.history.pushState({}, '', '/login');
  });

  it('clears the whole session, not just the token', async () => {
    const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
      throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, null, {
        status: 401, statusText: 'Unauthorized', data: { detail: 'expired' }, headers: {}, config,
      });
    };
    await expect(api.get('/projects', { adapter })).rejects.toBeInstanceOf(AxiosError);
    expect(store.has('auth_token')).toBe(false);
    expect(store.has('activeProject')).toBe(false);
    expect(store.has('assistant_thread:p1')).toBe(false);
  });

  it('leaves the session alone on a 403', async () => {
    const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
      throw new AxiosError('Forbidden', 'ERR_BAD_REQUEST', config, null, {
        status: 403, statusText: 'Forbidden', data: {}, headers: {}, config,
      });
    };
    await expect(api.get('/admin/config', { adapter })).rejects.toBeInstanceOf(AxiosError);
    expect(store.get('auth_token')).toBe('eyJ.previous.analyst');
  });
});
