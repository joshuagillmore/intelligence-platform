'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Icon } from './Icon';
import { Tag } from './Primitives';
import { useNotifications, useNotificationCount } from '@/components/NotificationProvider';
import { APP_NOTIFICATIONS, type AppNotification } from '@/components/sentinel/mockData';

function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const NOTIF_TYPE_ICON: Record<AppNotification['type'], string> = {
  evidence: 'doc',
  agent: 'sparkle',
  change: 'arrow-up-right',
  community: 'graph',
  product: 'product',
  watch: 'star',
};
const NOTIF_TYPE_TONE: Record<AppNotification['type'], string> = {
  evidence: 'var(--cite)',
  agent: 'var(--signal-ink)',
  change: 'var(--ink)',
  community: 'var(--violet)',
  product: 'var(--live)',
  watch: 'var(--signal)',
};

export function NotificationBell() {
  const router = useRouter();
  const { notifications, removeNotification } = useNotifications();
  const toastUnread = useNotificationCount();
  const [systemNotifs, setSystemNotifs] = useState<AppNotification[]>(APP_NOTIFICATIONS);
  const systemUnread = systemNotifs.filter((n) => !n.read).length;
  const unread = toastUnread + systemUnread;
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const markAllRead = () => setSystemNotifs((prev) => prev.map((n) => ({ ...n, read: true })));
  const openNotif = (n: AppNotification) => {
    setSystemNotifs((prev) => prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
    setOpen(false);
    const path = n.action === 'review' ? '/review' : n.action === 'products' ? '/products' : `/${n.action}`;
    router.push(path);
  };

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        title="Notifications"
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 32,
          height: 32,
          background: 'transparent',
          border: 'none',
          borderRadius: 4,
          cursor: 'pointer',
          color: 'var(--fg-2)',
        }}
      >
        <Icon name="flag" size={18} />
        {unread > 0 && (
          <span
            style={{
              position: 'absolute',
              top: 4,
              right: 4,
              minWidth: 14,
              height: 14,
              padding: '0 3px',
              borderRadius: 8,
              background: 'var(--signal)',
              color: 'var(--ink)',
              fontFamily: 'var(--mono)',
              fontSize: 9,
              fontWeight: 700,
              lineHeight: '14px',
              textAlign: 'center',
            }}
          >
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            width: 320,
            maxHeight: 420,
            overflowY: 'auto',
            background: 'var(--paper)',
            border: '1px solid var(--line)',
            borderRadius: 4,
            boxShadow: '0 12px 32px rgba(15,18,22,0.18)',
            zIndex: 100,
          }}
        >
          {/* SYSTEM notifications — persistent inbox */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 14px',
              borderBottom: '1px solid var(--line-soft)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 9.5,
                letterSpacing: '0.18em',
                color: 'var(--fg-3)',
                fontWeight: 600,
              }}
            >
              INBOX · {systemUnread} UNREAD
            </span>
            {systemUnread > 0 && (
              <button
                onClick={markAllRead}
                style={{
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.08em',
                  color: 'var(--cite)',
                }}
              >
                MARK ALL READ
              </button>
            )}
          </div>
          {systemNotifs.length === 0 ? (
            <div style={{ padding: '14px 14px', textAlign: 'center', fontSize: 11.5, color: 'var(--fg-3)' }}>
              No system notifications
            </div>
          ) : (
            systemNotifs.slice(0, 8).map((n) => (
              <button
                key={n.id}
                onClick={() => openNotif(n)}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '10px 14px',
                  borderBottom: '1px solid var(--line-soft)',
                  background: n.read ? 'transparent' : 'var(--signal-soft)',
                  border: 'none', cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                  <span style={{ color: NOTIF_TYPE_TONE[n.type] }}>
                    <Icon name={NOTIF_TYPE_ICON[n.type]} size={12} />
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {n.title}
                  </span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)', flexShrink: 0 }}>{n.t}</span>
                </div>
                <p style={{ margin: '2px 0 0 18px', fontSize: 11, color: 'var(--fg-2)', lineHeight: 1.4 }}>{n.body}</p>
              </button>
            ))
          )}

          {/* Existing in-flight toast notifications (live processing/success/error) */}
          {notifications.length > 0 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderTop: '1px solid var(--line)',
                borderBottom: '1px solid var(--line-soft)',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 9.5,
                  letterSpacing: '0.18em',
                  color: 'var(--fg-3)',
                  fontWeight: 600,
                }}
              >
                IN-FLIGHT · {notifications.length}
              </span>
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  color: 'var(--fg-3)',
                }}
              >
                {notifications.length}
              </span>
            </div>
          )}

          {notifications.length > 0 && notifications.slice(0, 20).map((n) => (
            <div key={n.id} style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-soft)' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                  <NotifIcon type={n.type} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {n.title}
                  </span>
                </div>
                <button
                  onClick={() => removeNotification(n.id)}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--fg-4)', fontSize: 14, lineHeight: 1 }}
                  aria-label="Dismiss"
                >
                  ×
                </button>
              </div>
              <p style={{ margin: '4px 0 2px 18px', fontSize: 11, color: 'var(--fg-2)', lineHeight: 1.4 }}>
                {n.message}
              </p>
              <p
                style={{ margin: '2px 0 0 18px', fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)', letterSpacing: '0.04em' }}
                suppressHydrationWarning
              >
                {formatTimeAgo(n.timestamp)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function NotifIcon({ type }: { type: 'info' | 'success' | 'error' | 'processing' }) {
  if (type === 'processing')
    return (
      <span
        style={{
          width: 12,
          height: 12,
          border: '2px solid var(--line)',
          borderTopColor: 'var(--signal)',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
          flexShrink: 0,
        }}
      />
    );
  const map: Record<string, { ch: string; color: string }> = {
    success: { ch: '✓', color: 'var(--live)' },
    error:   { ch: '✕', color: 'var(--warn)' },
    info:    { ch: 'ⓘ', color: 'var(--cite)' },
  };
  const m = map[type] || map.info;
  return (
    <span style={{ color: m.color, fontSize: 12, lineHeight: 1, flexShrink: 0 }}>{m.ch}</span>
  );
}

interface UserMenuProps {
  username: string;
  role: string;
}

export function UserMenu({ username, role }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const initials = username
    ? username
        .split(/\s+/)
        .map((w) => w.charAt(0).toUpperCase())
        .slice(0, 2)
        .join('')
    : 'A';

  function signOut() {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      localStorage.removeItem('auth_role');
      window.location.href = '/login';
    }
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 4px 0 0',
          height: 32,
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--ink)',
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: 'var(--ink)',
            color: 'var(--paper)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: 'var(--mono)',
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: '0.04em',
            flexShrink: 0,
          }}
          suppressHydrationWarning
        >
          {initials}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, textAlign: 'left' }}>
          <span
            style={{ fontSize: 12, fontWeight: 500, lineHeight: 1, color: 'var(--ink)' }}
            suppressHydrationWarning
          >
            {username}
          </span>
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 9,
              color: 'var(--fg-3)',
              lineHeight: 1,
              letterSpacing: '0.04em',
            }}
            suppressHydrationWarning
          >
            {role}
          </span>
        </div>
        <Icon name="chevron-down" size={12} />
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            width: 200,
            background: 'var(--paper)',
            border: '1px solid var(--line)',
            borderRadius: 4,
            boxShadow: '0 12px 32px rgba(15,18,22,0.18)',
            zIndex: 100,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '10px 14px',
              borderBottom: '1px solid var(--line-soft)',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)' }} suppressHydrationWarning>
              {username}
            </span>
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 10,
                color: 'var(--fg-3)',
                letterSpacing: '0.04em',
              }}
              suppressHydrationWarning
            >
              {role}
            </span>
          </div>
          <button
            disabled
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              padding: '8px 14px',
              background: 'transparent',
              border: 'none',
              cursor: 'not-allowed',
              color: 'var(--fg-3)',
              fontSize: 12,
              textAlign: 'left',
            }}
          >
            <Icon name="layers" size={13} />
            <span>Profile</span>
            <Tag>SOON</Tag>
          </button>
          <button
            onClick={signOut}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              padding: '8px 14px',
              background: 'transparent',
              border: 'none',
              borderTop: '1px solid var(--line-soft)',
              cursor: 'pointer',
              color: 'var(--warn)',
              fontSize: 12,
              textAlign: 'left',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--paper-2)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <Icon name="arrow-right" size={13} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
