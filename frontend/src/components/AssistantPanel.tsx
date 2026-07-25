'use client';
/**
 * Aegis Intelligence Assistant — the single implementation.
 *
 * Replaces the two bespoke, drifting copies that used to live inside
 * `app/network/page.tsx` and `app/geo/page.tsx`. Mounted once in the root
 * layout so every view has it; the thread lives in `lib/AssistantContext` so it
 * survives navigation between views.
 *
 * Positioning deliberately avoids the chrome it used to fight with:
 *   - it is viewport-fixed to the bottom-RIGHT, clear of the fixed left rail;
 *   - `md:bottom-9` clears the 28px desktop StatusBar;
 *   - `bottom-20` clears the mobile bottom nav;
 *   - it is z-40, so page modals (z-50) still sit above it;
 *   - collapsed it is a small launcher, so it no longer covers the graph
 *     canvas / TemporalSlider on /network or the map on /geo;
 *   - on mobile it is inset with `left-2 right-2` (never a fixed width), so it
 *     cannot introduce horizontal overflow at 390px.
 *
 * NO STREAMING: `POST /api/query` returns a single JSON body. The only SSE
 * endpoint in the backend is `POST /api/topics/{id}/summarize`. Streaming this
 * path needs a backend change, so the panel shows an honest pending state
 * rather than faking incremental text.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import Markdown from './Markdown';
import AssistantCitations from './AssistantCitations';
import { useAssistant } from '@/lib/AssistantContext';
import { useProject } from '@/lib/ProjectContext';
import { useNotifications } from './NotificationProvider';
import { notebookApi, reportsApi } from '@/lib/api';

interface NotebookEntry {
  id: string;
  name?: string;
  content?: string;
  note_type?: string;
}

const NOTE_TYPES = ['observation', 'hypothesis', 'question', 'conclusion'];

/** Shared focus treatment so every control in the panel is keyboard-visible. */
const FOCUS = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-blue focus-visible:ring-offset-1 focus-visible:ring-offset-navy-800';

function ChatTab() {
  const { messages, busy, ask, clear, projectId } = useAssistant();
  const { addNotification } = useNotifications();
  const [input, setInput] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  // Keep the newest turn in view without scrolling the page behind the panel.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  const submit = useCallback(() => {
    const value = input.trim();
    if (!value) return;
    setInput('');
    void ask(value);
  }, [ask, input]);

  const saveAsProduct = useCallback(async (content: string, question: string) => {
    if (!projectId) return;
    try {
      await reportsApi.save({
        project_id: projectId,
        title: `RAG Response: ${question.slice(0, 50) || 'Query'}...`,
        content,
        report_type: 'RAG Analysis',
      });
      addNotification({ type: 'success', title: 'Saved', message: 'Response saved as product' });
    } catch {
      addNotification({ type: 'error', title: 'Failed', message: 'Could not save product' });
    }
  }, [addNotification, projectId]);

  return (
    <>
      <div ref={listRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
        {!projectId && (
          <p className="text-xs text-gray-500">
            No active project. Select one from the sidebar to query its knowledge graph.
          </p>
        )}
        {projectId && messages.length === 0 && (
          <p className="text-xs text-gray-500">
            Ask about the knowledge graph. Answers are grounded in the project&apos;s entities,
            relationships, and source documents — expand <span className="text-gray-400">Sources</span> on
            any answer to see what it was based on.
          </p>
        )}

        {messages.map((msg, i) => (
          <div key={msg.id}>
            <div className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-xs break-words ${
                  msg.role === 'user'
                    ? 'bg-accent-blue text-white'
                    : msg.failed
                      ? 'bg-navy-900 text-threat-high border border-threat-high/40'
                      : 'bg-navy-900 text-gray-200'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <Markdown content={msg.content} />
                ) : (
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                )}
              </div>
            </div>

            {msg.role === 'assistant' && !msg.failed && (
              <div className="ml-1">
                {msg.grounding && <AssistantCitations grounding={msg.grounding} />}
                {msg.content.length > 50 && (
                  <button
                    type="button"
                    onClick={() => saveAsProduct(msg.content, messages[i - 1]?.content ?? '')}
                    className={`mt-1 text-[10px] px-2 py-0.5 rounded bg-navy-700 text-accent-blue hover:bg-navy-600 transition-colors ${FOCUS}`}
                  >
                    Save as Product
                  </button>
                )}
              </div>
            )}
          </div>
        ))}

        {busy && (
          <div className="flex justify-start" role="status" aria-live="polite">
            <div className="rounded-lg px-3 py-2 text-xs bg-navy-900 text-gray-500">Thinking…</div>
          </div>
        )}
      </div>

      <div className="px-3 py-2.5 flex gap-2 shrink-0 border-t border-navy-600">
        <label htmlFor="assistant-chat-input" className="sr-only">Ask the intelligence assistant</label>
        <input
          id="assistant-chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={!projectId}
          placeholder={projectId ? 'Ask about the knowledge graph…' : 'Select a project first'}
          className={`flex-1 min-w-0 rounded bg-navy-900 border border-navy-600 px-3 py-1.5 text-sm text-gray-200 placeholder:text-gray-600 disabled:opacity-50 ${FOCUS}`}
        />
        <button
          type="button"
          onClick={submit}
          disabled={busy || !projectId || !input.trim()}
          className={`px-3 py-1.5 rounded text-sm font-medium bg-accent-blue text-white disabled:opacity-40 shrink-0 ${FOCUS}`}
        >
          Send
        </button>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={clear}
            title="Clear conversation"
            className={`px-2 py-1.5 rounded text-xs text-gray-500 hover:text-gray-300 shrink-0 ${FOCUS}`}
          >
            Clear
          </button>
        )}
      </div>
    </>
  );
}

