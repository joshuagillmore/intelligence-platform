import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';

/**
 * The network view end to end over a mocked API: the canvas counts, the entity
 * browser, selecting an entity (relationships and the evidence chain), the
 * relationship filter with undo, and the Statistics tab. Written against the
 * view before it was split into hooks and components, and kept as the guard
 * that the split changed nothing an analyst can see.
 */

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));
vi.mock('@/lib/ProjectContext', () => ({
  useProject: () => ({ activeProject: { id: 'p1', name: 'Nightfall' }, setActiveProject: vi.fn() }),
}));
vi.mock('@/lib/AssistantContext', () => ({ useAssistant: () => ({ setLinkedEntities: vi.fn() }) }));
vi.mock('@/components/NotificationProvider', () => ({
  useNotifications: () => ({ addNotification: vi.fn(), updateNotification: vi.fn() }),
}));
vi.mock('@/components/Sidebar', () => ({ default: () => null }));
vi.mock('@/components/EnrichmentPanel', () => ({ default: () => null }));
vi.mock('@/components/TemporalHistogram', () => ({ default: () => null }));
vi.mock('@/components/TemporalSlider', () => ({ default: () => null }));
// The d3 canvas is covered by its own test; here each node is a button.
vi.mock('@/components/GraphVisualization', () => ({
  default: ({ nodes, onNodeClick }: { nodes: Array<{ id: string; name: string }>; onNodeClick: (n: unknown) => void }) => (
    <div data-testid="canvas">
      {nodes.map((n) => (
        <button key={n.id} onClick={() => onNodeClick(n)}>node:{n.name}</button>
      ))}
    </div>
  ),
}));

const nodes = [
  { id: 'e1', name: 'APT-X', entity_type: 'ThreatActor' },
  { id: 'e2', name: 'Loader', entity_type: 'Malware' },
];
const edges = [{ source_id: 'e1', target_id: 'e2', rel_type: 'USES', confidence: 0.9 }];

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>();
  const ok = (data: unknown, headers: Record<string, string> = {}) => Promise.resolve({ data, headers });
  return {
    ...real,
    graphApi: {
      full: vi.fn(() => ok({ nodes, edges, truncated: false, project_exists: true })),
      // GET /graph/statistics as the backend sends it.
      statistics: vi.fn(() => ok({
        nodes: 2, edges: 1, density: 1, components: 1, truncated: false, project_exists: true,
        entities: [
          { id: 'a', name: 'APT-X', entity_type: 'ThreatActor', degree: 1, in_degree: 0, out_degree: 1,
            betweenness: 0, eigenvector: 0.7, pagerank: 0.5, closeness: 1 },
          { id: 'b', name: 'Loader', entity_type: 'Malware', degree: 1, in_degree: 1, out_degree: 0,
            betweenness: 0, eigenvector: 0.7, pagerank: 0.5, closeness: 1 },
        ],
      })),
      communities: vi.fn(() => ok([])),
      structuralHoles: vi.fn(() => ok([])),
      egoNetwork: vi.fn(),
      influence: vi.fn(),
    },
    snapshotsApi: { list: vi.fn(() => ok({ snapshots: [] })), create: vi.fn(), get: vi.fn(), delete: vi.fn() },
    timelineApi: { get: vi.fn(), histogram: vi.fn(() => ok({ bins: [] })) },
    entitiesApi: {
      search: vi.fn(() => ok(nodes, { 'x-total-count': '2' })),
      get: vi.fn((id: string) => ok({
        entity: nodes.find((n) => n.id === id),
        relationships: id === 'e1'
          ? [{ source_id: 'e1', target_id: 'e2', rel_type: 'USES', confidence: 0.9, source_name: 'APT-X', target_name: 'Loader', source_doc_id: 'd1' }]
          : [],
      })),
      documents: vi.fn(() => ok({
        documents: [{ id: 'd1', name: 'Report A', url: '', source_doc_id: 'd1', mention_count: 3, passages: [{ text: 'APT-X deployed the loader', offset: 4 }] }],
        count: 1,
        total: 1,
      })),
      subgraph: vi.fn(),
      shortestPath: vi.fn(),
    },
    documentsApi: { list: vi.fn(() => ok({ documents: [{ id: 'd1', name: 'Report A', reliability_rating: 'B2' }] })), get: vi.fn(), evidence: vi.fn() },
    watchlistApi: { list: vi.fn(() => ok({ watched_entities: [], count: 0 })), add: vi.fn(), remove: vi.fn() },
  };
});

import NetworkPage from '@/app/network/page';

describe('network page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('draws the graph and counts what it shows', async () => {
    render(<NetworkPage />);
    expect(await screen.findByText('node:APT-X')).toBeInTheDocument();
    expect(screen.getByText('2 nodes, 1 edges')).toBeInTheDocument();
  });

  it('lists entities by type and shows the selected one with its relationships and sources', async () => {
    render(<NetworkPage />);
    fireEvent.click(await screen.findByRole('button', { name: /Threat Actor/ }));
    fireEvent.click(screen.getByRole('button', { name: 'APT-X' }));

    expect(await screen.findByRole('heading', { name: 'APT-X' })).toBeInTheDocument();
    expect(await screen.findByText('Relationships (1)')).toBeInTheDocument();
    expect(screen.getByText('APT-X → Loader')).toBeInTheDocument();

    // The evidence chain: one call for the entity's documents, with the
    // reliability grade joined from the document list.
    expect(await screen.findByText('Report A')).toBeInTheDocument();
    expect(screen.getByText('B2')).toBeInTheDocument();
    expect(screen.getByText('×3')).toBeInTheDocument();
    expect(screen.getByText(/APT-X deployed the loader/)).toBeInTheDocument();

    // A relationship's provenance names its source document.
    fireEvent.click(screen.getByRole('button', { name: 'Show Evidence' }));
    expect(screen.getByRole('button', { name: 'Hide Evidence' })).toBeInTheDocument();
  });

  it('selects from the canvas too', async () => {
    render(<NetworkPage />);
    fireEvent.click(await screen.findByText('node:Loader'));
    expect(await screen.findByRole('heading', { name: 'Loader' })).toBeInTheDocument();
    expect(screen.getByText('Path:')).toBeInTheDocument();
  });

  it('hides a relationship type and undoes it', async () => {
    render(<NetworkPage />);
    await screen.findByText('2 nodes, 1 edges');
    fireEvent.click(screen.getByRole('button', { name: /Rel Filter/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'USES' }));
    // Both nodes were connected only by that edge, so they go with it.
    await waitFor(() => expect(screen.getByText('0 nodes, 0 edges')).toBeInTheDocument());
    expect(screen.queryByTestId('canvas')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(screen.getByText('2 nodes, 1 edges')).toBeInTheDocument());
  });

  it('shows the edge overview and the centrality table on the Statistics tab', async () => {
    render(<NetworkPage />);
    await screen.findByText('2 nodes, 1 edges');
    fireEvent.click(screen.getByRole('button', { name: 'Statistics' }));
    expect(await screen.findByText('Edge Overview')).toBeInTheDocument();
    expect(screen.getByText('Avg confidence: 90%')).toBeInTheDocument();
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Loader')).toBeInTheDocument();
  });
});
