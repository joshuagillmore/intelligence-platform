import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AssistantPanel from '@/components/AssistantPanel';
import { AssistantProvider } from '@/lib/AssistantContext';

// The panel talks to the backend only through lib/api.
vi.mock('@/lib/api', () => ({
  queryApi: { rag: vi.fn() },
  reportsApi: { save: vi.fn() },
  notebookApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn() },
}));

// Project context is driven per test instead of hitting the real provider.
const ctx = vi.hoisted(() => ({ activeProject: null as { id: string; name: string } | null }));
vi.mock('@/lib/ProjectContext', () => ({
  useProject: () => ({ activeProject: ctx.activeProject, setActiveProject: vi.fn() }),
}));

vi.mock('next/navigation', () => ({ usePathname: () => '/network' }));

vi.mock('@/components/NotificationProvider', () => ({
  useNotifications: () => ({ addNotification: vi.fn(), updateNotification: vi.fn() }),
}));

import { queryApi, notebookApi } from '@/lib/api';
const mockRag = queryApi.rag as unknown as ReturnType<typeof vi.fn>;
const mockNotes = notebookApi.list as unknown as ReturnType<typeof vi.fn>;

/**
 * Node 26 exposes a global `localStorage` that is undefined unless the runtime
 * is started with --localstorage-file, and it shadows the jsdom one. Install a
 * minimal in-memory implementation so thread persistence is actually
 * exercised. (The app itself treats missing/throwing storage as "no thread" —
 * this only makes the persistence path testable.)
 */
function installLocalStorage() {
  const data = new Map<string, string>();
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
      setItem: (k: string, v: string) => { data.set(k, String(v)); },
      removeItem: (k: string) => { data.delete(k); },
      clear: () => data.clear(),
      key: (i: number) => [...data.keys()][i] ?? null,
      get length() { return data.size; },
    },
  });
}

function renderPanel() {
  return render(
    <AssistantProvider>
      <AssistantPanel />
    </AssistantProvider>,
  );
}

const RAG_RESPONSE = {
  data: {
    query: 'who is in rotterdam',
    answer: 'Marcus Kellerman operates out of Rotterdam.',
    model: 'claude-sonnet-4-5',
    tokens_used: 900,
    context: '### Persons (1)\n- Marcus Kellerman\n\n### Relationships (1 unique)\n- Marcus Kellerman --[OPERATES_IN]--> Rotterdam',
    context_nodes: 4,
    context_edges: 2,
    vector_results: 3,
    retrieval_mode: 'hybrid',
  },
};

describe('AssistantPanel', () => {
  beforeEach(() => {
    mockRag.mockReset();
    mockNotes.mockReset();
    mockNotes.mockResolvedValue({ data: [] });
    installLocalStorage();
    ctx.activeProject = { id: 'p1', name: 'Operation Nightfall' };
  });

  it('starts collapsed as a launcher and expands on click', async () => {
    const user = userEvent.setup();
    renderPanel();

    const launcher = screen.getByRole('button', { name: /aegis/i });
    expect(launcher).toHaveAttribute('aria-expanded', 'false');

    await user.click(launcher);
    expect(await screen.findByRole('region', { name: /aegis intelligence assistant/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Graph RAG Chat' })).toHaveAttribute('aria-selected', 'true');
  });

  it('says so gracefully when no project is active, instead of breaking', async () => {
    ctx.activeProject = null;
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /aegis/i }));
    // Stated in both the header (project slot) and the chat body.
    expect(await screen.findByText(/no active project\. select one from the sidebar/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/ask the intelligence assistant/i)).toBeDisabled();
    expect(mockRag).not.toHaveBeenCalled();
  });

  it('sends a question through queryApi.rag and renders the answer', async () => {
    mockRag.mockResolvedValue(RAG_RESPONSE);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /aegis/i }));
    await user.type(screen.getByLabelText(/ask the intelligence assistant/i), 'who is in rotterdam');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(mockRag).toHaveBeenCalledWith('p1', 'who is in rotterdam'));
    expect(await screen.findByText(/marcus kellerman operates out of rotterdam/i)).toBeInTheDocument();
  });

  it('exposes the citations that grounded the answer', async () => {
    mockRag.mockResolvedValue(RAG_RESPONSE);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /aegis/i }));
    await user.type(screen.getByLabelText(/ask the intelligence assistant/i), 'q');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    const sources = await screen.findByRole('button', { name: /^sources ·/i });
    await user.click(sources);
    expect(screen.getByText(/hybrid retrieval · 4 nodes · 2 edges · 3 vector hits/i)).toBeInTheDocument();
    expect(screen.getByText(/Entities in context \(1\)/i)).toBeInTheDocument();
  });

  it('surfaces a readable error instead of a raw JSON dump when the query fails', async () => {
    mockRag.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /aegis/i }));
    await user.type(screen.getByLabelText(/ask the intelligence assistant/i), 'q');
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText(/query failed/i)).toBeInTheDocument();
  });

  it('restores a persisted thread after mount (never in a state initializer)', async () => {
    localStorage.setItem(
      'assistant_thread:p1',
      JSON.stringify([{ id: 'm1', role: 'assistant', content: 'Earlier finding from another view.' }]),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /aegis/i }));
    expect(await screen.findByText(/earlier finding from another view/i)).toBeInTheDocument();
  });

  it('ignores a malformed persisted thread', async () => {
    localStorage.setItem('assistant_thread:p1', '{not json');
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /aegis/i }));
    expect(await screen.findByText(/ask about the knowledge graph/i)).toBeInTheDocument();
  });

  it('switches to the Notebook tab', async () => {
    mockNotes.mockResolvedValue({ data: [{ id: 'n1', name: 'Terminal visit', content: 'Observed twice', note_type: 'observation' }] });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /aegis/i }));
    await user.click(screen.getByRole('tab', { name: 'Notebook' }));

    expect(await screen.findByText('Terminal visit')).toBeInTheDocument();
    await waitFor(() => expect(mockNotes).toHaveBeenCalledWith('p1'));
  });
});
