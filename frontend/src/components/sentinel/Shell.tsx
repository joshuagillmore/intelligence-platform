'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Icon } from './Icon';
import { Tag, Kbd, PulseDot } from './Primitives';
import { NotificationBell, UserMenu } from './HeaderActions';
import { ProjectSwitcher } from './ProjectSwitcher';
import { usePathname, useRouter } from 'next/navigation';
import { SEARCH_INDEX } from '@/components/sentinel/mockData';
import { useProject } from '@/lib/ProjectContext';
import { projectsApi } from '@/lib/api';

export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <rect x={0.5} y={0.5} width={31} height={31} rx={3} fill="var(--ink)" />
      <circle cx={16} cy={16} r={9} stroke="var(--paper)" strokeWidth={1} opacity={0.4} />
      <path d="M16 7 L22.5 19 L9.5 19 Z" stroke="var(--signal)" strokeWidth={1.4} fill="none" />
      <circle cx={16} cy={16} r={1.8} fill="var(--signal)" />
      <path d="M16 3v2.5M16 26.5V29M3 16h2.5M26.5 16H29" stroke="var(--paper)" strokeWidth={1} opacity={0.5} />
    </svg>
  );
}

interface HeaderProps {
  projectName?: string;
  classification: string;
  onAskOpen: () => void;
  username?: string;
  role?: string;
  onProjectClick?: () => void;
}

export function Header({
  classification,
  onAskOpen,
  username = 'Analyst',
  role = 'analyst',
}: HeaderProps) {
  return (
    <header
      style={{
        height: 52,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '0 16px',
        background: 'var(--paper)',
        borderBottom: '1px solid var(--line)',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Mark />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <span
            style={{
              fontFamily: 'serif',
              fontStyle: 'italic',
              fontSize: 17,
              lineHeight: 1,
              color: 'var(--ink)',
            }}
          >
            Sentinel
          </span>
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 8.5,
              letterSpacing: '0.08em',
              color: 'var(--fg-3)',
              lineHeight: 1,
            }}
          >
            INTEL · WORKSPACE
          </span>
        </div>
      </div>

      <div style={{ width: 1, height: 28, background: 'var(--line)', margin: '0 4px' }} />

      <ProjectSwitcher />

      <Tag tone="signal">{classification}</Tag>

      <div style={{ flex: 1 }} />

      <button
        onClick={onAskOpen}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          minWidth: 320,
          height: 32,
          padding: '0 12px',
          background: 'var(--paper-2)',
          border: '1px solid var(--line)',
          borderRadius: 4,
          cursor: 'pointer',
          color: 'var(--fg-3)',
          fontSize: 12,
        }}
      >
        <Icon name="sparkle" size={14} />
        <span style={{ flex: 1, textAlign: 'left' }}>Ask Sentinel — entity, question, PIR…</span>
        <Kbd>⌘ K</Kbd>
      </button>

      <NotificationBell />
      <UserMenu username={username} role={role} />
    </header>
  );
}

interface RailItem {
  id: string;
  icon: string;
  name: string;
  href: string;
}

const RAIL_GROUPS: { label: string; items: RailItem[] }[] = [
  {
    label: 'Workspace',
    items: [
      { id: 'hub',       icon: 'hub',     name: 'Hub',      href: '/' },
      { id: 'acquire',   icon: 'acquire', name: 'Acquire',  href: '/collections' },
      { id: 'graph',     icon: 'graph',   name: 'Graph',    href: '/network' },
      { id: 'pinboard',  icon: 'grid',    name: 'Pinboard', href: '/pinboard' },
      { id: 'ach',       icon: 'filter',  name: 'ACH',      href: '/ach' },
      { id: 'products',  icon: 'product', name: 'Products', href: '/products' },
    ],
  },
  {
    label: 'Lenses',
    items: [
      { id: 'topics', icon: 'sparkle',  name: 'Topics', href: '/topics' },
      { id: 'geo',    icon: 'location', name: 'Geo',    href: '/geo' },
      { id: 'cyber',  icon: 'bolt',     name: 'Cyber',  href: '/cyber' },
    ],
  },
  {
    label: 'Library',
    items: [
      { id: 'docs',   icon: 'doc',    name: 'Documents', href: '/documents' },
      { id: 'review', icon: 'check',  name: 'Review',    href: '/review' },
      { id: 'watch',  icon: 'star-o', name: 'Watchlist', href: '/watchlist' },
    ],
  },
];