function NotebookTab() {
  const { projectId, linkedEntities } = useAssistant();
  const [notes, setNotes] = useState<NotebookEntry[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [noteType, setNoteType] = useState(NOTE_TYPES[0]);

  const loadNotes = useCallback(async () => {
    if (!projectId) {
      setNotes([]);
      return;
    }
    try {
      const res = await notebookApi.list(projectId);
      setNotes(Array.isArray(res.data) ? res.data : []);
    } catch {
      setNotes([]);
    }
  }, [projectId]);

  useEffect(() => { void loadNotes(); }, [loadNotes]);

  const createNote = useCallback(async () => {
    if (!projectId || !title.trim() || !content.trim()) return;
    try {
      await notebookApi.create({
        project_id: projectId,
        title,
        content,
        entity_ids: linkedEntities.map(e => e.id),
        note_type: noteType,
      });
      setTitle('');
      setContent('');
      setNoteType(NOTE_TYPES[0]);
      setFormOpen(false);
      void loadNotes();
    } catch {
      /* surfaced by the empty list not changing; keep the draft */
    }
  }, [content, linkedEntities, loadNotes, noteType, projectId, title]);

  const deleteNote = useCallback(async (id: string) => {
    try {
      await notebookApi.delete(id);
      void loadNotes();
    } catch { /* ignore */ }
  }, [loadNotes]);

  if (!projectId) {
    return (
      <div className="flex-1 px-3 py-3">
        <p className="text-xs text-gray-500">No active project. Select one to keep an analyst notebook.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-navy-600 shrink-0">
        <span className="text-xs text-gray-400">{notes.length} note{notes.length === 1 ? '' : 's'}</span>
        <button
          type="button"
          onClick={() => setFormOpen(v => !v)}
          aria-expanded={formOpen}
          className={`text-xs px-2.5 py-1 rounded font-medium bg-accent-blue text-white ${FOCUS}`}
        >
          {formOpen ? 'Cancel' : 'New Note'}
        </button>
      </div>

      {formOpen ? (
        <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
          <label htmlFor="assistant-note-title" className="sr-only">Note title</label>
          <input
            id="assistant-note-title"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Note title…"
            className={`w-full rounded bg-navy-900 border border-navy-600 px-3 py-1.5 text-xs text-gray-200 placeholder:text-gray-600 ${FOCUS}`}
          />
          <label htmlFor="assistant-note-body" className="sr-only">Note body</label>
          <textarea
            id="assistant-note-body"
            value={content}
            onChange={e => setContent(e.target.value)}
            placeholder="Write your note…"
            className={`w-full h-20 resize-none rounded bg-navy-900 border border-navy-600 px-3 py-1.5 text-xs text-gray-200 placeholder:text-gray-600 ${FOCUS}`}
          />
          <div className="flex items-center gap-2 flex-wrap">
            <label htmlFor="assistant-note-type" className="sr-only">Note type</label>
            <select
              id="assistant-note-type"
              value={noteType}
              onChange={e => setNoteType(e.target.value)}
              className={`rounded bg-navy-900 border border-navy-600 px-2 py-1 text-xs text-gray-200 ${FOCUS}`}
            >
              {NOTE_TYPES.map(t => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>
            {linkedEntities.length > 0 && (
              <span className="text-[10px] text-gray-400">Linking {linkedEntities.length} entities</span>
            )}
            <button
              type="button"
              onClick={createNote}
              disabled={!title.trim() || !content.trim()}
              className={`ml-auto px-3 py-1 rounded text-xs font-medium bg-accent-cyan text-navy-900 disabled:opacity-40 ${FOCUS}`}
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
          {notes.length === 0 ? (
            <p className="text-xs text-gray-500 text-center py-4">No notebook entries yet.</p>
          ) : notes.map(note => (
            <div key={note.id} className="rounded-lg bg-navy-900 p-2.5 text-xs">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-medium text-gray-200 truncate">{note.name}</span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-navy-700 text-gray-400">
                    {note.note_type || 'note'}
                  </span>
                  <button
                    type="button"
                    onClick={() => deleteNote(note.id)}
                    className={`text-threat-critical hover:opacity-80 text-[10px] ${FOCUS}`}
                  >
                    Delete
                  </button>
                </div>
              </div>
              <p className="text-gray-400 truncate">{note.content || ''}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AssistantPanel() {
  const { open, setOpen, tab, setTab, busy, messages } = useAssistant();
  const { activeProject } = useProject();
  const pathname = usePathname();
  const panelRef = useRef<HTMLDivElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  // The launcher and the panel are alternatives, so toggling unmounts whichever
  // element had focus. Remember that the *user* toggled (as opposed to a page
  // opening the panel to show a task result, where stealing focus would yank
  // the analyst out of the view they were working in) and restore it after the
  // re-render that swaps the two.
  const restoreFocus = useRef(false);

  useEffect(() => {
    if (!restoreFocus.current) return;
    restoreFocus.current = false;
    if (open) panelRef.current?.focus();
    else launcherRef.current?.focus();
  }, [open]);

  const toggle = (next: boolean) => {
    restoreFocus.current = true;
    setOpen(next);
  };

  // Escape closes the panel from anywhere inside it.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Escape') return;
      const el = panelRef.current;
      if (el && el.contains(document.activeElement)) {
        restoreFocus.current = true;
        setOpen(false);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, setOpen]);

  // The login view has no project, no auth token, and no chrome to assist.
  if (pathname?.startsWith('/login')) return null;

  if (!open) {
    return (
      <button
        ref={launcherRef}
        type="button"
        onClick={() => toggle(true)}
        aria-expanded={false}
        aria-controls="assistant-panel"
        className={`fixed right-3 bottom-20 md:bottom-9 z-40 flex items-center gap-2 rounded-full border border-navy-600 bg-navy-800 pl-2 pr-3.5 py-2 shadow-2xl hover:border-accent-blue transition-colors ${FOCUS}`}
      >
        <span className="w-6 h-6 rounded-full bg-accent-blue text-white flex items-center justify-center text-[10px] font-bold shrink-0">
          AI
        </span>
        <span className="text-xs font-medium text-gray-200">Aegis</span>
        {busy && <span className="w-2 h-2 rounded-full bg-accent-cyan animate-pulse" aria-hidden="true" />}
        {!busy && messages.length > 0 && (
          <span className="text-[10px] text-gray-500">{messages.length}</span>
        )}
      </button>
    );
  }

  return (
    <div
      id="assistant-panel"
      ref={panelRef}
      role="region"
      aria-label="Aegis Intelligence Assistant"
      tabIndex={-1}
      className="fixed z-40 left-2 right-2 bottom-20 md:left-auto md:right-4 md:bottom-9 md:w-[26rem] max-h-[70vh] md:max-h-[34rem] flex flex-col rounded-xl border border-navy-600 bg-navy-800 shadow-2xl overflow-hidden"
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b border-navy-600 shrink-0">
        <span className="w-6 h-6 rounded-full bg-accent-blue text-white flex items-center justify-center text-[10px] font-bold shrink-0">
          AI
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-gray-200 truncate">Aegis Intelligence Assistant</p>
          <p className="text-[10px] text-gray-500 truncate">
            {activeProject ? activeProject.name : 'No active project'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => toggle(false)}
          aria-label="Collapse assistant"
          className={`p-1 rounded text-gray-400 hover:text-gray-200 hover:bg-navy-700 shrink-0 ${FOCUS}`}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      <div role="tablist" aria-label="Assistant sections" className="flex gap-1 px-2 py-1.5 border-b border-navy-600 shrink-0">
        {([['chat', 'Graph RAG Chat'], ['notebook', 'Notebook']] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`assistant-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`assistant-tabpanel-${id}`}
            onClick={() => setTab(id)}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${FOCUS} ${
              tab === id ? 'bg-navy-700 text-accent-blue' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`assistant-tabpanel-${tab}`}
        aria-labelledby={`assistant-tab-${tab}`}
        className="flex flex-col flex-1 min-h-0"
      >
        {tab === 'chat' ? <ChatTab /> : <NotebookTab />}
      </div>
    </div>
  );
}
