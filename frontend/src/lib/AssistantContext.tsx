'use client';
/**
 * Shared state for the Aegis Intelligence Assistant.
 *
 * The assistant used to be implemented twice (a bespoke overlay on /network and
 * another on /geo) and existed nowhere else. It is now one component mounted in
 * the root layout, so the thread has to live above the pages: this context owns
 * the conversation, the busy flag, open/tab UI state, and the entities a page
 * wants attached to new notebook entries.
 *
 * Thread persistence is per project and hydration-safe. Following the pattern
 * in ProjectContext, localStorage is NEVER read in a useState initializer —
 * that renders one thing on the server and another on the first client render,
 * which is exactly the app-wide hydration mismatch (React #418/#423) that was
 * fixed and is now guarded by tests. It is read in a post-mount effect instead.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { queryApi } from './api';
import { useProject } from './ProjectContext';
import {
  compactGroundingForStorage,
  parseGrounding,
  sanitizeGrounding,
  type AssistantGrounding,
} from './assistantGrounding';

export type AssistantRole = 'user' | 'assistant';

export interface AssistantMessage {
  id: string;
  role: AssistantRole;
  content: string;
  /** Set on assistant turns that failed, so the UI can mark them. */
  failed?: boolean;
  /** Citations/grounding for RAG answers; null for plain LLM task output. */
  grounding?: AssistantGrounding | null;
}

/** What a page-contributed task resolves to. */
export interface AssistantTaskResult {
  content: string;
  grounding?: AssistantGrounding | null;
}

export interface LinkedEntity {
  id: string;
  name: string;
}

export type AssistantTab = 'chat' | 'notebook';

interface AssistantContextValue {
  messages: AssistantMessage[];
  busy: boolean;
  open: boolean;
  setOpen: (open: boolean) => void;
  tab: AssistantTab;
  setTab: (tab: AssistantTab) => void;
  /** Project the thread belongs to; null when no project is active. */
  projectId: string | null;
  /** Ask the Graph-RAG endpoint a question and append both turns. */
  ask: (question: string) => Promise<void>;
  /**
   * Run a page-owned intelligence task (gap analysis, assessment, …) and render
   * its output in the shared thread. The page keeps its own domain logic; only
   * the presentation is shared.
   */
  runTask: (task: { label: string; run: () => Promise<AssistantTaskResult> }) => Promise<void>;
  clear: () => void;
  /** Entities a page has selected; new notebook entries link to them. */
  linkedEntities: LinkedEntity[];
  setLinkedEntities: (entities: LinkedEntity[]) => void;
}

const noop = () => {};
const AssistantContext = createContext<AssistantContextValue>({
  messages: [],
  busy: false,
  open: false,
  setOpen: noop,
  tab: 'chat',
  setTab: noop,
  projectId: null,
  ask: async () => {},
  runTask: async () => {},
  clear: noop,
  linkedEntities: [],
  setLinkedEntities: noop,
});

/** Keep stored threads small — localStorage is a shared 5MB budget. */
const MAX_STORED_MESSAGES = 40;
const STORAGE_PREFIX = 'assistant_thread:';

function storageKey(projectId: string | null): string {
  return `${STORAGE_PREFIX}${projectId ?? '_none'}`;
}

function readThread(projectId: string | null): AssistantMessage[] {
  if (typeof window === 'undefined') return [];
  try {
    const stored = localStorage.getItem(storageKey(projectId));
    if (!stored) return [];
    const parsed = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (m): m is AssistantMessage =>
          !!m && typeof m.id === 'string' && typeof m.content === 'string'
          && (m.role === 'user' || m.role === 'assistant'),
      )
      // The panel renders in the root layout and the app has no error boundary,
      // so a malformed `grounding` (corrupt storage, or a thread written by an
      // older shape) would throw on `.map` and blank every route until the user
      // cleared storage by hand. Coerce it to something renderable instead.
      .map(m => ({ ...m, grounding: sanitizeGrounding(m.grounding) }));
  } catch {
    return []; // malformed or unavailable storage — start clean
  }
}

/** Remove every stored assistant thread except (optionally) one to keep. */
function pruneThreads(keepKey?: string) {
  if (typeof window === 'undefined') return;
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(STORAGE_PREFIX) && key !== keepKey) localStorage.removeItem(key);
    }
  } catch { /* storage unavailable */ }
}

/**
 * Drop every persisted assistant thread. Called on logout — these threads hold
 * RAG answers and verbatim source-document excerpts, which must not outlive the
 * session on a shared analyst workstation.
 */
export function clearAllAssistantThreads() {
  pruneThreads();
}

