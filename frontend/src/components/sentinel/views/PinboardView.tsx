'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { Btn, Tag, Icon } from '@/components/sentinel';
import { useProject } from '@/lib/ProjectContext';
import { notebookApi } from '@/lib/api';
import { useNotifications } from '@/components/NotificationProvider';

type NoteKind = 'entity' | 'quote' | 'note' | 'finding' | 'gap' | 'pin';
type FilterKind = 'all' | NoteKind;

interface NotebookNote {
  id: string;
  project_id?: string;
  title?: string;
  content?: string;
  note_type?: string;
  entity_ids?: string[];
  created_at?: string;
}

const KIND_TONES: Record<NoteKind, { tint: string; label: string; icon: string }> = {
  entity:  { tint: 'var(--cite)',      label: 'ENTITY',  icon: 'entity'  },
  quote:   { tint: 'var(--cite)',      label: 'QUOTE',   icon: 'sparkle' },
  note:    { tint: 'var(--violet)',    label: 'NOTE',    icon: 'doc'     },
  finding: { tint: 'var(--live)',      label: 'FINDING', icon: 'check'   },
  gap:     { tint: 'var(--warn)',      label: 'GAP',     icon: 'bolt'    },
  pin:     { tint: 'var(--signal-ink)', label: 'PIN',    icon: 'star'    },
};

function normKind(t?: string): NoteKind {
  const k = (t || 'note').toLowerCase();
  if (k in KIND_TONES) return k as NoteKind;
  return 'note';
}

export function PinboardView() {
  const { activeProject } = useProject();
  const { addNotification, updateNotification } = useNotifications();
  const [notes, setNotes] = useState<NotebookNote[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKind>('all');
  const [composing, setComposing] = useState(false);

  const refresh = useCallback(() => {
    if (!activeProject) { setNotes([]); return; }
    setLoading(true);
    notebookApi
      .list(activeProject.id)
      .then((res) => {
        const raw = res.data as NotebookNote[] | { notebook?: NotebookNote[]; notes?: NotebookNote[] };
        const list = Array.isArray(raw)
          ? raw
          : (raw?.notebook ?? raw?.notes ?? []);
        setNotes(Array.isArray(list) ? list : []);
      })
      .catch(() => setNotes([]))
      .finally(() => setLoading(false));
  }, [activeProject]);

  useEffect(() => { refresh(); }, [refresh]);

  const visible = filter === 'all' ? notes : notes.filter((n) => normKind(n.note_type) === filter);
  const selected = notes.find((n) => n.id === selectedId);

  const onDelete = async (id: string) => {
    const toastId = addNotification({ type: 'processing', title: 'Deleting pin', message: '' });
    try {
      await notebookApi.delete(id);
      setNotes((prev) => prev.filter((n) => n.id !== id));
      if (selectedId === id) setSelectedId(null);
      updateNotification(toastId, { type: 'success', title: 'Pin deleted', message: '' });
    } catch (e) {
      updateNotification(toastId, { type: 'error', title: 'Delete failed', message: (e as Error).message });
    }
  };

  if (!activeProject) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: 'var(--fg-3)' }}>
        <Icon name="pinboard" size={36} />
        <h2 style={{ margin: '12px 0 6px', fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
          No active project
        </h2>
        <p style={{ fontSize: 13 }}>Pinboards are project-scoped. Open one from the Hub.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', height: '100%', overflow: 'hidden' }}>
      <main style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--paper)' }}>
        <Toolbar
          filter={filter}
          setFilter={setFilter}
          count={visible.length}
          total={notes.length}
          onAddPin={() => setComposing(true)}
        />
        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {loading ? (
            <p style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)', letterSpacing: '0.08em' }}>LOADING…</p>
          ) : visible.length === 0 ? (
            <EmptyState filtered={filter !== 'all'} total={notes.length} onAdd={() => setComposing(true)} />
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                gap: 14,
              }}
            >
              {visible.map((n) => (
                <PinCard
                  key={n.id}
                  note={n}
                  selected={selectedId === n.id}
                  onClick={() => setSelectedId(n.id)}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      <aside style={{ background: 'var(--paper-2)', borderLeft: '1px solid var(--line)', overflow: 'auto' }}>
        <Inspector
          note={selected}
          onDelete={() => selected && onDelete(selected.id)}
        />
      </aside>

      {composing && (
        <Composer
          projectId={activeProject.id}
          onClose={() => setComposing(false)}
          onCreated={(n) => {
            setNotes((prev) => [n, ...prev]);
            setSelectedId(n.id);
            setComposing(false);
          }}
        />
      )}
    </div>
  );
}

function Toolbar({
  filter,
  setFilter,
  count,
  total,
  onAddPin,
}: {
  filter: FilterKind;
  setFilter: (f: FilterKind) => void;
  count: number;
  total: number;
  onAddPin: () => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '14px 24px',
        borderBottom: '1px solid var(--line)',
        background: 'var(--paper)',
      }}
    >
      <div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.18em', color: 'var(--fg-3)' }}>
          PINBOARD
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
          <h1 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>
            Project notebook
          </h1>
          <Tag>{count} of {total}</Tag>
        </div>
      </div>
      <span style={{ flex: 1 }} />
      {(['all', 'pin', 'note', 'finding', 'gap'] as const).map((k) => (
        <button
          key={k}
          onClick={() => setFilter(k)}
          style={{
            padding: '4px 10px',
            fontFamily: 'var(--mono)',
            fontSize: 10,
            letterSpacing: '0.1em',
            border: '1px solid var(--line)',
            borderRadius: 2,
            background: filter === k ? 'var(--ink)' : 'transparent',
            color: filter === k ? 'var(--paper)' : 'var(--fg-2)',
            cursor: 'pointer',
            textTransform: 'uppercase',
          }}
        >
          {k}
        </button>
      ))}
      <Btn variant="outline" icon="plus" size="sm" onClick={onAddPin}>
        Add pin
      </Btn>
    </div>
  );
}

