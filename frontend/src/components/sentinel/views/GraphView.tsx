'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';
import { graphApi, queryApi, watchlistApi } from '@/lib/api';
import {
  Btn,
  Tag,
  Icon,
  ENTITY_META,
  EntityChip,
  CiteChip,
} from '@/components/sentinel';
import { useNotifications } from '@/components/NotificationProvider';

interface GraphNode {
  id: string;
  name: string;
  entity_type?: string;
  type?: string;
  confidence?: number;
  watched?: boolean;
  flag?: string;
  description?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  a?: string;
  b?: string;
  label?: string;
  type?: string;
  weight?: number;
  confidence?: number;
}

type RightTab = 'inspector' | 'stats' | 'analysis';

export function GraphView() {
  const router = useRouter();
  const { activeProject } = useProject();

  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [askQ, setAskQ] = useState('');
  const [askResult, setAskResult] = useState<{ answer?: string; confidence?: number; entities?: string[]; sources?: Array<{ id?: string; title?: string; excerpt?: string }> } | null>(null);
  const [asking, setAsking] = useState(false);
  const [rightTab, setRightTab] = useState<RightTab>('inspector');

  const { addNotification, updateNotification } = useNotifications();

  const loadGraph = useCallback(
    (announce = false) => {
      if (!activeProject) return;
      setLoading(true);
      const toastId = announce
        ? addNotification({
            title: 'Refreshing graph',
            message: `Re-fetching subgraph for ${activeProject.name}…`,
            type: 'processing',
          })
        : null;
      graphApi
        .full(activeProject.id)
        .then((res) => {
          const data = res.data as { nodes?: GraphNode[]; edges?: GraphEdge[]; relationships?: GraphEdge[] };
          const ns = data.nodes || [];
          const es = data.edges || data.relationships || [];
          setNodes(ns);
          setEdges(es);
          if (ns.length && !selected) setSelected(ns[0].id);
          if (toastId) {
            updateNotification(toastId, {
              title: 'Graph refreshed',
              message: `${ns.length} entities · ${es.length} edges`,
              type: 'success',
            });
          }
        })
        .catch(() => {
          setNodes([]);
          setEdges([]);
          if (toastId) {
            updateNotification(toastId, {
              title: 'Refresh failed',
              message: 'Could not reach the graph service. Try again in a moment.',
              type: 'error',
            });
          }
        })
        .finally(() => setLoading(false));
    },
    [activeProject, addNotification, updateNotification, selected],
  );

  useEffect(() => {
    loadGraph();
  }, [activeProject]); // eslint-disable-line react-hooks/exhaustive-deps

  const openFilters = () =>
    addNotification({
      title: 'Filters',
      message: 'Type · degree · community · watched-only filters coming in Analysis tab.',
      type: 'info',
    });

  const positions = useMemo(() => layoutCircular(nodes), [nodes]);
  const selectedNode = nodes.find((n) => n.id === selected);

  const submitAsk = async () => {
    if (!activeProject || !askQ.trim()) return;
    setAsking(true);
    setAskResult(null);
    try {
      const res = await queryApi.rag(activeProject.id, askQ);
      setAskResult(res.data as typeof askResult);
    } catch (e) {
      setAskResult({ answer: `Query failed: ${(e as Error).message}` });
    } finally {
      setAsking(false);
    }
  };

  if (!activeProject) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: 'var(--fg-3)' }}>
        <Icon name="graph" size={36} />
        <h2 style={{ margin: '12px 0 6px', fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 500, color: 'var(--ink)' }}>
          No active project
        </h2>
        <p style={{ fontSize: 13 }}>The graph is project-scoped. Select one from the Hub.</p>
        <Btn variant="signal" icon="hub" onClick={() => router.push('/')}>
          Open Hub
        </Btn>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '320px 1fr 340px',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <AskPanel
        question={askQ}
        setQuestion={setAskQ}
        asking={asking}
        result={askResult}
        onAsk={submitAsk}
        nodes={nodes}
        onPickEntity={(id) => setSelected(id)}
      />

      <main
        style={{
          position: 'relative',
          overflow: 'hidden',
          background: 'var(--paper)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <GraphToolbar
          nodeCount={nodes.length}
          edgeCount={edges.length}
          loading={loading}
          onRefresh={() => loadGraph(true)}
          onFilters={openFilters}
        />
        <div style={{ flex: 1, position: 'relative' }}>
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            positions={positions}
            selected={selected}
            onSelect={setSelected}
          />
          <GraphLegend />
        </div>
      </main>

      <aside
        style={{
          background: 'var(--paper-2)',
          borderLeft: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <RightTabs active={rightTab} onChange={setRightTab} />
        <div style={{ flex: 1, overflow: 'auto' }}>
          {rightTab === 'inspector' && (
            <EntityInspector
              entity={selectedNode}
              projectId={activeProject.id}
            />
          )}
          {rightTab === 'stats' && <GraphStatsTab projectId={activeProject.id} />}
          {rightTab === 'analysis' && (
            <GraphAnalysisTab
              projectId={activeProject.id}
              selectedNode={selectedNode}
            />
          )}
        </div>
      </aside>
    </div>
  );
}

// ============================================================================
// Layout
// ============================================================================

function layoutCircular(nodes: GraphNode[]): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  const cx = 500;
  const cy = 320;
  const r = Math.min(220, 60 + nodes.length * 8);
  nodes.forEach((n, i) => {
    const a = (i / Math.max(1, nodes.length)) * Math.PI * 2 - Math.PI / 2;
    positions[n.id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  });
  return positions;
}

// ============================================================================
// Ask panel
// ============================================================================

function AskPanel({
  question,
  setQuestion,
  asking,
  result,
  onAsk,
  nodes,
  onPickEntity,
}: {
  question: string;
  setQuestion: (q: string) => void;
  asking: boolean;
  result: { answer?: string; confidence?: number; entities?: string[]; sources?: Array<{ id?: string; title?: string; excerpt?: string }> } | null;
  onAsk: () => void;
  nodes: GraphNode[];
  onPickEntity: (id: string) => void;
}) {
  return (
    <aside
      style={{
        background: 'var(--paper-2)',
        borderRight: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '20px 22px 14px', borderBottom: '1px solid var(--line)' }}>
        <div
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 9.5,
            letterSpacing: '0.2em',
            color: 'var(--fg-3)',
            fontWeight: 600,
            marginBottom: 8,
          }}
        >
          ASK · GRAPH RAG
        </div>
        <div style={{ position: 'relative' }}>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                onAsk();
              }
            }}
            rows={3}
            placeholder="What do you want to know about this corpus? ⌘↵ to send"
            style={{
              width: '100%',
              resize: 'none',
              background: 'var(--paper)',
              border: '1px solid var(--line)',
              borderRadius: 3,
              padding: '10px 12px 36px',
              fontFamily: 'var(--serif)',
              fontSize: 14,
              lineHeight: 1.4,
              color: 'var(--ink)',
              outline: 'none',
            }}
          />
          <div
            style={{
              position: 'absolute',
              left: 12,
              bottom: 8,
              right: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Tag>GRAPH-RAG</Tag>
            <Tag>{nodes.length} ENTITIES</Tag>
            <span style={{ flex: 1 }} />
            <button
              onClick={onAsk}
              disabled={asking || !question.trim()}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '3px 8px',
                borderRadius: 2,
                background: 'var(--ink)',
                color: 'var(--paper)',
                fontSize: 11,
                fontWeight: 500,
                border: 'none',
                cursor: asking ? 'wait' : 'pointer',
                opacity: asking || !question.trim() ? 0.5 : 1,
              }}
            >
              {asking ? 'Asking…' : 'Ask'} <Icon name="arrow-right" size={11} />
            </button>
          </div>
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '18px 22px' }}>
        {!result && !asking && (
          <div
            style={{
              padding: '24px 16px',
              textAlign: 'center',
              fontSize: 12.5,
              color: 'var(--fg-3)',
              border: '1px dashed var(--line)',
              borderRadius: 3,
            }}
          >
            Ask a question to draw an answer from the graph. The agent will cite entities and
            documents in its response.
          </div>
        )}
        {asking && (
          <div
            style={{
              padding: '24px 16px',
              textAlign: 'center',
              fontSize: 12.5,
              color: 'var(--fg-3)',
            }}
          >
            <span style={{ animation: 'caret-blink 1s infinite' }}>▋</span> Reasoning over the graph…
          </div>
        )}
        {result && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.12em' }}>
              <span
                style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--live)', animation: 'pulse-dot 1.6s ease-in-out infinite',
                }}
              />
              GROUNDED IN EVIDENCE
              {result.entities && result.entities.length > 0 && (
                <span> · {result.entities.length} {result.entities.length === 1 ? 'ENTITY' : 'ENTITIES'}</span>
              )}
            </div>
            <p style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 14, lineHeight: 1.55, color: 'var(--ink)' }}>
              {result.answer || '—'}
            </p>
            {result.entities && result.entities.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 9.5,
                    letterSpacing: '0.2em',
                    color: 'var(--fg-3)',
                    fontWeight: 600,
                    marginBottom: 6,
                  }}
                >
                  CITED ENTITIES
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {result.entities.map((eid) => {
                    const n = nodes.find((x) => x.id === eid);
                    if (!n) return null;
                    return (
                      <EntityChip
                        key={eid}
                        entity={{
                          name: n.name,
                          type: (n.entity_type || n.type || 'PERSON').toUpperCase(),
                          watched: n.watched,
                        }}
                        onClick={() => onPickEntity(eid)}
                      />
                    );
                  })}
                </div>
              </div>
            )}
            {result.sources && result.sources.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 9.5,
                    letterSpacing: '0.2em',
                    color: 'var(--fg-3)',
                    fontWeight: 600,
                    marginBottom: 6,
                  }}
                >
                  SOURCES · {result.sources.length}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {result.sources.map((s, i) => (
                    <div
                      key={i}
                      style={{
                        padding: '8px 10px',
                        background: 'var(--paper)',
                        border: '1px solid var(--line-soft)',
                        borderRadius: 2,
                      }}
                    >
                      <CiteChip kind="doc">{s.title || s.id || `doc-${i + 1}`}</CiteChip>
                      {s.excerpt && (
                        <p style={{ margin: '6px 0 0', fontSize: 11.5, color: 'var(--fg-2)', lineHeight: 1.4 }}>
                          {s.excerpt}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

// ============================================================================
// Center: graph canvas
// ============================================================================

function GraphToolbar({
  nodeCount,
  edgeCount,
  loading,
  onRefresh,
  onFilters,
}: {
  nodeCount: number;
  edgeCount: number;
  loading: boolean;
  onRefresh: () => void;
  onFilters: () => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 18px',
        borderBottom: '1px solid var(--line)',
        background: 'var(--paper)',
      }}
    >
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.14em', color: 'var(--fg-3)' }}>
        {loading ? 'LOADING GRAPH…' : `${nodeCount} ENTITIES · ${edgeCount} EDGES`}
      </span>
      <span style={{ flex: 1 }} />
      <Btn variant="outline" icon="filter" size="sm" onClick={onFilters}>
        Filters
      </Btn>
      <Btn variant="outline" icon="refresh" size="sm" onClick={() => { if (!loading) onRefresh(); }}>
        Refresh
      </Btn>
    </div>
  );
}

function GraphCanvas({
  nodes,
  edges,
  positions,
  selected,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  positions: Record<string, { x: number; y: number }>;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  if (nodes.length === 0) {
    return (
      <div
        style={{
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--fg-3)',
          fontSize: 13,
        }}
      >
        No graph data yet — run an acquisition or upload documents to populate the graph.
      </div>
    );
  }
  return (
    <svg viewBox="0 0 1000 640" style={{ width: '100%', height: '100%', background: 'var(--paper)' }}>
      {/* crosshair grid */}
      <g stroke="var(--line-soft)" strokeWidth={0.5}>
        {Array.from({ length: 20 }).map((_, i) => (
          <line key={`h${i}`} x1={0} x2={1000} y1={i * 32} y2={i * 32} />
        ))}
        {Array.from({ length: 32 }).map((_, i) => (
          <line key={`v${i}`} x1={i * 32} x2={i * 32} y1={0} y2={640} />
        ))}
      </g>

      {edges.map((e, i) => {
        const a = positions[e.source || e.a || ''];
        const b = positions[e.target || e.b || ''];
        if (!a || !b) return null;
        return (
          <g key={i}>
            <line
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--fg-4)"
              strokeOpacity={0.5}
              strokeWidth={1 + (e.weight || e.confidence || 0.5) * 1.5}
            />
          </g>
        );
      })}

      {nodes.map((n) => {
        const pos = positions[n.id];
        if (!pos) return null;
        const type = (n.entity_type || n.type || 'PERSON').toUpperCase();
        const meta = ENTITY_META[type] || { icon: 'entity', tint: 'var(--fg-3)' };
        const isSelected = selected === n.id;
        return (
          <g
            key={n.id}
            onClick={() => onSelect(n.id)}
            style={{ cursor: 'pointer' }}
          >
            {isSelected && (
              <circle
                cx={pos.x}
                cy={pos.y}
                r={20}
                fill="var(--signal-soft)"
                stroke="var(--signal)"
                strokeWidth={1.5}
              />
            )}
            <circle
              cx={pos.x}
              cy={pos.y}
              r={11}
              fill={meta.tint}
              stroke="var(--paper)"
              strokeWidth={2}
            />
            {n.watched && (
              <text
                x={pos.x + 12}
                y={pos.y - 8}
                fill="var(--signal)"
                fontSize={11}
                fontWeight={700}
              >
                ★
              </text>
            )}
            <text
              x={pos.x}
              y={pos.y + 26}
              textAnchor="middle"
              fill="var(--ink)"
              fontSize={11}
              fontFamily="var(--sans)"
              fontWeight={isSelected ? 600 : 500}
            >
              {(() => { const nm = n.name || n.id || ''; return nm.length > 22 ? nm.slice(0, 20) + '…' : nm; })()}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function GraphLegend() {
  const items: Array<{ type: string; label: string }> = [
    { type: 'VESSEL',   label: 'Vessel' },
    { type: 'ORG',      label: 'Organization' },
    { type: 'PERSON',   label: 'Person' },
    { type: 'LOCATION', label: 'Location' },
    { type: 'INDICATOR', label: 'Indicator' },
  ];
  return (
    <div
      style={{
        position: 'absolute',
        left: 18,
        bottom: 18,
        padding: '10px 12px',
        background: 'var(--paper)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div
        style={{
          fontFamily: 'var(--mono)',
          fontSize: 9,
          letterSpacing: '0.18em',
          color: 'var(--fg-3)',
          fontWeight: 600,
        }}
      >
        ENTITY TYPES
      </div>
      {items.map((i) => {
        const meta = ENTITY_META[i.type];
        return (
          <div key={i.type} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: meta.tint }} />
            <span style={{ fontSize: 11, color: 'var(--fg-2)' }}>{i.label}</span>
          </div>
        );
      })}
    </div>
  );
}

// ============================================================================
// Right tabs
// ============================================================================

function RightTabs({ active, onChange }: { active: RightTab; onChange: (t: RightTab) => void }) {
  const tabs: { id: RightTab; label: string; icon: string }[] = [
    { id: 'inspector', label: 'Inspector',  icon: 'entity' },
    { id: 'stats',     label: 'Statistics', icon: 'grid' },
    { id: 'analysis',  label: 'Analysis',   icon: 'sparkle' },
  ];
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', background: 'var(--paper)' }}>
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          style={{
            flex: 1,
            padding: '10px 6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 5,
            background: 'transparent',
            border: 'none',
            borderBottom: `2px solid ${active === t.id ? 'var(--ink)' : 'transparent'}`,
            color: active === t.id ? 'var(--ink)' : 'var(--fg-3)',
            fontSize: 11.5,
            fontWeight: active === t.id ? 600 : 500,
            cursor: 'pointer',
            marginBottom: -1,
          }}
        >
          <Icon name={t.icon} size={12} />
          {t.label}
        </button>
      ))}
    </div>
  );
}

function EntityInspector({
  entity,
  projectId,
}: {
  entity?: GraphNode;
  projectId: string;
}) {
  const [busy, setBusy] = useState(false);
  const { addNotification } = useNotifications();
  const openSubgraph = () => {
    if (!entity) return;
    addNotification({
      title: `Subgraph · ${entity.name}`,
      message: 'Pivoting view to 1-hop neighbourhood (open Analysis tab → Ego for full controls).',
      type: 'info',
    });
  };
  if (!entity) {
    return (
      <div style={{ padding: 24, fontSize: 13, color: 'var(--fg-3)' }}>
        Click any entity in the graph to inspect.
      </div>
    );
  }
  const type = (entity.entity_type || entity.type || 'PERSON').toUpperCase();
  const meta = ENTITY_META[type] || { icon: 'entity', tint: 'var(--fg-3)' };

  const toggleWatch = async () => {
    setBusy(true);
    try {
      if (entity.watched) {
        await watchlistApi.remove(projectId, entity.id);
      } else {
        await watchlistApi.add(projectId, entity.id);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ padding: '18px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span
          style={{
            width: 36,
            height: 36,
            borderRadius: 4,
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
              fontSize: 14,
              fontWeight: 600,
              color: 'var(--ink)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {entity.name}
          </div>
          <div
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10,
              color: 'var(--fg-3)',
              letterSpacing: '0.08em',
              marginTop: 2,
            }}
          >
            {type}
            {entity.flag ? ` · ${entity.flag.toUpperCase()}` : ''}
          </div>
        </div>
      </div>

      {entity.description && (
        <p
          style={{
            margin: '14px 0 0',
            fontFamily: 'var(--serif)',
            fontSize: 13,
            lineHeight: 1.5,
            color: 'var(--fg-2)',
          }}
        >
          {entity.description}
        </p>
      )}

      <div style={{ display: 'flex', gap: 6, marginTop: 14 }}>
        <Btn
          variant={entity.watched ? 'signal' : 'outline'}
          icon={entity.watched ? 'star' : 'star-o'}
          onClick={toggleWatch}
          size="sm"
        >
          {busy ? '…' : entity.watched ? 'Watching' : 'Watch'}
        </Btn>
        <Btn variant="outline" icon="link" size="sm" onClick={openSubgraph}>
          Subgraph
        </Btn>
      </div>
    </div>
  );
}

function GraphStatsTab({ projectId }: { projectId: string }) {
  const [stats, setStats] = useState<{ nodes?: number; edges?: number; communities?: number } | null>(null);
  const [centrality, setCentrality] = useState<Array<{ id: string; name?: string; degree?: number; betweenness?: number; pagerank?: number }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      graphApi.statistics(projectId).catch(() => ({ data: null })),
      graphApi.centrality(projectId).catch(() => ({ data: [] })),
    ])
      .then(([s, c]) => {
        setStats(s.data as typeof stats);
        const cd = c.data as typeof centrality;
        setCentrality(Array.isArray(cd) ? cd : []);
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div style={{ padding: 24, fontSize: 13, color: 'var(--fg-3)' }}>Loading…</div>;

  return (
    <div style={{ padding: '18px 20px' }}>
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
          <StatBlock label="Nodes" value={stats.nodes ?? 0} />
          <StatBlock label="Edges" value={stats.edges ?? 0} />
          <StatBlock label="Communities" value={stats.communities ?? 0} />
        </div>
      )}

      <div
        style={{
          fontFamily: 'var(--mono)',
          fontSize: 9.5,
          letterSpacing: '0.2em',
          color: 'var(--fg-3)',
          fontWeight: 600,
          marginBottom: 8,
        }}
      >
        TOP CENTRALITY
      </div>
      {centrality.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>No centrality data.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {centrality.slice(0, 12).map((c) => (
            <div
              key={c.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                alignItems: 'center',
                padding: '6px 8px',
                background: 'var(--paper)',
                border: '1px solid var(--line-soft)',
                borderRadius: 2,
              }}
            >
              <span style={{ fontSize: 12, color: 'var(--ink)' }}>{c.name || c.id}</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>
                {(c.pagerank ?? c.betweenness ?? c.degree ?? 0).toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

type AnalysisMode = 'communities' | 'path' | 'ego' | 'influence' | 'holes';

function GraphAnalysisTab({
  projectId,
  selectedNode,
}: {
  projectId: string;
  selectedNode?: GraphNode;
}) {
  const [mode, setMode] = useState<AnalysisMode>('communities');
  const [communities, setCommunities] = useState<Array<{ id: string | number; size?: number; entities?: string[] }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    graphApi
      .communities(projectId)
      .then((res) => {
        const data = res.data as Array<{ id: string | number; size?: number; entities?: string[] }> | { communities?: typeof communities };
        const list = Array.isArray(data) ? data : data.communities || [];
        setCommunities(list);
      })
      .catch(() => setCommunities([]))
      .finally(() => setLoading(false));
  }, [projectId]);

  const modes: { id: AnalysisMode; label: string }[] = [
    { id: 'communities', label: 'Communities' },
    { id: 'path',        label: 'Path' },
    { id: 'ego',         label: 'Ego' },
    { id: 'influence',   label: 'Influence' },
    { id: 'holes',       label: 'Holes' },
  ];

  return (
    <div style={{ padding: '14px 16px' }}>
      {/* Sub-mode chips */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 14, flexWrap: 'wrap' }}>
        {modes.map((m) => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            style={{
              padding: '4px 9px', borderRadius: 2,
              fontFamily: 'var(--mono)', fontSize: 10.5, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
              cursor: 'pointer',
              background: mode === m.id ? 'var(--ink)' : 'transparent',
              color: mode === m.id ? 'var(--paper)' : 'var(--fg-2)',
              border: '1px solid ' + (mode === m.id ? 'var(--ink)' : 'var(--line)'),
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === 'communities' && (
        <CommunitiesMode communities={communities} loading={loading} />
      )}
      {mode === 'path'      && <PathMode />}
      {mode === 'ego'       && <EgoMode projectId={projectId} selectedNode={selectedNode} />}
      {mode === 'influence' && <InfluenceMode projectId={projectId} selectedNode={selectedNode} />}
      {mode === 'holes'     && <HolesMode projectId={projectId} />}
    </div>
  );
}

function CommunitiesMode({ communities, loading }: { communities: Array<{ id: string | number; size?: number; entities?: string[] }>; loading: boolean }) {
  if (loading) return <div style={{ padding: 8, fontSize: 13, color: 'var(--fg-3)' }}>Loading…</div>;
  return (
    <>
      <AnalysisLabel>COMMUNITIES · {communities.length}</AnalysisLabel>
      {communities.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>No communities detected yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {communities.slice(0, 15).map((c) => (
            <div
              key={String(c.id)}
              style={{
                padding: '8px 10px', background: 'var(--paper)',
                border: '1px solid var(--line-soft)', borderRadius: 2,
                display: 'flex', justifyContent: 'space-between',
              }}
            >
              <span style={{ fontSize: 12, color: 'var(--ink)' }}>Community {c.id}</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>
                {c.size ?? c.entities?.length ?? 0} entities
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function PathMode() {
  return (
    <>
      <AnalysisLabel>SHORTEST PATH</AnalysisLabel>
      <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--fg-3)' }}>
        Pick a source and destination entity to compute the shortest path.
      </p>
      <div style={{
        padding: 14, background: 'var(--paper)', border: '1px dashed var(--line)',
        borderRadius: 3, fontSize: 12, color: 'var(--fg-3)', textAlign: 'center',
      }}>
        Shortest-path API not yet available. Once the backend exposes <code style={{ fontFamily: 'var(--mono)' }}>graphApi.shortestPath</code>, this view will pivot to the from/to picker and the resolved hop list.
      </div>
    </>
  );
}

interface EgoNode { id: string; name?: string; entity_type?: string; hop_distance?: number; local_pagerank?: number; local_betweenness?: number }
interface EgoEdge { source?: string; target?: string; type?: string; relationship_type?: string }

function EgoMode({ projectId, selectedNode }: { projectId: string; selectedNode?: GraphNode }) {
  const [nodes, setNodes] = useState<EgoNode[]>([]);
  const [edges, setEdges] = useState<EgoEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedNode) { setNodes([]); setEdges([]); return; }
    setLoading(true);
    setErr(null);
    graphApi
      .egoNetwork(selectedNode.id, projectId, 1)
      .then((res) => {
        const data = res.data as { nodes?: EgoNode[]; edges?: EgoEdge[] };
        setNodes(Array.isArray(data?.nodes) ? data.nodes : []);
        setEdges(Array.isArray(data?.edges) ? data.edges : []);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [projectId, selectedNode]);

  if (!selectedNode) {
    return <EmptyAnalysis label="EGO NETWORK · 1-HOP" body="Select an entity in the graph to view its 1-hop neighborhood." />;
  }
  const neighbors = nodes.filter((n) => n.id !== selectedNode.id);
  return (
    <>
      <AnalysisLabel>EGO NETWORK · 1-HOP</AnalysisLabel>
      <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--fg-3)' }}>
        Local neighborhood of <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{selectedNode.name || selectedNode.id}</span> · degree {neighbors.length} · {edges.length} edges
      </p>
      {loading ? <LoadingLine /> : err ? <ErrorLine msg={err} /> : neighbors.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--fg-3)', fontStyle: 'italic' }}>No neighbors at 1 hop.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {neighbors.slice(0, 20).map((n) => {
            const edge = edges.find((e) => e.source === selectedNode.id && e.target === n.id) || edges.find((e) => e.target === selectedNode.id && e.source === n.id);
            const rel = edge?.relationship_type || edge?.type || '—';
            return (
              <div key={n.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8, padding: '8px 10px', background: 'var(--paper)', border: '1px solid var(--line-soft)', borderRadius: 2, alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--ink)' }}>{n.name || n.id}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--fg-3)', letterSpacing: '0.08em' }}>{String(rel).toUpperCase()}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink)' }}>{(n.local_pagerank ?? 0).toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

interface InfluenceStep { step: number; activated?: string[]; new_activations?: string[]; count?: number }

function InfluenceMode({ projectId, selectedNode }: { projectId: string; selectedNode?: GraphNode }) {
  const [steps, setSteps] = useState<InfluenceStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedNode) { setSteps([]); return; }
    setLoading(true);
    setErr(null);
    graphApi
      .influence(projectId, [selectedNode.id], 5, 0.35)
      .then((res) => {
        const raw = res.data as { steps?: InfluenceStep[]; cascade?: InfluenceStep[] } | InfluenceStep[];
        const list = Array.isArray(raw) ? raw : (raw?.steps ?? raw?.cascade ?? []);
        setSteps(Array.isArray(list) ? list : []);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [projectId, selectedNode]);

  if (!selectedNode) {
    return <EmptyAnalysis label="INFLUENCE PROPAGATION" body="Select an entity to seed a linear-threshold cascade." />;
  }
  return (
    <>
      <AnalysisLabel>INFLUENCE PROPAGATION · LINEAR THRESHOLD</AnalysisLabel>
      <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--fg-3)' }}>
        Cascade from <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{selectedNode.name || selectedNode.id}</span> · threshold 0.35 · max steps 5
      </p>
      {loading ? <LoadingLine /> : err ? <ErrorLine msg={err} /> : steps.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--fg-3)', fontStyle: 'italic' }}>Cascade halted at step 0 — no neighbors above threshold.</p>
      ) : (
        <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {steps.map((s, i) => {
            const activated = s.new_activations || s.activated || [];
            const count = s.count ?? activated.length;
            return (
              <li key={i} style={{ padding: '8px 10px', background: 'var(--paper)', border: '1px solid var(--line-soft)', borderRadius: 2 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.1em', color: 'var(--fg-3)' }}>
                    STEP {s.step ?? i}
                  </span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink)' }}>
                    +{count} activated
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--ink)' }}>
                  {Array.isArray(activated) && activated.length > 0 ? activated.slice(0, 4).join(', ') + (activated.length > 4 ? `, +${activated.length - 4} more` : '') : '—'}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </>
  );
}

interface Broker { id?: string; name?: string; entity?: string; constraint?: number; effective_size?: number; eff_size?: number; degree?: number; bridges?: string }

function HolesMode({ projectId }: { projectId: string }) {
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    graphApi
      .structuralHoles(projectId, 10)
      .then((res) => {
        const raw = res.data as Broker[] | { brokers?: Broker[]; results?: Broker[] };
        const list = Array.isArray(raw) ? raw : (raw?.brokers ?? raw?.results ?? []);
        setBrokers(Array.isArray(list) ? list : []);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [projectId]);

  return (
    <>
      <AnalysisLabel>STRUCTURAL HOLES · BURT&apos;S BROKERAGE</AnalysisLabel>
      <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--fg-3)' }}>
        Entities bridging otherwise-disconnected clusters. Lower constraint = stronger broker.
      </p>
      {loading ? <LoadingLine /> : err ? <ErrorLine msg={err} /> : brokers.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--fg-3)', fontStyle: 'italic' }}>No structural brokers detected for this project.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {brokers.slice(0, 8).map((b, i) => {
            const name = b.name || b.entity || b.id || `Broker ${i + 1}`;
            const constraint = b.constraint;
            const effSize = b.effective_size ?? b.eff_size;
            const degree = b.degree;
            return (
              <div key={b.id || name + i} style={{ padding: '10px 12px', background: 'var(--paper)', border: '1px solid var(--line-soft)', borderRadius: 2 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)', flex: 1 }}>{name}</span>
                  <span style={{ padding: '1px 6px', fontFamily: 'var(--mono)', fontSize: 9, letterSpacing: '0.08em', color: 'var(--signal-ink)', background: 'var(--signal-soft)', borderRadius: 2, fontWeight: 600 }}>
                    BROKER
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 12, fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-3)' }}>
                  {typeof constraint === 'number' && <span>constraint <span style={{ color: 'var(--ink)' }}>{constraint.toFixed(2)}</span></span>}
                  {typeof effSize === 'number' && <span>eff. size <span style={{ color: 'var(--ink)' }}>{effSize.toFixed(2)}</span></span>}
                  {typeof degree === 'number' && <span>degree <span style={{ color: 'var(--ink)' }}>{degree}</span></span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

function EmptyAnalysis({ label, body }: { label: string; body: string }) {
  return (
    <>
      <AnalysisLabel>{label}</AnalysisLabel>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--fg-3)', fontStyle: 'italic' }}>{body}</p>
    </>
  );
}
function LoadingLine() {
  return <p style={{ fontSize: 11.5, color: 'var(--fg-3)', fontFamily: 'var(--mono)', letterSpacing: '0.06em' }}>LOADING…</p>;
}
function ErrorLine({ msg }: { msg: string }) {
  return <p style={{ fontSize: 11.5, color: 'var(--warn)', fontFamily: 'var(--mono)' }}>error · {msg}</p>;
}

function AnalysisLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.2em',
      color: 'var(--fg-3)', fontWeight: 600, marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

function StatBlock({ label, value }: { label: string; value: number }) {
  return (
    <div
      style={{
        padding: '10px 12px',
        background: 'var(--paper)',
        border: '1px solid var(--line)',
        borderRadius: 3,
      }}
    >
      <div style={{ fontFamily: 'var(--mono)', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>
        {value.toLocaleString()}
      </div>
      <div
        style={{
          fontFamily: 'var(--mono)',
          fontSize: 9.5,
          color: 'var(--fg-3)',
          letterSpacing: '0.14em',
          marginTop: 2,
        }}
      >
        {label.toUpperCase()}
      </div>
    </div>
  );
}