const ADMIN_ITEM: RailItem = { id: 'admin', icon: 'layers', name: 'Admin', href: '/admin' };

function isPathActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === '/') return pathname === '/' || pathname.startsWith('/project/');
  return pathname === href || pathname.startsWith(href + '/');
}

interface RailProps {
  badges?: Record<string, { dot?: boolean; count?: number; tone?: string } | undefined>;
}

export function Rail({ badges = {} }: RailProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [hovered, setHovered] = useState<string | null>(null);

  const renderItem = (item: RailItem) => {
    const active = isPathActive(pathname, item.href);
    const isHovered = hovered === item.id;
    const badge = badges[item.id];
    return (
      <button
        key={item.id}
        onClick={() => router.push(item.href)}
        onMouseEnter={() => setHovered(item.id)}
        onMouseLeave={() => setHovered(null)}
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 3,
          width: '100%',
          padding: '8px 0',
          background: active ? 'var(--paper)' : 'transparent',
          border: 'none',
          borderLeft: active ? '2px solid var(--signal)' : '2px solid transparent',
          cursor: 'pointer',
          color: active ? 'var(--ink)' : isHovered ? 'var(--ink)' : 'var(--fg-3)',
          transition: 'color 0.1s',
        }}
      >
        <span style={{ position: 'relative' }}>
          <Icon name={item.icon} size={18} />
          {badge?.dot && (
            <span
              style={{
                position: 'absolute',
                top: -2,
                right: -4,
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: badge.tone || 'var(--signal)',
                animation: 'pulse-dot 1.6s ease-in-out infinite',
              }}
            />
          )}
          {!badge?.dot && badge?.count != null && badge.count > 0 && (
            <span
              style={{
                position: 'absolute',
                top: -6,
                right: -10,
                minWidth: 14,
                height: 14,
                padding: '0 3px',
                borderRadius: 8,
                background: badge.tone || 'var(--signal)',
                color: 'var(--ink)',
                fontFamily: 'var(--mono)',
                fontSize: 9,
                fontWeight: 700,
                lineHeight: '14px',
                textAlign: 'center',
              }}
            >
              {badge.count > 99 ? '99+' : badge.count}
            </span>
          )}
        </span>
        <span
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 9,
            letterSpacing: '0.04em',
            lineHeight: 1,
          }}
        >
          {item.name}
        </span>
      </button>
    );
  };

  return (
    <nav
      style={{
        width: 64,
        background: 'var(--paper-2)',
        borderRight: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        overflowY: 'auto',
      }}
    >
      {RAIL_GROUPS.map((group, gi) => (
        <div key={group.label}>
          {gi > 0 && (
            <div style={{ height: 1, background: 'var(--line)', margin: '4px 0' }} />
          )}
          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 8.5,
              letterSpacing: '0.08em',
              color: 'var(--fg-3)',
              textAlign: 'center',
              padding: '8px 0 4px',
            }}
          >
            {group.label.toUpperCase()}
          </div>
          {group.items.map(renderItem)}
        </div>
      ))}

      <div style={{ flex: 1 }} />

      <div style={{ height: 1, background: 'var(--line)', margin: '4px 0' }} />
      {renderItem(ADMIN_ITEM)}
    </nav>
  );
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNavigate?: (view: string) => void;
}

const PALETTE_ACTIONS: { id: string; icon: string; label: string; kbd: string; route: string }[] = [
  { id: 'ask',        icon: 'graph',   label: 'Ask (graph RAG)', kbd: '⌘ A', route: '/network' },
  { id: 'pir',        icon: 'doc',     label: 'New PIR',         kbd: '⌘ P', route: '/collections' },
  { id: 'draft',      icon: 'product', label: 'Draft product',   kbd: '⌘ D', route: '/products' },
  { id: 'open-graph', icon: 'graph',   label: 'Open graph',      kbd: '⌘ G', route: '/network' },
];

interface PaletteRecent { id: string; icon: string; label: string; sub: string; route: string }

