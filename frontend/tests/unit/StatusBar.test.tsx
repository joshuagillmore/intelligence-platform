import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import StatusBar from '@/components/StatusBar';

// Mock the axios API client so the component never makes a real HTTP request.
// StatusBar only uses `healthApi.check`.
vi.mock('@/lib/api', () => ({
  healthApi: { check: vi.fn() },
}));

// Mock the project context so the test drives `activeProject` without the real
// provider (which reaches for localStorage). `vi.hoisted` gives the hoisted
// mock factory a mutable holder we can set per test.
const ctx = vi.hoisted(() => ({
  activeProject: null as { name: string } | null,
}));
vi.mock('@/lib/ProjectContext', () => ({
  useProject: () => ({ activeProject: ctx.activeProject, setActiveProject: vi.fn() }),
}));

// Typed handles to the mocked function for per-test behaviour.
import { healthApi } from '@/lib/api';
const mockCheck = healthApi.check as unknown as ReturnType<typeof vi.fn>;

describe('StatusBar', () => {
  beforeEach(() => {
    mockCheck.mockReset();
    ctx.activeProject = null;
  });

  it('runs a health check on mount (via the mocked api, not real HTTP)', async () => {
    mockCheck.mockResolvedValue({ data: { status: 'ok', neo4j_connected: true, ollama_connected: true } });
    render(<StatusBar />);
    await waitFor(() => expect(mockCheck).toHaveBeenCalled());
  });

  it('shows "Systems Nominal" while the backend is reachable', async () => {
    mockCheck.mockResolvedValue({ data: { status: 'ok', neo4j_connected: true, ollama_connected: true } });
    render(<StatusBar />);
    expect(await screen.findByText('Systems Nominal')).toBeInTheDocument();
  });

  // /health answers 200 with status "degraded" when Neo4j is down, so a 2xx
  // alone is not "nominal": the body's status field is what counts.
  it('does not claim "Systems Nominal" when /health reports degraded', async () => {
    mockCheck.mockResolvedValue({ data: { status: 'degraded', neo4j_connected: false, ollama_connected: true } });
    render(<StatusBar />);
    expect(await screen.findByText(/Degraded/)).toBeInTheDocument();
    expect(screen.queryByText('Systems Nominal')).toBeNull();
  });

  it('names the graph database when it is the part that is down', async () => {
    mockCheck.mockResolvedValue({ data: { status: 'degraded', neo4j_connected: false, ollama_connected: true } });
    render(<StatusBar />);
    expect(await screen.findByText(/Neo4j/)).toBeInTheDocument();
  });

  it('does not claim "Systems Nominal" for a 200 with no status field', async () => {
    mockCheck.mockResolvedValue({ data: {} });
    render(<StatusBar />);
    await waitFor(() => expect(mockCheck).toHaveBeenCalled());
    expect(await screen.findByText(/Degraded/)).toBeInTheDocument();
    expect(screen.queryByText('Systems Nominal')).toBeNull();
  });

  it('shows "Disconnected" when the health check fails', async () => {
    mockCheck.mockRejectedValue(new Error('backend down'));
    render(<StatusBar />);
    expect(await screen.findByText('Disconnected')).toBeInTheDocument();
  });

  it('renders the active project name when one is selected', async () => {
    mockCheck.mockResolvedValue({ data: { status: 'ok', neo4j_connected: true, ollama_connected: true } });
    ctx.activeProject = { name: 'Operation Nightfall' };
    render(<StatusBar />);
    expect(await screen.findByText('Operation Nightfall')).toBeInTheDocument();
  });
});
