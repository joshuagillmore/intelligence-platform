'use client';

/**
 * Sentinel Mobile shell — top header, bottom tab bar, command/notif/menu sheets,
 * and a floating Ask FAB. Renders ON TOP OF the existing route content; the
 * desktop Header + Rail are CSS-hidden at narrow widths (see SentinelShell).
 *
 * Ported from the v2 mobile prototype (sentinel-2/src/mobile.jsx).
 */

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Icon } from '@/components/sentinel';
import { APP_NOTIFICATIONS, SEARCH_INDEX, REVIEW_QUEUE } from '@/components/sentinel/mockData';
import { useProject } from '@/lib/ProjectContext';

type Sheet = null | 'command' | 'notif' | 'menu';

// Map mobile tab id -> Next.js route. "ask" maps to /network since that view
// already hosts the Ask panel + cited-answer pattern.
const TAB_ROUTES: Record<string, string> = {
  hub: '/',
  acquire: '/collections',
  ask: '/network',
  products: '/products',
  review: '/review',
};

const TABS: { id: string; icon: string; label: string }[] = [
  { id: 'hub',      icon: 'hub',     label: 'Hub' },
  { id: 'acquire',  icon: 'acquire', label: 'Acquire' },
  { id: 'ask',      icon: 'sparkle', label: 'Ask' },
  { id: 'products', icon: 'product', label: 'Products' },
  { id: 'review',   icon: 'check',   label: 'Review' },
];

function tabForPath(p: string): string {
  if (p === '/') return 'hub';
  if (p.startsWith('/collections')) return 'acquire';
  if (p.startsWith('/network')) return 'ask';
  if (p.startsWith('/products')) return 'products';
  if (p.startsWith('/review')) return 'review';
  return '';
}

