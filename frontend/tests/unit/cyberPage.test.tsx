import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';

/**
 * The cyber view's relation counts over a mocked API. `GET /entities` now sends
 * `relationship_count` on every row (the entity's edges, not the documents
 * that mention it); the IOC table's "Rels" column and the actor list read it,
 * where they used to show "--" for every row. The count is computed, not
 * stored, so it stays out of the properties panel.
 */

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/lib/ProjectContext', () => ({
  useProject: () => ({ activeProject: { id: 'p1', name: 'Nightfall' }, setActiveProject: vi.fn() }),
}));
vi.mock('@/components/NotificationProvider', () => ({
  useNotifications: () => ({ addNotification: vi.fn(), updateNotification: vi.fn() }),
}));
vi.mock('@/components/Sidebar', () => ({ default: () => null }));
vi.mock('@/components/GraphVisualization', () => ({ default: () => null }));
vi.mock('@/components/EnrichmentPanel', () => ({ default: () => null }));
vi.mock('@/components/AttackMatrix', () => ({ default: () => null }));
vi.mock('@/components/AttackAttribution', () => ({ default: () => null }));

const rows: Record<string, Array<Record<string, unknown>>> = {
  IPAddress: [
    { id: 'ip1', name: '203.0.113.7', entity_type: 'IPAddress', relationship_count: 3 },
    { id: 'ip2', name: '198.51.100.1', entity_type: 'IPAddress', relationship_count: 0 },
  ],
  ThreatActor: [{ id: 'ta1', name: 'APT-X', entity_type: 'ThreatActor', relationship_count: 2, motivation: 'espionage' }],
};

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>();
  const ok = (data: unknown, headers: Record<string, string> = {}) => Promise.resolve({ data, headers });
  return {
    ...real,
    entitiesApi: {
      search: vi.fn((_project: string, _query: string | undefined, type: string) => {
        const data = rows[type] ?? [];
        return ok(data, { 'x-total-count': String(data.length) });
      }),
      get: vi.fn((id: string) => ok({ entity: { id }, relationships: [] })),
    },
    graphApi: { full: vi.fn(() => ok({ nodes: [], edges: [], truncated: false, project_exists: true })) },
    assessApi: {},
  };
});

import CyberPage from '@/app/cyber/page';

/** The "Rels" cell of the IOC row naming `indicator`. */
function relsCell(indicator: string): string {
  const row = screen.getByText(indicator).closest('tr') as HTMLElement;
  const header = screen.getByRole('columnheader', { name: 'Rels' });
  const column = Array.from(header.parentElement!.children).indexOf(header);
  return within(row).getAllByRole('cell')[column].textContent ?? '';
}

describe('Cyber view relation counts', () => {
  it('shows each indicator its relationship_count, zero included', async () => {
    render(<CyberPage />);
    await screen.findByText('203.0.113.7');
    expect(relsCell('203.0.113.7')).toBe('3');
    expect(relsCell('198.51.100.1')).toBe('0');
  });

  it('labels each threat actor with its connections and keeps the count out of its properties', async () => {
    render(<CyberPage />);
    fireEvent.click(await screen.findByText('Threat Actors'));
    await waitFor(() => expect(screen.getByText('2 connections')).toBeInTheDocument());

    // The actor's panel lists the row's own fields: stored ones only.
    fireEvent.click(screen.getByText('APT-X'));
    await screen.findByText('Properties / Assessment');
    expect(screen.getByText('motivation:')).toBeInTheDocument();
    expect(screen.queryByText('relationship_count:')).not.toBeInTheDocument();
  });
});