function writeThread(projectId: string | null, messages: AssistantMessage[]) {
  if (typeof window === 'undefined') return;
  const key = storageKey(projectId);
  try {
    if (messages.length === 0) {
      localStorage.removeItem(key);
      return;
    }
    const payload = JSON.stringify(
      messages.slice(-MAX_STORED_MESSAGES).map(m => ({
        ...m,
        grounding: compactGroundingForStorage(m.grounding),
      })),
    );
    try {
      localStorage.setItem(key, payload);
    } catch {
      // Almost certainly the quota: other projects' threads are the only thing
      // this feature owns, so reclaim them and retry once before giving up.
      pruneThreads(key);
      localStorage.setItem(key, payload);
    }
  } catch {
    /* quota still exceeded / private mode — the in-memory thread still works */
  }
}

let messageSeq = 0;
function nextId(): string {
  messageSeq += 1;
  return `m${Date.now().toString(36)}-${messageSeq}`;
}

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { activeProject } = useProject();
  const projectId = activeProject?.id ?? null;

  // projectId + messages live in ONE state object so the persist effect can
  // tell "these messages belong to the project currently in context" from
  // "we are mid-swap and the thread has not been re-hydrated yet". Null means
  // not yet hydrated — the value rendered on the server and on first paint.
  const [thread, setThread] = useState<{ projectId: string | null; messages: AssistantMessage[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<AssistantTab>('chat');
  const [linkedEntities, setLinkedEntities] = useState<LinkedEntity[]>([]);

  // Post-mount (and on project switch): load that project's stored thread.
  useEffect(() => {
    setThread({ projectId, messages: readThread(projectId) });
  }, [projectId]);

  // Persist, but never write a stale thread under a freshly switched project.
  useEffect(() => {
    if (!thread || thread.projectId !== projectId) return;
    writeThread(projectId, thread.messages);
  }, [thread, projectId]);

  const messages = useMemo(() => thread?.messages ?? [], [thread]);

  // Appends are addressed to the project that was active when the request was
  // issued. A request in flight across a project switch must NOT land in the
  // new project's thread — in a tool built on project compartmentation, an
  // answer about project A appearing (and persisting) under project B is worse
  // than losing it. The reply is dropped if the analyst has moved on.
  const append = useCallback((forProject: string | null, message: AssistantMessage) => {
    setThread(prev =>
      prev && prev.projectId === forProject
        ? { ...prev, messages: [...prev.messages, message] }
        : prev,
    );
  }, []);

  // `busy` is also mirrored in a ref so two calls dispatched within a single
  // tick (key-repeat, a future non-discrete caller) can't both get past the
  // guard on the same stale render value.
  const busyRef = useRef(false);
  const beginRequest = useCallback(() => {
    if (busyRef.current) return false;
    busyRef.current = true;
    setBusy(true);
    return true;
  }, []);
  const endRequest = useCallback(() => {
    busyRef.current = false;
    setBusy(false);
  }, []);

  const ask = useCallback(async (question: string) => {
    const q = question.trim();
    const forProject = projectId;
    if (!q || !forProject || !beginRequest()) return;
    setOpen(true);
    setTab('chat');
    append(forProject, { id: nextId(), role: 'user', content: q });
    try {
      const res = await queryApi.rag(forProject, q);
      const data = (res?.data ?? {}) as Record<string, unknown>;
      const content =
        (typeof data.answer === 'string' && data.answer) ||
        (typeof data.response === 'string' && data.response) ||
        (typeof data.context === 'string' && data.context) ||
        'The query returned no answer.';
      append(forProject, { id: nextId(), role: 'assistant', content, grounding: parseGrounding(data) });
    } catch {
      append(forProject, {
        id: nextId(),
        role: 'assistant',
        content: 'Query failed. Check that the backend and an LLM provider are reachable, then try again.',
        failed: true,
      });
    } finally {
      endRequest();
    }
  }, [append, beginRequest, endRequest, projectId]);

  const runTask = useCallback(async (task: { label: string; run: () => Promise<AssistantTaskResult> }) => {
    const forProject = projectId;
    if (!forProject || !beginRequest()) return;
    setOpen(true);
    setTab('chat');
    append(forProject, { id: nextId(), role: 'user', content: task.label });
    try {
      const result = await task.run();
      append(forProject, {
        id: nextId(),
        role: 'assistant',
        content: result.content || 'No output returned.',
        grounding: result.grounding ?? null,
      });
    } catch {
      append(forProject, { id: nextId(), role: 'assistant', content: `${task.label} failed.`, failed: true });
    } finally {
      endRequest();
    }
  }, [append, beginRequest, endRequest, projectId]);

  const clear = useCallback(() => {
    setThread(prev => (prev ? { ...prev, messages: [] } : prev));
  }, []);

  const value = useMemo<AssistantContextValue>(() => ({
    messages,
    busy,
    open,
    setOpen,
    tab,
    setTab,
    projectId,
    ask,
    runTask,
    clear,
    linkedEntities,
    setLinkedEntities,
  }), [messages, busy, open, tab, projectId, ask, runTask, clear, linkedEntities]);

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant() {
  return useContext(AssistantContext);
}
