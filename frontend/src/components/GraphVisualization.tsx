'use client';
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  entity_type: string;
  entity_category?: string;
  community_id?: number;
  pagerank?: number;
  degree?: number;
  members?: string[];
  isCommunity?: boolean;
}

interface GraphEdge extends d3.SimulationLinkDatum<GraphNode> {
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  weight?: number;
}

export type LayoutMode = 'force' | 'radial' | 'hierarchical';
export type ColorMode = 'type' | 'community';

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode, event?: MouseEvent) => void;
  selectedNodeId?: string | null;
  layout?: LayoutMode;
  colorMode?: ColorMode;
  communityMap?: Record<string, number>;
}

const TYPE_COLORS: Record<string, string> = {
  Person: '#f97316', Organization: '#3b82f6', Location: '#22c55e',
  IPAddress: '#06b6d4', Domain: '#a855f7', Hash: '#ec4899',
  ThreatActor: '#ef4444', TTP: '#eab308', Vulnerability: '#f43f5e',
  Document: '#6b7280', Assessment: '#14b8a6', Malware: '#be123c',
  Campaign: '#d946ef', Community: '#8b5cf6', Date: '#94a3b8', Technology: '#06b6d4',
  Weapon: '#f43f5e', Facility: '#84cc16', Software: '#0ea5e9',
  MilitaryUnit: '#dc2626', GovernmentAgency: '#2563eb',
  Country: '#16a34a', City: '#65a30d', Custom: '#78716c',
};

const COMMUNITY_PALETTE = [
  '#f97316', '#3b82f6', '#22c55e', '#ef4444', '#a855f7',
  '#06b6d4', '#eab308', '#ec4899', '#14b8a6', '#f43f5e',
];

export default function GraphVisualization({
  nodes, edges, onNodeClick, selectedNodeId,
  layout = 'force', colorMode = 'type', communityMap,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const onClickRef = useRef(onNodeClick);
  onClickRef.current = onNodeClick;

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    // DEEP COPY data to prevent D3 from mutating React state
    const simNodes: GraphNode[] = nodes.map(n => ({ ...n }));
    const simEdges: GraphEdge[] = edges.map(e => ({
      ...e,
      source: e.source_id,
      target: e.target_id,
    }));

    // Build degree map
    const deg: Record<string, number> = {};
    edges.forEach(e => {
      deg[e.source_id] = (deg[e.source_id] || 0) + 1;
      deg[e.target_id] = (deg[e.target_id] || 0) + 1;
    });
    const maxDeg = Math.max(1, ...Object.values(deg));

    function radius(d: GraphNode): number {
      if (d.isCommunity) return Math.min(35, 12 + (d.members?.length || 2) * 1.5);
      return 5 + ((deg[d.id] || 0) / maxDeg) * 15;
    }

    function color(d: GraphNode): string {
      if (colorMode === 'community') {
        const cid = communityMap?.[d.id] ?? d.community_id;
        if (cid != null && cid >= 0) return COMMUNITY_PALETTE[cid % COMMUNITY_PALETTE.length];
      }
      return TYPE_COLORS[d.entity_type] || '#78716c';
    }

    // Container with zoom
    const g = svg.append('g');
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => g.attr('transform', event.transform))
    );

    // Simulation
    const sim = d3.forceSimulation<GraphNode>(simNodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(simEdges).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide<GraphNode>().radius(d => radius(d) + 5));

    // Edges
    const link = g.append('g')
      .selectAll('line')
      .data(simEdges)
      .join('line')
      .attr('stroke', '#4b5563')
      .attr('stroke-width', d => Math.min(3, d.weight || 1))
      .attr('stroke-opacity', 0.5);

    // Nodes
    const node = g.append('g')
      .selectAll<SVGCircleElement, GraphNode>('circle')
      .data(simNodes)
      .join('circle')
      .attr('r', d => radius(d))
      .attr('fill', d => color(d))
      .attr('stroke', d => d.id === selectedNodeId ? '#fff' : d.isCommunity ? '#8b5cf6' : 'none')
      .attr('stroke-width', d => d.id === selectedNodeId ? 3 : d.isCommunity ? 2 : 0)
      .attr('stroke-dasharray', d => d.isCommunity ? '4,2' : 'none')
      .attr('cursor', 'pointer')
      .on('click', (event, d) => onClickRef.current(d, event as unknown as MouseEvent))
      .call(d3.drag<SVGCircleElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on('end', (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          if (layout === 'force') { d.fx = null; d.fy = null; }
        })
      );

    // Labels
    const label = g.append('g')
      .selectAll('text')
      .data(simNodes)
      .join('text')
      .text(d => d.name.length > 25 ? d.name.slice(0, 22) + '...' : d.name)
      .attr('font-size', '9px')
      .attr('fill', '#d1d5db')
      .attr('text-anchor', 'middle')
      .attr('dy', d => -(radius(d) + 3))
      .attr('pointer-events', 'none');

    // Legend — only show types that exist in this graph
    const usedTypes = Array.from(new Set(simNodes.map(n => n.entity_type))).sort();
    const legendG = svg.append('g').attr('transform', `translate(10, ${Math.max(10, height - usedTypes.length * 16 - 10)})`);
    legendG.append('rect')
      .attr('x', -4).attr('y', -4)
      .attr('width', 110).attr('height', usedTypes.length * 16 + 8)
      .attr('rx', 4).attr('fill', 'rgba(15,23,42,0.85)').attr('stroke', '#334155');
    usedTypes.forEach((t, i) => {
      const row = legendG.append('g').attr('transform', `translate(2, ${i * 16 + 4})`);
      row.append('circle').attr('r', 4).attr('cx', 4).attr('cy', 4).attr('fill', TYPE_COLORS[t] || '#78716c');
      row.append('text').attr('x', 14).attr('y', 7).attr('font-size', '8px').attr('fill', '#d1d5db').text(t);
    });

    // Tick
    sim.on('tick', () => {
      link
        .attr('x1', d => (d.source as GraphNode).x || 0)
        .attr('y1', d => (d.source as GraphNode).y || 0)
        .attr('x2', d => (d.target as GraphNode).x || 0)
        .attr('y2', d => (d.target as GraphNode).y || 0);
      node.attr('cx', d => d.x || 0).attr('cy', d => d.y || 0);
      label.attr('x', d => d.x || 0).attr('y', d => (d.y || 0) - radius(d) - 3);
    });

    return () => { sim.stop(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // Only re-render when actual data content changes
    nodes.length, edges.length, selectedNodeId, layout, colorMode,
    nodes.map(n => n.id).join(','),
  ]);

  return (
    <svg ref={svgRef} className="w-full h-full bg-navy-900 rounded-lg" style={{ minHeight: '400px' }} />
  );
}
