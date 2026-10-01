'use client';
import { useState } from 'react';
import { APP_NAME, APP_TAGLINE } from '@/lib/branding';
import axios from 'axios';
import { authApi, clearSession, rememberSessionUser } from '@/lib/api';

/** The backend's `detail` for a failed login, or a generic line. */
function loginError(error: unknown): string {
  if (!axios.isAxiosError(error) || !error.response) return 'Connection error';
  const detail = (error.response.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' && detail.trim() ? detail : 'Login failed';
}

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      // Sets the httpOnly session cookie. The body may still carry an
      // access_token from an older backend; it is deliberately not read.
      await authApi.login({ username, password });
    } catch (err) {
      setError(loginError(err));
      setLoading(false);
      return;
    }
    try {
      // Nothing from a previous analyst's session (selected project, assistant
      // threads) may carry into this one on a shared workstation.
      clearSession();
      // Proves the cookie took: a browser that refused it (a Secure cookie
      // over plain http, say) would otherwise bounce straight back here.
      const me = await authApi.me();
      rememberSessionUser(me.data);
    } catch {
      setError('Signed in, but this browser did not keep the session cookie.');
      setLoading(false);
      return;
    }
    // A full navigation, not router.push: the project and assistant contexts
    // live in the root layout and would otherwise keep the previous analyst's
    // in-memory state (and write it back to storage).
    window.location.href = '/';
  }

  return (
    <div className="min-h-screen bg-navy-900 flex items-center justify-center">
      <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-accent-blue tracking-tight">{APP_NAME}</h1>
          <p className="text-sm text-gray-500 mt-1">{APP_TAGLINE}</p>
        </div>
        <form onSubmit={handleLogin}>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
              placeholder="Enter username"
              autoFocus
            />
          </div>
          <div className="mb-6">
            <label className="block text-sm text-gray-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
              placeholder="Enter password"
            />
          </div>
          {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full bg-accent-blue hover:bg-blue-600 text-white py-2 rounded font-medium text-sm disabled:opacity-50 transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
