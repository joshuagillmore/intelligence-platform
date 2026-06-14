'use client';

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { healthApi, collectionsApi, watchlistApi, adminApi } from '@/lib/api';
import { ClassificationStrip } from './Primitives';
import { Header, Rail, FooterBar, CommandPalette } from './Shell';
import { MobileShell } from './MobileShell';

interface SentinelShellProps {
  children: React.ReactNode;
}

const HIDE_SHELL_PATHS = ['/login'];

export function SentinelShell({ children }: SentinelShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { activeProject } = useProject();

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [username, setUsername] = useState('Analyst');
  const [role, setRole] = useState('analyst');
  const [healthOk, setHealthOk] = useState(true);
  const [activeCollections, setActiveCollections] = useState(0);
  const [watchlistCount, setWatchlistCount] = useState(0);
  const [llmLabel, setLlmLabel] = useState<string | undefined>(undefined);
  const [proxyMode, setProxyMode] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setUsername(localStorage.getItem('auth_user') || 'Analyst');
      setRole(localStorage.getItem('auth_role') || 'analyst');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        await healthApi.check();
        if (!cancelled) setHealthOk(true);
      } catch {
        if (!cancelled) setHealthOk(false);
      }
    }
    check();
    const interval = setInterval(check, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    adminApi
      .listModels()
      .then((res) => {
        if (cancelled) return;
        const raw = res.data as { models?: Array<{ id?: string; name?: string; active?: boolean; selected?: boolean }> } | Array<{ id?: string; name?: string; active?: boolean; selected?: boolean }> | undefined;
        const models = Array.isArray(raw) ? raw : raw?.models ?? [];
        const active = models.find((m) => m?.active || m?.selected) || models[0];
        if (active) setLlmLabel(active.name || active.id);
      })
      .catch(() => { /* ignore */ });
    adminApi
      .getProxy()
      .then((res) => {
        if (cancelled) return;
        const data = res.data as { mode?: string } | undefined;
        if (data?.mode) setProxyMode(data.mode);
      })
      .catch(() => { /* ignore */ });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    // Keyboard shortcuts (skip when typing in inputs/textareas/contenteditable)
    const VIEW_ROUTES = ['/', '/collections', '/network', '/pinboard', '/ach', '/products', '/topics', '/geo', '/cyber'];
    function isTyping(target: EventTarget | null): boolean {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable;
    }
    function onKey(e: KeyboardEvent) {
      // ⌘K / Ctrl+K — palette toggle (works even while typing)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if (isTyping(e.target)) return;
      // 1–9 → jump to view
      if (e.key >= '1' && e.key <= '9') {
        const idx = parseInt(e.key, 10) - 1;
        const route = VIEW_ROUTES[idx];
        if (route) {
          e.preventDefault();
          router.push(route);
        }
        return;
      }
      // / or ? → open palette
      if (e.key === '/' || (e.shiftKey && e.key === '?')) {
        e.preventDefault();
        setPaletteOpen(true);
        return;
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [router]);

  useEffect(() => {
    let cancelled = false;
    async function fetchBadges() {
      try {
        const colRes = await collectionsApi.list();
        const items = (colRes.data || []) as Array<{ status?: string }>;
        const active = items.filter((c) => {
          const s = c.status?.toUpperCase();
          return s === 'PENDING' || s === 'STARTED' || s === 'PROGRESS' || s === 'RUNNING';
        });
        if (!cancelled) setActiveCollections(active.length);
      } catch {
        /* ignore */
      }

      if (activeProject) {
        try {
          const wRes = await watchlistApi.list(activeProject.id);
          const data = wRes.data as { watched_entities?: unknown[]; items?: unknown[]; count?: number } | unknown[] | undefined;
          const items = Array.isArray(data)
            ? data
            : data?.watched_entities ?? data?.items ?? [];
          const count = Array.isArray(items)
            ? items.length
            : (typeof (data as { count?: number })?.count === 'number' ? (data as { count: number }).count : 0);
          if (!cancelled) setWatchlistCount(count);
        } catch {
          /* ignore */
        }
      } else if (!cancelled) {
        setWatchlistCount(0);
      }
    }
    fetchBadges();
    const interval = setInterval(fetchBadges, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [activeProject]);

  if (pathname && HIDE_SHELL_PATHS.some((p) => pathname.startsWith(p))) {
    return <>{children}</>;
  }

  const projectName = activeProject?.name || 'No project selected';
  const classification = activeProject?.classification_level || 'U//FOUO';
  const entities = activeProject?.entity_count ?? 0;
  const relationships = activeProject?.relationship_count ?? 0;
  const documents = activeProject?.document_count ?? 0;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100vw',
        background: 'var(--paper)',
        color: 'var(--fg)',
        overflow: 'hidden',
      }}
    >
      <div className="sentinel-desktop-only">
        <ClassificationStrip text={`${classification}//FOR OFFICIAL USE ONLY`} />
      </div>
      <div className="sentinel-desktop-only">
        <Header
          projectName={projectName}
          classification={classification}
          username={username}
          role={role}
          onAskOpen={() => setPaletteOpen(true)}
          onProjectClick={() => router.push('/')}
        />
      </div>
      {/* Mobile header + bottom tab bar + sheets — only visible at narrow widths */}
      <div className="sentinel-mobile-only">
        <MobileShell />
      </div>
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <div className="sentinel-desktop-only">
          <Rail
            badges={{
              acquire: activeCollections > 0 ? { dot: true, tone: 'var(--signal)' } : undefined,
              watch: watchlistCount > 0 ? { count: watchlistCount, tone: 'var(--signal)' } : undefined,
            }}
          />
        </div>
        <main className="sentinel-main" style={{ flex: 1, overflow: 'auto', background: 'var(--paper)' }}>{children}</main>
      </div>
      <div className="sentinel-desktop-only">
        <FooterBar
          entities={entities}
          relationships={relationships}
          documents={documents}
          healthOk={healthOk}
          llmLabel={llmLabel}
          agentsRunning={activeCollections}
          proxyMode={proxyMode}
        />
      </div>
      <div className="sentinel-desktop-only">
        <ClassificationStrip text={`${classification}//FOR OFFICIAL USE ONLY`} />
      </div>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={(view) => {
          setPaletteOpen(false);
          router.push(view);
        }}
      />
    </div>
  );
}
