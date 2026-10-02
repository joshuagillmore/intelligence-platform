import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { AxiosError } from 'axios';
import { ProjectProvider, useProject } from '@/lib/ProjectContext';
import SelectProjectPrompt from '@/components/SelectProjectPrompt';

/**
 * `ProjectProvider` re-checks the project it restores from storage and drops
 * it when the backend refuses it with 403, so no view opens on a project the
 * analyst can no longer read; `SelectProjectPrompt` then says why.
 */

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>();
  return { ...real, projectsApi: { get: vi.fn() } };
});

import { projectsApi } from '@/lib/api';
const mockGet = projectsApi.get as unknown as ReturnType<typeof vi.fn>;

function refused(status: number): AxiosError {
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, null, {
    status,
    statusText: String(status),
    data: status === 403 ? { detail: 'No access to this project' } : {},
    headers: {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config: {} as any,
  });
}

const stored = { id: 'p1', name: 'Nightfall', description: '', priority: 'high', status: 'active', classification_level: 'U' };

let api: ReturnType<typeof useProject>;
function Probe() {
  api = useProject();
  return (
    <div>
      <span data-testid="active">{api.activeProject?.name ?? 'none'}</span>
      {!api.activeProject && <SelectProjectPrompt action="map" />}
    </div>
  );
}

function renderProvider() {
  return render(
    <ProjectProvider>
      <Probe />
    </ProjectProvider>,
  );
}

/** Node 26's own global `localStorage` is undefined without
 *  --localstorage-file and shadows jsdom's; give the provider a real one (the
 *  same shim as AssistantPanel.test). */
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

describe('ProjectProvider access', () => {
  beforeEach(() => {
    mockGet.mockReset();
    installLocalStorage();
  });

  it('drops a restored project that answers 403 and says why', async () => {
    localStorage.setItem('activeProject', JSON.stringify(stored));
    mockGet.mockRejectedValue(refused(403));
    renderProvider();

    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('none'));
    expect(mockGet).toHaveBeenCalledWith('p1');
    // Storage is cleared by a separate effect after the state update; on a
    // slow runner it had not flushed yet when the rendered state had.
    await waitFor(() => expect(localStorage.getItem('activeProject')).toBeNull());
    expect(api.deniedProject?.id).toBe('p1');
    expect(screen.getByRole('heading', { name: "You don't have access to this project" })).toBeInTheDocument();
    expect(screen.getByText(/Nightfall/)).toBeInTheDocument();
  });

  it('keeps a restored project on any other failure', async () => {
    localStorage.setItem('activeProject', JSON.stringify(stored));
    mockGet.mockRejectedValue(refused(500));
    renderProvider();

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    // Let the rejection settle before asserting nothing changed.
    await act(async () => {});
    expect(screen.getByTestId('active')).toHaveTextContent('Nightfall');
    expect(api.deniedProject).toBeNull();
  });

  it('keeps a restored project the backend still serves', async () => {
    localStorage.setItem('activeProject', JSON.stringify(stored));
    mockGet.mockResolvedValue({ data: stored });
    renderProvider();

    await waitFor(() => expect(mockGet).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.getByTestId('active')).toHaveTextContent('Nightfall');
  });

  it('asks nothing when no project is stored', async () => {
    renderProvider();
    await act(async () => {});
    expect(mockGet).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'No project selected' })).toBeInTheDocument();
  });

  it('drops only the project it was asked to', async () => {
    localStorage.setItem('activeProject', JSON.stringify(stored));
    mockGet.mockResolvedValue({ data: stored });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('Nightfall'));

    act(() => api.dropProject('another'));
    expect(screen.getByTestId('active')).toHaveTextContent('Nightfall');

    act(() => api.dropProject('p1'));
    expect(screen.getByTestId('active')).toHaveTextContent('none');
    expect(api.deniedProject?.name).toBe('Nightfall');
  });

  it('forgets the refusal once another project is chosen', async () => {
    localStorage.setItem('activeProject', JSON.stringify(stored));
    mockGet.mockRejectedValue(refused(403));
    renderProvider();
    await waitFor(() => expect(api.deniedProject).not.toBeNull());

    act(() => api.setActiveProject({ ...stored, id: 'p2', name: 'Daybreak' }));
    expect(screen.getByTestId('active')).toHaveTextContent('Daybreak');
    expect(api.deniedProject).toBeNull();
    expect(JSON.parse(localStorage.getItem('activeProject') ?? '{}').id).toBe('p2');
  });
});