function activityToRecent(a: { id?: string; action?: string; entity_name?: string; entity_type?: string; timestamp?: string }, i: number): PaletteRecent {
  const action = a.action || 'Event';
  const upperAction = action.toUpperCase();
  const kindLower = action.toLowerCase();
  const icon = kindLower.includes('extract') ? 'sparkle'
    : kindLower.includes('ingest') || kindLower.includes('acqui') ? 'acquire'
    : kindLower.includes('report') || kindLower.includes('intsum') || kindLower.includes('product') ? 'product'
    : 'entity';
  const route = kindLower.includes('report') || kindLower.includes('intsum') ? '/products'
    : kindLower.includes('ingest') || kindLower.includes('acqui') ? '/collections'
    : '/network';
  const label = a.entity_name ? `${upperAction} · ${a.entity_name}` : upperAction;
  let sub = '';
  if (a.timestamp) {
    const d = new Date(a.timestamp);
    if (!Number.isNaN(d.getTime())) {
      const mins = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
      sub = mins < 1 ? 'just now' : mins < 60 ? `${mins}m ago` : `${Math.floor(mins / 60)}h ago`;
    }
  }
  return { id: a.id || `r${i}`, icon, label, sub, route };
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const { activeProject } = useProject();
  const [recents, setRecents] = useState<PaletteRecent[]>([]);

  useEffect(() => {
    if (!open || !activeProject) { setRecents([]); return; }
    let cancelled = false;
    projectsApi
      .activity(activeProject.id, 5)
      .then((res) => {
        if (cancelled) return;
        const raw = res.data as { activity?: Array<{ id?: string; action?: string; entity_name?: string; entity_type?: string; timestamp?: string }> } | Array<{ id?: string; action?: string; entity_name?: string; entity_type?: string; timestamp?: string }> | undefined;
        const list = Array.isArray(raw) ? raw : raw?.activity ?? [];
        setRecents((Array.isArray(list) ? list : []).slice(0, 5).map((a, i) => activityToRecent(a, i)));
      })
      .catch(() => setRecents([]));
    return () => { cancelled = true; };
  }, [open, activeProject]);

  // Live search across entities/documents/products/questions
  const q = query.trim().toLowerCase();
  const results = q
    ? SEARCH_INDEX.filter((s) =>
        s.label.toLowerCase().includes(q) || s.meta.toLowerCase().includes(q),
      ).slice(0, 12)
    : [];
  const groupedResults: Record<string, typeof results> = {
    entity: results.filter((r) => r.kind === 'entity'),
    document: results.filter((r) => r.kind === 'document'),
    product: results.filter((r) => r.kind === 'product'),
    question: results.filter((r) => r.kind === 'question'),
  };

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 30);
    } else {
      setQuery('');
    }
  }, [open]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.45)',
        backdropFilter: 'blur(4px)',
        zIndex: 1000,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'flex-start',
        paddingTop: '14vh',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 640,
          background: 'var(--paper)',
          border: '1px solid var(--line)',
          borderRadius: 8,
          overflow: 'hidden',
          boxShadow: '0 24px 64px rgba(0,0,0,0.3)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '0 14px',
            borderBottom: '1px solid var(--line)',
            height: 48,
          }}
        >
          <Icon name="sparkle" size={16} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entities, documents, questions, PIRs…"
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: 14,
              color: 'var(--ink)',
            }}
          />
          <Tag>esc</Tag>
        </div>

        {q && results.length > 0 && (
          <div style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
            {(['entity', 'document', 'product', 'question'] as const).map((kind) => {
              const items = groupedResults[kind];
              if (!items || items.length === 0) return null;
              return (
                <div key={kind}>
                  <div
                    style={{
                      fontFamily: 'var(--mono)',
                      fontSize: 9,
                      letterSpacing: '0.08em',
                      color: 'var(--fg-3)',
                      padding: '4px 14px 6px',
                    }}
                  >
                    {kind === 'question' ? 'PAST QUESTIONS' : (kind.toUpperCase() + 'S')}
                  </div>
                  {items.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => {
                        onClose();
                        router.push(r.view === 'network' ? '/network' : `/${r.view === 'documents' ? 'documents' : r.view}`);
                      }}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                        padding: '7px 14px', background: 'transparent', border: 'none',
                        cursor: 'pointer', color: 'var(--ink)', fontSize: 13, textAlign: 'left',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--paper-2)')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                    >
                      <Icon
                        name={
                          r.kind === 'entity' ? 'entity'
                          : r.kind === 'document' ? 'doc'
                          : r.kind === 'product' ? 'product'
                          : 'sparkle'
                        }
                        size={15}
                      />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.label}
                      </span>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)' }}>
                        {r.meta}
                      </span>
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        )}
        {q && results.length === 0 && (
          <div style={{ padding: '24px 14px', textAlign: 'center', fontSize: 12, color: 'var(--fg-3)' }}>
            No matches for &ldquo;{query}&rdquo;
          </div>
        )}
        <div style={{ padding: '8px 0' }}>
          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 9,
              letterSpacing: '0.08em',
              color: 'var(--fg-3)',
              padding: '4px 14px 6px',
            }}
          >
            ACTIONS
          </div>
          {PALETTE_ACTIONS.map((action) => (
            <button
              key={action.id}
              onClick={() => { onClose(); router.push(action.route); }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: '7px 14px',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--ink)',
                fontSize: 13,
                textAlign: 'left',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--paper-2)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <Icon name={action.icon} size={15} />
              <span style={{ flex: 1 }}>{action.label}</span>
              <Kbd>{action.kbd}</Kbd>
            </button>
          ))}
        </div>

        {recents.length > 0 && (
        <div style={{ padding: '8px 0', borderTop: '1px solid var(--line)' }}>
          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 9,
              letterSpacing: '0.08em',
              color: 'var(--fg-3)',
              padding: '4px 14px 6px',
            }}
          >
            RECENT ACTIVITY
          </div>
          {recents.map((item) => (
            <button
              key={item.id}
              onClick={() => { onClose(); router.push(item.route); }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: '7px 14px',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--ink)',
                fontSize: 13,
                textAlign: 'left',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--paper-2)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <Icon name={item.icon} size={15} />
              <span style={{ flex: 1 }}>{item.label}</span>
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  color: 'var(--fg-3)',
                }}
              >
                {item.sub}
              </span>
            </button>
          ))}
        </div>
        )}

        <div
          style={{
            borderTop: '1px solid var(--line)',
            padding: '7px 14px',
            display: 'flex',
            gap: 16,
            alignItems: 'center',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--fg-3)' }}>
            <Kbd>↵</Kbd> open
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--fg-3)' }}>
            <Kbd>↑↓</Kbd> navigate
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--fg-3)' }}>
            <Kbd>esc</Kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}

