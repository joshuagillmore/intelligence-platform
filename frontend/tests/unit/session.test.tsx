import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';

/**
 * The session is an httpOnly cookie (contract 8). The client must never hold
 * a token, must send the cookie and the CSRF header on every request, and
 * takes the analyst's identity from `/api/auth/me`, not from the login body.
 */

const auth = vi.hoisted(() => ({
  login: vi.fn(),
  me: vi.fn(),
  logout: vi.fn(),
}));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  authApi: auth,
}));

import api from '@/lib/api';
import LoginPage from '@/app/login/page';
import { SessionProvider, useSession } from '@/lib/SessionContext';

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

/** Run one request through the real client and return what axios would send. */
async function sent(method: 'get' | 'post', url: string): Promise<InternalAxiosRequestConfig> {
  let captured: InternalAxiosRequestConfig | undefined;
  const adapter: AxiosAdapter = async (config) => {
    captured = config;
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
  };
  await (method === 'get' ? api.get(url, { adapter }) : api.post(url, {}, { adapter }));
  return captured!;
}

describe('the API client', () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = installLocalStorage();
    // A token an older client left behind must not be sent, let alone trusted.
    store.set('auth_token', 'eyJ.legacy.token');
  });

  it.each(['get', 'post'] as const)('sends the cookie and the CSRF header on a %s, and no bearer token', async (method) => {
    const config = await sent(method, '/projects');
    expect(config.withCredentials).toBe(true);
    expect(config.headers['X-Requested-With']).toBe('sentinel');
    expect(config.headers.Authorization).toBeUndefined();
  });
});

describe('the login page', () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = installLocalStorage();
    auth.login.mockReset();
    auth.me.mockReset();
    store.set('activeProject', '{"id":"previous-analyst"}');
  });

  async function submit() {
    render(<LoginPage />);
    fireEvent.change(screen.getByPlaceholderText('Enter username'), { target: { value: 'alice' } });
    fireEvent.change(screen.getByPlaceholderText('Enter password'), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
  }

  it('stores no token and takes the identity from /auth/me', async () => {
    // An older backend still returns access_token; it must be ignored.
    auth.login.mockResolvedValue({ data: { access_token: 'eyJ.should.not.persist', username: 'alice', role: 'admin' } });
    auth.me.mockResolvedValue({ data: { username: 'alice', role: 'analyst' } });
    await submit();
    await waitFor(() => expect(auth.me).toHaveBeenCalled());
    await waitFor(() => expect(store.get('auth_role')).toBe('analyst'));
    expect(auth.login).toHaveBeenCalledWith({ username: 'alice', password: 'pw' });
    expect(store.get('auth_user')).toBe('alice');
    expect(store.has('auth_token')).toBe(false);
    expect(store.has('activeProject'), "the previous analyst's project").toBe(false);
  });

  it('works when the login body has no access_token at all', async () => {
    auth.login.mockResolvedValue({ data: { username: 'alice', role: 'analyst' } });
    auth.me.mockResolvedValue({ data: { username: 'alice', role: 'analyst' } });
    await submit();
    await waitFor(() => expect(store.get('auth_user')).toBe('alice'));
    expect(store.has('auth_token')).toBe(false);
  });

  it('says so when the cookie did not stick', async () => {
    auth.login.mockResolvedValue({ data: { username: 'alice', role: 'analyst' } });
    auth.me.mockRejectedValue(new Error('401'));
    await submit();
    expect(await screen.findByText(/did not keep the session cookie/)).toBeInTheDocument();
    expect(store.has('auth_user')).toBe(false);
  });

  it("shows the backend's reason for a refused login", async () => {
    const { AxiosError } = await import('axios');
    auth.login.mockRejectedValue(
      new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', undefined, null, {
        status: 401, statusText: 'Unauthorized', data: { detail: 'Invalid credentials' }, headers: {},
        config: {} as InternalAxiosRequestConfig,
      }),
    );
    await submit();
    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument();
    expect(auth.me).not.toHaveBeenCalled();
  });
});

describe('SessionProvider', () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = installLocalStorage();
    auth.me.mockReset();
    window.history.pushState({}, '', '/');
  });

  function WhoAmI() {
    const { user } = useSession();
    return <p>{user ? `${user.username}:${user.role}` : 'nobody'}</p>;
  }

  it('asks /auth/me on load, records the answer and drops a legacy token', async () => {
    store.set('auth_token', 'eyJ.legacy.token');
    auth.me.mockResolvedValue({ data: { username: 'carol', role: 'admin' } });
    render(<SessionProvider><WhoAmI /></SessionProvider>);
    expect(await screen.findByText('carol:admin')).toBeInTheDocument();
    expect(store.get('auth_role')).toBe('admin');
    expect(store.has('auth_token')).toBe(false);
  });

  it('does not ask on the login page', async () => {
    window.history.pushState({}, '', '/login');
    render(<SessionProvider><WhoAmI /></SessionProvider>);
    expect(screen.getByText('nobody')).toBeInTheDocument();
    expect(auth.me).not.toHaveBeenCalled();
  });
});
