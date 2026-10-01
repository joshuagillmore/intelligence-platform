'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { authApi, cachedSessionUser, forgetLegacyToken, rememberSessionUser, type SessionUser } from './api';

interface SessionValue {
  /** The signed-in analyst, or null before `/api/auth/me` answers (or on the
   *  login page, which has no session to ask about). */
  user: SessionUser | null;
}

const SessionContext = createContext<SessionValue>({ user: null });

/**
 * Who is signed in, for display and UI gating.
 *
 * The session is an httpOnly cookie, so script cannot see it; on every page
 * load this asks `GET /api/auth/me`. A 401 there is the app-wide sign-in gate:
 * the axios interceptor clears the session and sends the analyst to /login.
 * Until the answer arrives, the identity `/me` reported last time is shown.
 * Logins and sign-outs are full navigations, so mount-once is per session.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    forgetLegacyToken();
    if (window.location.pathname.startsWith('/login')) return;
    setUser(cachedSessionUser());
    let cancelled = false;
    authApi
      .me()
      .then((res) => {
        if (cancelled) return;
        rememberSessionUser(res.data);
        setUser(res.data);
      })
      .catch(() => {
        /* a 401 is handled by the interceptor; anything else keeps the cache */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return <SessionContext.Provider value={{ user }}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  return useContext(SessionContext);
}
