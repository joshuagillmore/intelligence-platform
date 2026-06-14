'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { watchlistApi } from '@/lib/api';
import { Btn, Tag, Icon, ENTITY_META } from '@/components/sentinel';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WatchedEntity {
  id: string;
  name: string;
  entity_type?: string;
  type?: string;
  confidence?: number;
  flag?: string;
  watched?: boolean;
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export function WatchlistView() {
  const router = useRouter();
  const { activeProject } = useProject();

  const [items, setItems] = useState<WatchedEntity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = (projectId: string) => {
    setLoading(true);
    setError(null);
    watchlistApi
      .list(projectId)
      .then((res) => {
        const raw = res.data as
          | WatchedEntity[]
          | { watched_entities?: WatchedEntity[]; items?: WatchedEntity[] };
        const arr = Array.isArray(raw)
          ? raw
          : Array.isArray(raw?.watched_entities)
            ? raw.watched_entities
            : Array.isArray(raw?.items)
              ? raw.items
              : [];
        setItems(arr);
      })
      .catch(() => {
        setItems([]);
        setError('Could not load watchlist.');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!activeProject) {
      setItems([]);
      return;
    }
    refresh(activeProject.id);
  }, [activeProject]);

  if (!activeProject) {
    return (
      <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
        <div style={{ maxWidth: 1320, margin: '0 auto', padding: '28px 32px' }}>
          <NoProject onOpenHub={() => router.push('/')} />
        </div>
      </div>
    );
  }

  const handleRemove = async (entityId: string) => {
    try {
      await watchlistApi.remove(activeProject.id, entityId);
      setItems((prev) => prev.filter((e) => e.id !== entityId));
    } catch {
      // Best-effort: refresh from server in case state diverged
      refresh(activeProject.id);
    }
  };

  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1320, margin: '0 auto', padding: '28px 32px 48px' }}>
        <Header count={items.length} loading={loading} />

        {error && (
          <div
            style={{
              marginTop: 18,
              padding: '12px 16px',
              border: '1px solid var(--warn)',
              borderRadius: 3,
              fontSize: 12.5,
              color: 'var(--warn)',
              background: 'transparent',
            }}
          >
            {error}
          </div>
        )}

        {loading && items.length === 0 ? (
          <LoadingState />
        ) : items.length === 0 ? (
          <EmptyState onOpenGraph={() => router.push('/network')} />
        ) : (
          <div
            style={{
              marginTop: 24,
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 16,
            }}
          >
            {items.map((entity) => (
              <EntityCard
                key={entity.id}
                entity={entity}
                onOpen={() => router.push(`/network?entity=${entity.id}`)}
                onRemove={() => handleRemove(entity.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function Header({ count, loading }: { count: number; loading: boolean }) {
  return (
    <div style={{ paddingBottom: 18, borderBottom: '1px solid var(--line)' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          marginBottom: 6,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 9.5,
            letterSpacing: '0.2em',
            color: 'var(--fg-3)',
            fontWeight: 600,
          }}
        >
          WATCHLIST
        </span>
        <Tag tone="signal">{count} PINNED</Tag>
        {loading && (
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10,
              letterSpacing: '0.14em',
              color: 'var(--fg-3)',
            }}
          >
            REFRESHING…
          </span>
        )}
      </div>
      <h1
        style={{
          margin: 0,
          fontFamily: 'var(--serif)',
          fontWeight: 500,
          fontSize: 22,
          color: 'var(--ink)',
          letterSpacing: '-0.01em',
        }}
      >
        Watchlist
      </h1>
      <p
        style={{
          margin: '4px 0 0',
          fontSize: 13,
          color: 'var(--fg-2)',
          lineHeight: 1.45,
        }}
      >
        Pinned entities you&apos;re actively monitoring.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

function EntityCard({
  entity,
  onOpen,
  onRemove,
}: {
  entity: WatchedEntity;
  onOpen: () => void;
  onRemove: () => void;
}) {
  const type = (entity.entity_type || entity.type || 'PERSON').toUpperCase();
  const meta = ENTITY_META[type] || { icon: 'entity', tint: 'var(--fg-3)' };
  const flag = entity.flag || '—';

  return (
    <article
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
        padding: '18px 18px 16px',
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span
          style={{
            width: 36,
            height: 36,
            borderRadius: 3,
            background: meta.tint,
            color: '#fff',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon name={meta.icon} size={18} />
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: 'var(--serif)',
              fontSize: 16,
              fontWeight: 500,
              color: 'var(--ink)',
              lineHeight: 1.25,
              wordBreak: 'break-word',
            }}
          >
            {entity.name}
          </div>
          <div
            style={{
              marginTop: 4,
              fontFamily: 'var(--mono)',
              fontSize: 10,
              letterSpacing: '0.12em',
              color: 'var(--fg-3)',
              textTransform: 'uppercase',
            }}
          >
            {type} · {flag}
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          gap: 8,
          paddingTop: 12,
          borderTop: '1px solid var(--line-soft)',
        }}
      >
        <Btn
          variant="outline"
          icon="graph"
          size="sm"
          onClick={onOpen}
          style={{ flex: 1, justifyContent: 'center' }}
        >
          Open in graph
        </Btn>
        <Btn
          variant="ghost"
          icon="x"
          size="sm"
          onClick={onRemove}
          title="Remove from watchlist"
        >
          Remove
        </Btn>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Empty / loading / no-project states
// ---------------------------------------------------------------------------

function EmptyState({ onOpenGraph }: { onOpenGraph: () => void }) {
  return (
    <div
      style={{
        marginTop: 32,
        padding: '64px 24px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 44,
          height: 44,
          borderRadius: 3,
          background: 'var(--paper)',
          border: '1px solid var(--line)',
          color: 'var(--fg-3)',
          marginBottom: 14,
        }}
      >
        <Icon name="star-o" size={20} />
      </span>
      <h2
        style={{
          margin: 0,
          fontFamily: 'var(--serif)',
          fontWeight: 500,
          fontSize: 22,
          color: 'var(--ink)',
        }}
      >
        No entities watched yet
      </h2>
      <p
        style={{
          margin: '6px auto 18px',
          maxWidth: 440,
          fontSize: 13,
          color: 'var(--fg-2)',
          lineHeight: 1.5,
        }}
      >
        Pin entities from the graph to monitor them here. Anything you star will surface in the
        hub digest and turn up new patterns automatically.
      </p>
      <Btn variant="solid" icon="graph" onClick={onOpenGraph}>
        Open the graph
      </Btn>
    </div>
  );
}

function LoadingState() {
  return (
    <div
      style={{
        marginTop: 32,
        padding: '64px 24px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        fontFamily: 'var(--mono)',
        fontSize: 11,
        letterSpacing: '0.16em',
        color: 'var(--fg-3)',
        textTransform: 'uppercase',
      }}
    >
      LOADING WATCHLIST…
    </div>
  );
}

function NoProject({ onOpenHub }: { onOpenHub: () => void }) {
  return (
    <div style={{ paddingBottom: 22, borderBottom: '1px solid var(--line)' }}>
      <span
        style={{
          fontFamily: 'var(--mono)',
          fontSize: 9.5,
          letterSpacing: '0.2em',
          color: 'var(--fg-3)',
          fontWeight: 600,
        }}
      >
        WATCHLIST · NO ACTIVE PROJECT
      </span>
      <h1
        style={{
          margin: '8px 0 0',
          fontFamily: 'var(--serif)',
          fontWeight: 500,
          fontSize: 32,
          color: 'var(--ink)',
          letterSpacing: '-0.015em',
        }}
      >
        No active project
      </h1>
      <p
        style={{
          margin: '8px 0 16px',
          maxWidth: 560,
          fontSize: 13.5,
          color: 'var(--fg-2)',
          lineHeight: 1.5,
        }}
      >
        Select or open a project from the hub to view its watchlist.
      </p>
      <Btn variant="solid" icon="arrow-right" onClick={onOpenHub}>
        Open hub
      </Btn>
    </div>
  );
}