function PinCard({ note, selected, onClick }: { note: NotebookNote; selected: boolean; onClick: () => void }) {
  const kind = normKind(note.note_type);
  const tone = KIND_TONES[kind];
  const text = (note.content || '').trim();
  const preview = text.length > 220 ? text.slice(0, 218) + '…' : text;
  return (
    <button
      onClick={onClick}
      style={{
        position: 'relative',
        padding: '12px 14px 14px 18px',
        background: 'var(--paper-2)',
        border: '1px solid ' + (selected ? 'var(--ink)' : 'var(--line)'),
        borderRadius: 3,
        textAlign: 'left',
        cursor: 'pointer',
        overflow: 'hidden',
        minHeight: 120,
      }}
    >
      <span style={{ position: 'absolute', top: 0, left: 0, width: 3, height: '100%', background: tone.tint }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <Icon name={tone.icon} size={11} />
        <span style={{ fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.12em', color: tone.tint, fontWeight: 600 }}>
          {tone.label}
        </span>
        <span style={{ flex: 1 }} />
        {note.created_at && (
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)' }}>
            {new Date(note.created_at).toLocaleDateString()}
          </span>
        )}
      </div>
      {note.title && (
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginBottom: 4, lineHeight: 1.3 }}>
          {note.title}
        </div>
      )}
      {preview && (
        <p
          style={{
            margin: 0,
            fontFamily: kind === 'quote' ? 'var(--serif)' : 'var(--sans)',
            fontStyle: kind === 'quote' ? 'italic' : 'normal',
            fontSize: 11.5, color: 'var(--fg-2)', lineHeight: 1.45,
          }}
        >
          {preview}
        </p>
      )}
    </button>
  );
}