export function MobileShell() {
  const router = useRouter();
  const pathname = usePathname();
  const { activeProject } = useProject();
  const [sheet, setSheet] = useState<Sheet>(null);

  // Lock body scroll while a sheet is open (so the underlying content doesn't move).
  useEffect(() => {
    if (sheet) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = prev; };
    }
  }, [sheet]);

  const go = (tab: string) => {
    setSheet(null);
    const route = TAB_ROUTES[tab];
    if (route) router.push(route);
  };

  const goRoute = (route: string) => {
    setSheet(null);
    router.push(route);
  };

  const active = tabForPath(pathname || '/');
  const unreadNotifs = APP_NOTIFICATIONS.filter((n) => !n.read).length;
  const pendingReview = REVIEW_QUEUE.filter((r) => r.status === 'pending').length;

  return (
    <>
      {/* Mobile header — replaces desktop header on small screens */}
      <header className="sentinel-mobile-header"
        style={{
          flexShrink: 0, background: 'var(--paper)',
          borderBottom: '1px solid var(--line)',
          display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
          position: 'sticky', top: 0, zIndex: 30,
        }}
      >
        <button
          onClick={() => setSheet('menu')}
          aria-label="Menu"
          style={{ color: 'var(--fg-2)', background: 'none', border: 'none', padding: 0 }}
        >
          <Icon name="menu-dots" size={22} />
        </button>
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, lineHeight: 1, minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>
            Sentinel
          </span>
          <span
            style={{
              fontFamily: 'var(--mono)', fontSize: 8, letterSpacing: '0.15em',
              color: 'var(--fg-3)', marginTop: 2,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {(activeProject?.name || 'NO PROJECT').toUpperCase()}
          </span>
        </div>
        <button
          onClick={() => setSheet('command')}
          aria-label="Search"
          style={{ color: 'var(--fg-2)', background: 'none', border: 'none', padding: 0 }}
        >
          <Icon name="search" size={20} />
        </button>
        <button
          onClick={() => setSheet('notif')}
          aria-label="Notifications"
          style={{ position: 'relative', color: 'var(--fg-2)', background: 'none', border: 'none', padding: 0 }}
        >
          <Icon name="flag" size={20} />
          {unreadNotifs > 0 && (
            <span
              style={{
                position: 'absolute', top: -3, right: -3, minWidth: 14, height: 14, padding: '0 3px',
                borderRadius: 7, background: 'var(--signal)', color: 'var(--ink)',
                fontFamily: 'var(--mono)', fontSize: 8.5, fontWeight: 700,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {unreadNotifs > 9 ? '9+' : unreadNotifs}
            </span>
          )}
        </button>
      </header>

      {/* Floating Ask button (FAB) */}
      <button
        onClick={() => setSheet('command')}
        aria-label="Ask Sentinel"
        className="sentinel-mobile-fab"
        style={{
          position: 'fixed', right: 16, bottom: 80, width: 52, height: 52, borderRadius: 26,
          background: 'var(--ink)', color: 'var(--signal)', border: 'none',
          boxShadow: '0 8px 24px rgba(15,18,22,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 40,
        }}
      >
        <Icon name="sparkle" size={24} />
      </button>

      {/* Bottom tab bar */}
      <nav
        className="sentinel-mobile-tabbar"
        style={{
          position: 'fixed', left: 0, right: 0, bottom: 0,
          background: 'var(--paper)', borderTop: '1px solid var(--line)',
          paddingBottom: 'max(8px, env(safe-area-inset-bottom))', paddingTop: 6,
          display: 'flex', zIndex: 35,
        }}
      >
        {TABS.map((t) => {
          const on = active === t.id;
          const showBadge = t.id === 'review' && pendingReview > 0;
          return (
            <button
              key={t.id}
              onClick={() => go(t.id)}
              style={{
                flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
                background: 'none', border: 'none', padding: '4px 0', cursor: 'pointer',
                color: on ? 'var(--ink)' : 'var(--fg-3)',
              }}
            >
              <div style={{ position: 'relative' }}>
                <Icon name={t.icon} size={21} stroke={on ? 2 : 1.6} />
                {showBadge && (
                  <span
                    style={{
                      position: 'absolute', top: -4, right: -7, minWidth: 13, height: 13, padding: '0 3px',
                      borderRadius: 7, background: 'var(--signal)', color: 'var(--ink)',
                      fontFamily: 'var(--mono)', fontSize: 8, fontWeight: 700,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    {pendingReview}
                  </span>
                )}
              </div>
              <span style={{ fontSize: 9.5, fontWeight: on ? 600 : 500, letterSpacing: '0.02em' }}>{t.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Sheets */}
      <CommandSheet open={sheet === 'command'} onClose={() => setSheet(null)} goRoute={goRoute} />
      <NotifSheet open={sheet === 'notif'} onClose={() => setSheet(null)} goRoute={goRoute} />
      <MenuSheet open={sheet === 'menu'} onClose={() => setSheet(null)} goRoute={goRoute} />
    </>
  );
}

// ============================================================================
// Sheets
// ============================================================================

function CommandSheet({ open, onClose, goRoute }: { open: boolean; onClose: () => void; goRoute: (r: string) => void }) {
  const [q, setQ] = useState('');
  useEffect(() => { if (!open) setQ(''); }, [open]);
  if (!open) return null;
  const lq = q.trim().toLowerCase();
  const results = lq
    ? SEARCH_INDEX.filter((s) => (s.label + s.meta).toLowerCase().includes(lq)).slice(0, 8)
    : [];

  const actions: { icon: string; label: string; route: string }[] = [
    { icon: 'sparkle', label: 'Ask a graph-RAG question', route: '/network' },
    { icon: 'acquire', label: 'Start a collection plan',  route: '/collections' },
    { icon: 'product', label: 'Draft a product',          route: '/products' },
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,18,22,0.4)', zIndex: 60,
        display: 'flex', alignItems: 'flex-start', animation: 'fade-in 0.15s ease',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', background: 'var(--paper)', borderRadius: '0 0 18px 18px',
          maxHeight: '70%', display: 'flex', flexDirection: 'column',
        }}
      >
        <div
          style={{
            padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 10,
            background: 'var(--paper-2)', borderBottom: '1px solid var(--line)',
          }}
        >
          <Icon name="sparkle" size={18} />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask, or search…"
            style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', fontSize: 16, color: 'var(--ink)' }}
          />
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--fg-3)' }}>
            <Icon name="x" size={18} />
          </button>
        </div>
        <div style={{ overflowY: 'auto' }}>
          {!lq ? (
            <div style={{ padding: '12px 0' }}>
              <div style={{ fontFamily: 'var(--mono)', padding: '6px 16px', fontSize: 9, letterSpacing: '0.15em', color: 'var(--fg-4)' }}>
                ACTIONS
              </div>
              {actions.map((a) => (
                <button
                  key={a.label}
                  onClick={() => goRoute(a.route)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12, width: '100%',
                    padding: '11px 16px', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer',
                  }}
                >
                  <Icon name={a.icon} size={17} />
                  <span style={{ flex: 1, fontSize: 14, color: 'var(--ink)' }}>{a.label}</span>
                  <Icon name="arrow-right" size={14} />
                </button>
              ))}
            </div>
          ) : (
            <div style={{ padding: '8px 0' }}>
              {results.length === 0 ? (
                <div style={{ padding: '20px 16px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
                  No matches. Tap to ask Sentinel.
                </div>
              ) : (
                results.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => goRoute(`/${r.view === 'network' ? 'network' : r.view}`)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12, width: '100%',
                      padding: '11px 16px', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer',
                    }}
                  >
                    <Icon
                      name={
                        r.kind === 'entity' ? 'entity'
                        : r.kind === 'document' ? 'doc'
                        : r.kind === 'product' ? 'product'
                        : 'sparkle'
                      }
                      size={17}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.label}
                      </div>
                      <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', marginTop: 1 }}>
                        {r.meta}
                      </div>
                    </div>
                    <Icon name="arrow-right" size={14} />
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function NotifSheet({ open, onClose, goRoute }: { open: boolean; onClose: () => void; goRoute: (r: string) => void }) {
  if (!open) return null;
  const items = APP_NOTIFICATIONS;
  const unread = items.filter((n) => !n.read).length;
  const iconFor = (type: string): string =>
    type === 'evidence' ? 'doc'
    : type === 'agent' ? 'sparkle'
    : type === 'change' ? 'arrow-up-right'
    : type === 'community' ? 'graph'
    : type === 'product' ? 'product'
    : 'star';

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,18,22,0.4)', zIndex: 60,
        display: 'flex', alignItems: 'flex-end', animation: 'fade-in 0.15s ease',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxHeight: '70%', overflowY: 'auto',
          background: 'var(--paper)', borderRadius: '18px 18px 0 0',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 4px' }}>
          <div style={{ width: 38, height: 4, borderRadius: 2, background: 'var(--line)' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 18px 12px' }}>
          <span style={{ fontFamily: 'var(--serif)', fontSize: 19, fontWeight: 500, color: 'var(--ink)' }}>Notifications</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--signal-ink)' }}>{unread} NEW</span>
        </div>
        {items.map((n) => {
          const route = n.action === 'review' ? '/review'
            : n.action === 'products' ? '/products'
            : `/${n.action}`;
          return (
            <button
              key={n.id}
              onClick={() => goRoute(route)}
              style={{
                display: 'flex', gap: 11, width: '100%', padding: '12px 18px', textAlign: 'left',
                background: !n.read ? 'var(--signal-soft)' : 'transparent',
                border: 'none', borderTop: '1px solid var(--line-soft)', cursor: 'pointer',
              }}
            >
              <span
                style={{
                  width: 28, height: 28, borderRadius: 6,
                  background: 'var(--paper-2)', border: '1px solid var(--line)',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  color: 'var(--fg-2)', flexShrink: 0,
                }}
              >
                <Icon name={iconFor(n.type)} size={14} />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>{n.title}</div>
                <div style={{ fontSize: 12, color: 'var(--fg-2)', marginTop: 2, lineHeight: 1.4 }}>{n.body}</div>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)', marginTop: 3 }}>{n.t}</div>
              </div>
            </button>
          );
        })}
        <div style={{ padding: '12px 18px 24px' }}>
          <button
            onClick={() => goRoute('/review')}
            style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
              padding: '11px 16px', width: '100%', borderRadius: 8,
              background: 'transparent', color: 'var(--fg)', border: '1px solid var(--line)',
              fontSize: 14, fontWeight: 600, fontFamily: 'var(--sans)', cursor: 'pointer',
            }}
          >
            Open review queue
          </button>
        </div>
      </div>
    </div>
  );
}

function MenuSheet({ open, onClose, goRoute }: { open: boolean; onClose: () => void; goRoute: (r: string) => void }) {
  const { activeProject } = useProject();
  if (!open) return null;

  const groups: { label: string; items: { icon: string; label: string; route: string }[] }[] = [
    {
      label: 'Workspace',
      items: [
        { icon: 'hub',     label: 'Hub',         route: '/' },
        { icon: 'acquire', label: 'Acquire',     route: '/collections' },
        { icon: 'graph',   label: 'Graph & Ask', route: '/network' },
        { icon: 'product', label: 'Products',    route: '/products' },
        { icon: 'check',   label: 'Review',      route: '/review' },
        { icon: 'grid',    label: 'Pinboard',    route: '/pinboard' },
        { icon: 'filter',  label: 'ACH',         route: '/ach' },
      ],
    },
    {
      label: 'Lenses',
      items: [
        { icon: 'sparkle',  label: 'Topics', route: '/topics' },
        { icon: 'location', label: 'Geo',    route: '/geo' },
        { icon: 'bolt',     label: 'Cyber',  route: '/cyber' },
      ],
    },
    {
      label: 'Library',
      items: [
        { icon: 'doc',    label: 'Documents', route: '/documents' },
        { icon: 'star-o', label: 'Watchlist', route: '/watchlist' },
      ],
    },
    {
      label: 'System',
      items: [
        { icon: 'layers', label: 'Admin', route: '/admin' },
      ],
    },
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,18,22,0.4)', zIndex: 60,
        display: 'flex', animation: 'fade-in 0.15s ease',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '78%', maxWidth: 360, height: '100%', overflowY: 'auto',
          background: 'var(--paper)', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid var(--line)', background: 'var(--paper-2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 34, height: 34, borderRadius: 6, background: 'var(--ink)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <svg width={22} height={22} viewBox="0 0 32 32" fill="none">
                <path d="M16 7 L22.5 19 L9.5 19 Z" stroke="var(--signal)" strokeWidth={1.6} fill="none" />
                <circle cx={16} cy={16} r={1.8} fill="var(--signal)" />
              </svg>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>
                Sentinel
              </div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 8.5, letterSpacing: '0.12em', color: 'var(--fg-3)' }}>
                INTEL · WORKSPACE
              </div>
            </div>
          </div>
          {/* Project pill */}
          <button
            onClick={() => goRoute('/')}
            style={{
              marginTop: 14, display: 'flex', alignItems: 'center', gap: 8, width: '100%',
              padding: '8px 10px', background: 'var(--paper)',
              border: '1px solid var(--line)', borderRadius: 8, cursor: 'pointer',
              textAlign: 'left',
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--live)' }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 8, letterSpacing: '0.12em', color: 'var(--fg-3)' }}>
                ACTIVE PROJECT · TAP TO SWITCH
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {activeProject?.name || 'No project'}
              </div>
            </div>
            <Icon name="chevron-down" size={14} />
          </button>
        </div>

        <div style={{ flex: 1, padding: '8px 0' }}>
          {groups.map((g) => (
            <div key={g.label} style={{ marginBottom: 6 }}>
              <div style={{ fontFamily: 'var(--mono)', padding: '8px 18px 4px', fontSize: 9, letterSpacing: '0.16em', color: 'var(--fg-4)' }}>
                {g.label.toUpperCase()}
              </div>
              {g.items.map((it) => (
                <button
                  key={it.label}
                  onClick={() => goRoute(it.route)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 13, width: '100%',
                    padding: '11px 18px', background: 'none', border: 'none', textAlign: 'left',
                    color: 'var(--fg)', cursor: 'pointer',
                  }}
                >
                  <Icon name={it.icon} size={19} />
                  <span style={{ fontSize: 14.5 }}>{it.label}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