interface FooterBarProps {
  entities?: number;
  relationships?: number;
  documents?: number;
  healthOk?: boolean;
  llmLabel?: string;
  agentsRunning?: number;
  proxyMode?: string;
}

export function FooterBar({
  entities = 0,
  relationships = 0,
  documents = 0,
  healthOk = true,
  llmLabel,
  agentsRunning = 0,
  proxyMode,
}: FooterBarProps) {
  const mono: React.CSSProperties = {
    fontFamily: 'var(--mono)',
    fontSize: 10,
    color: 'var(--fg-3)',
    letterSpacing: '0.04em',
  };

  const sep = (
    <span style={{ ...mono, opacity: 0.3, margin: '0 6px' }}>·</span>
  );

  return (
    <footer
      style={{
        height: 22,
        background: 'var(--paper-2)',
        borderTop: '1px solid var(--line)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 14px',
        gap: 0,
        flexShrink: 0,
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 5, ...mono }}>
        <PulseDot color={healthOk ? 'var(--live)' : 'var(--warn)'} />
        {healthOk ? 'BACKEND OK' : 'BACKEND DOWN'}
      </span>
      {sep}
      {llmLabel && (
        <>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, ...mono }}>
            <PulseDot />
            LLM · {llmLabel.toUpperCase()}
          </span>
          {sep}
        </>
      )}
      {agentsRunning > 0 && (
        <>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, ...mono }}>
            <PulseDot color="var(--signal)" />
            {agentsRunning} AGENT{agentsRunning === 1 ? '' : 'S'} RUNNING
          </span>
          {sep}
        </>
      )}
      {proxyMode && proxyMode.toLowerCase() !== 'direct' && (
        <>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, ...mono }}>
            <PulseDot />
            {proxyMode.toUpperCase()} PROXY
          </span>
          {sep}
        </>
      )}

      <div style={{ flex: 1 }} />

      <span style={mono}>
        {entities.toLocaleString()} entities
      </span>
      {sep}
      <span style={mono}>
        {relationships.toLocaleString()} relationships
      </span>
      {sep}
      <span style={mono}>
        {documents.toLocaleString()} documents
      </span>
      {sep}
      <span style={{ ...mono, opacity: 0.5 }}>v0.9.1</span>
    </footer>
  );
}