function Inspector({ note, onDelete }: { note?: NotebookNote; onDelete: () => void }) {
  if (!note) {
    return (
      <div style={{ padding: '20px', fontSize: 13, color: 'var(--fg-3)' }}>
        Click any pin to inspect it.
      </div>
    );
  }
  const kind = normKind(note.note_type);
  const tone = KIND_TONES[kind];
  return (
    <div style={{ padding: '18px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: tone.tint }} />
        <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.2em', color: 'var(--fg-3)', fontWeight: 600 }}>
          {tone.label} · PIN
        </div>
      </div>
      {note.title && (
        <h3 style={{ margin: '0 0 10px', fontFamily: 'var(--serif)', fontSize: 18, fontWeight: 500, color: 'var(--ink)', letterSpacing: '-0.01em' }}>
          {note.title}
        </h3>
      )}
      {note.content && (
        <p
          style={{
            margin: '0 0 12px',
            fontFamily: kind === 'quote' ? 'var(--serif)' : 'var(--sans)',
            fontStyle: kind === 'quote' ? 'italic' : 'normal',
            fontSize: 13, lineHeight: 1.5, color: 'var(--ink)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {note.content}
        </p>
      )}
      {note.entity_ids && note.entity_ids.length > 0 && (
        <div style={{ marginTop: 8, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)' }}>
          ENTITIES · {note.entity_ids.length}
        </div>
      )}
      {note.created_at && (
        <div style={{ marginTop: 8, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)' }}>
          CREATED · {new Date(note.created_at).toLocaleString()}
        </div>
      )}
      <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--line)' }}>
        <Btn variant="outline" icon="x" size="sm" onClick={onDelete} style={{ color: 'var(--warn)' }}>
          Delete pin
        </Btn>
      </div>
    </div>
  );
}

function EmptyState({ filtered, total, onAdd }: { filtered: boolean; total: number; onAdd: () => void }) {
  return (
    <div style={{ padding: '48px 24px', textAlign: 'center' }}>
      <Icon name="pinboard" size={32} />
      <h3 style={{ margin: '14px 0 6px', fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
        {filtered ? 'No pins match this filter' : 'Pinboard is empty'}
      </h3>
      <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--fg-3)' }}>
        {filtered
          ? `${total} pin${total === 1 ? '' : 's'} on this board — try a different filter.`
          : 'Drop a pin to start case-building.'}
      </p>
      {!filtered && (
        <Btn variant="signal" icon="plus" size="sm" onClick={onAdd}>
          Add first pin
        </Btn>
      )}
    </div>
  );
}

function Composer({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: (n: NotebookNote) => void;
}) {
  const { addNotification, updateNotification } = useNotifications();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [kind, setKind] = useState<NoteKind>('pin');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const t = title.trim();
    const c = content.trim();
    if (!t && !c) return;
    setSaving(true);
    const toastId = addNotification({ type: 'processing', title: 'Saving pin', message: t || c.slice(0, 60) });
    try {
      const res = await notebookApi.create({
        project_id: projectId,
        title: t || 'Untitled pin',
        content: c,
        note_type: kind,
      });
      const created = res.data as NotebookNote;
      updateNotification(toastId, { type: 'success', title: 'Pin saved', message: '' });
      onCreated(created);
    } catch (e) {
      updateNotification(toastId, { type: 'error', title: 'Save failed', message: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(20, 20, 20, 0.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 480, maxHeight: '85vh',
          background: 'var(--paper)', border: '1px solid var(--line)',
          borderRadius: 4, padding: '20px 22px',
          display: 'flex', flexDirection: 'column', gap: 12, overflow: 'auto',
        }}
      >
        <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.18em', color: 'var(--fg-3)' }}>
          NEW PIN
        </div>
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title"
          style={{
            padding: '10px 12px', fontSize: 14, fontFamily: 'var(--serif)',
            border: '1px solid var(--line)', borderRadius: 2,
            background: 'var(--paper-2)', color: 'var(--ink)', outline: 'none',
          }}
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Content, quote, or finding…"
          rows={6}
          style={{
            padding: '10px 12px', fontSize: 13, fontFamily: 'var(--serif)',
            border: '1px solid var(--line)', borderRadius: 2,
            background: 'var(--paper-2)', color: 'var(--ink)', outline: 'none',
            resize: 'vertical',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.1em' }}>
            KIND
          </span>
          {(['pin', 'note', 'finding', 'gap', 'quote'] as const).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              style={{
                padding: '4px 8px', borderRadius: 2,
                background: kind === k ? 'var(--ink)' : 'transparent',
                color: kind === k ? 'var(--paper)' : 'var(--fg-2)',
                border: '1px solid ' + (kind === k ? 'var(--ink)' : 'var(--line)'),
                fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', cursor: 'pointer',
                textTransform: 'uppercase',
              }}
            >
              {k}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
          <Btn variant="ghost" onClick={onClose} size="sm">Cancel</Btn>
          <span style={{ flex: 1 }} />
          <Btn variant="signal" icon="check" onClick={submit} size="sm">
            {saving ? 'Saving…' : 'Save pin'}
          </Btn>
        </div>
      </div>
    </div>
  );
}
