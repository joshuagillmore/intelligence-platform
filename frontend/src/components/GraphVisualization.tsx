'use client';
import { useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';

interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
  entity_category?: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
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
  Person: '#f97316',
  Organization: '#3b82f6',
  Location: '#22c55e',
  IPAddress: '#06b6d4',
  Domain: '#a855f7',
  Hash: '#ec4899',
  ThreatActor: '#ef4444',
  TTP: '#eab308',
  Vulnerability: '#f43f5e',
  Document: '#6b7280',
  Assessment: '#14b8a6',
  Technology: '#06b6d4',
  Weapon: '#f43f5e',
  Vehicle: '#8b5cf6',
  Facility: '#84cc16',
  Financial: '#f59e0b',
  Infrastructure: '#64748b',
  Software: '#0ea5e9',
  Hardware: '#78716c',
  MilitaryUnit: '#dc2626',
  GovernmentAgency: '#2563eb',
  Country: '#16a34a',
  City: '#65a30d',
  Region: '#059669',
  Campaign: '#d946ef',
  Malware: '#be123c',
  Topic: '#7c3aed',
  Report: '#475569',
  Product: '#ea580c',
  Custom: '#78716c',
};

const CATEGORY_COLORS: Record<string, string> = {
  Person: '#f97316',
  Organization: '#3b82f6',
  Location: '#22c55e',
  Cyber: '#06b6d4',
  Equipment: '#f43f5e',
  Event: '#eab308',
  Financial: '#f59e0b',
  Intelligence: '#6b7280',
  Campaign: '#ef4444',
  Other: '#78716c',
};

const COMMUNITY_PALETTE = [
  '#f97316', '#3b82f6', '#22c55e', '#ef4444', '#a855f7',
  '#06b6d4', '#eab308', '#ec4899', '#14b8a6', '#f43f5e',
  '#84cc16', '#8b5cf6', '#f59e0b', '#10b981', '#6366f1',
  '#e11d48', '#0ea5e9', '#d946ef', '#78716c', '#fb923c',
];

function getColor(entityType: string, entityCategory?: string): string {
  return TYPE_COLORS[entityType] || CATEGORY_COLORS[entityCategory || ''] || CATEGORY_COLORS['Other'];
}

function getCommunityColor(communityId: number): string {
  return COMMUNITY_PALETTE[communityId % COMMUNITY_PALETTE.length];
}

// Hierarchical Y tiers by entity type
const HIERARCHY_TIERS: Record<string, number> = {
  Person: 0,
  ThreatActor: 0,
  Organization: 1,
  Event: 1,
  Campaign: 1,
  TTP: 2,
  Vulnerability: 2,
  Document: 2,
  Hash: 3,
  Malware: 3,
  IPAddress: 4,
  Domain: 4,
  Location: 4,
};

export default function GraphVisualization({
  nodes,
  edges,
  onNodeClick,
  selectedNodeId,
  layout = 'force',
  colorMode = 'type',
  communityMap,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);

  const render = useCallback(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    // Define glow filter for selected nodes
    const defs = svg.append('defs');
    const filter = defs.append('filter').attr('id', 'glow');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur');
    const feMerge = filter.append('feMerge');
    feMerge.append('feMergeNode').attr('in', 'coloredBlur');
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

    // Container for zoom
    const g = svg.append('g');

    // Zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);

    // Prepare edge data mapping source_id/target_id to source/target for d3
    const edgeData: GraphEdge[] = edges.map(e => ({
      ...e,
      source: e.source_id,
      target: e.target_id,
    }));

    // Build degree map
    const degreeMap: Record<string, number> = {};
    edges.forEach(e => {
      degreeMap[e.source_id] = (degreeMap[e.source_id] || 0) + 1;
      degreeMap[e.target_id] = (degreeMap[e.target_id] || 0) + 1;
    });

    // Scale radius: min 5, max 20, based on degree
    const maxDegree = Math.max(1, ...Object.values(degreeMap));
    function nodeRadius(d: GraphNode): number {
      const degree = degreeMap[d.id] || 0;
      return 5 + (degree / maxDegree) * 15;
    }

    // Node color function based on colorMode
    function nodeColor(d: GraphNode): string {
      if (colorMode === 'community' && communityMap && communityMap[d.id] !== undefined) {
        return getCommunityColor(communityMap[d.id]);
      }
      return getColor(d.entity_type, d.entity_category);
    }

    // --- Layout-specific positioning ---
    if (layout === 'radial') {
      // Find center node: highest degree (proxy for PageRank when stats unavailable)
      const sortedByDegree = [...nodes].sort((a, b) => (degreeMap[b.id] || 0) - (degreeMap[a.id] || 0));
      const centerNode = sortedByDegree[0];

      // BFS to assign rings
      const visited = new Set<string>();
      const ringMap: Record<string, number> = {};
      const queue: { id: string; ring: number }[] = [{ id: centerNode.id, ring: 0 }];
      visited.add(centerNode.id);
      ringMap[centerNode.id] = 0;

      // Build adjacency
      const adj: Record<string, string[]> = {};
      edges.forEach(e => {
        if (!adj[e.source_id]) adj[e.source_id] = [];
        if (!adj[e.target_id]) adj[e.target_id] = [];
        adj[e.source_id].push(e.target_id);
        adj[e.target_id].push(e.source_id);
      });

      while (queue.length > 0) {
        const { id, ring } = queue.shift()!;
        const neighbors = adj[id] || [];
        for (const nid of neighbors) {
          if (!visited.has(nid)) {
            visited.add(nid);
            ringMap[nid] = ring + 1;
            queue.push({ id: nid, ring: ring + 1 });
          }
        }
      }
      // Assign unvisited nodes to max ring + 1
      const maxRing = Math.max(0, ...Object.values(ringMap));
      for (const node of nodes) {
        if (ringMap[node.id] === undefined) {
          ringMap[node.id] = maxRing + 1;
        }
      }

      // Position nodes in concentric circles
      const ringRadius = Math.min(width, height) / (2 * (maxRing + 2));
      const ringCounts: Record<number, number> = {};
      const ringIndices: Record<string, number> = {};
      for (const node of nodes) {
        const r = ringMap[node.id];
        if (!ringCounts[r]) ringCounts[r] = 0;
        ringIndices[node.id] = ringCounts[r];
        ringCounts[r]++;
      }

      for (const node of nodes) {
        const r = ringMap[node.id];
        if (r === 0) {
          node.fx = width / 2;
          node.fy = height / 2;
        } else {
          const count = ringCounts[r];
          const angle = (2 * Math.PI * ringIndices[node.id]) / count;
          node.fx = width / 2 + r * ringRadius * Math.cos(angle);
          node.fy = height / 2 + r * ringRadius * Math.sin(angle);
        }
        node.x = node.fx!;
        node.y = node.fy!;
      }
    } else if (layout === 'hierarchical') {
      // Group by tier
      const tiers: Record<number, GraphNode[]> = {};
      let maxTier = 0;
      for (const node of nodes) {
        const tier = HIERARCHY_TIERS[node.entity_type] ?? 2;
        if (!tiers[tier]) tiers[tier] = [];
        tiers[tier].push(node);
        if (tier > maxTier) maxTier = tier;
      }

      const tierKeys = Object.keys(tiers).map(Number).sort((a, b) => a - b);
      const rowHeight = height / (tierKeys.length + 1);

      for (let ti = 0; ti < tierKeys.length; ti++) {
        const tier = tierKeys[ti];
        const row = tiers[tier];
        const colWidth = width / (row.length + 1);
        for (let ci = 0; ci < row.length; ci++) {
          const node = row[ci];
          node.fx = colWidth * (ci + 1);
          node.fy = rowHeight * (ti + 1);
          node.x = node.fx;
          node.y = node.fy;
        }
      }
    } else {
      // Force layout: clear fixed positions
      for (const node of nodes) {
        node.fx = null;
        node.fy = null;
      }
    }

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(edgeData).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<GraphNode>().radius(d => nodeRadius(d) + 10));

    // For non-force layouts, run simulation briefly then stop (edges still need linking)
    if (layout !== 'force') {
      simulation.alpha(0).stop();
    }

    simulationRef.current = simulation;

    // Draw edges
    const link = g.append('g')
      .selectAll('line')
      .data(edgeData)
      .join('line')
      .attr('stroke', '#4b5563')
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.5);

    // Edge labels - hidden by default, shown on hover
    const linkLabel = g.append('g')
      .selectAll('text')
      .data(edgeData)
      .join('text')
      .text(d => d.rel_type || '')
      .attr('font-size', '8px')
      .attr('fill', '#9ca3af')
      .attr('text-anchor', 'middle')
      .attr('pointer-events', 'none')
      .attr('opacity', 0);

    // Hover zones on edges to show labels
    g.append('g')
      .selectAll('line')
      .data(edgeData)
      .join('line')
      .attr('stroke', 'transparent')
      .attr('stroke-width', 12)
      .attr('cursor', 'default')
      .on('mouseenter', (_event, d) => {
        linkLabel.filter(l => l === d).attr('opacity', 1);
        link.filter(l => l === d).attr('stroke', '#9ca3af').attr('stroke-width', 2);
      })
      .on('mouseleave', (_event, d) => {
        linkLabel.filter(l => l === d).attr('opacity', 0);
        link.filter(l => l === d).attr('stroke', '#4b5563').attr('stroke-width', 1);
      });

    // Store hover zones reference for tick updates
    const linkHover = g.selectAll<SVGLineElement, GraphEdge>('g:last-child line');

    // Draw nodes
    const node = g.append('g')
      .selectAll<SVGCircleElement, GraphNode>('circle')
      .data(nodes)
      .join('circle')
      .attr('r', d => nodeRadius(d))
      .attr('fill', d => nodeColor(d))
      .attr('stroke', d => d.id === selectedNodeId ? '#ffffff' : 'transparent')
      .attr('stroke-width', d => d.id === selectedNodeId ? 3 : 0)
      .attr('filter', d => d.id === selectedNodeId ? 'url(#glow)' : 'none')
      .attr('cursor', 'pointer')
      .on('click', (event, d) => {
        onNodeClick(d, event as unknown as MouseEvent);
      })
      .call(d3.drag<SVGCircleElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          // For non-force layouts, keep fixed position after drag
          if (layout === 'force') {
            d.fx = null;
            d.fy = null;
          }
        })
      );

    // Node labels
    const label = g.append('g')
      .selectAll('text')
      .data(nodes)
      .join('text')
      .text(d => d.name)
      .attr('font-size', '10px')
      .attr('fill', '#e5e7eb')
      .attr('text-anchor', 'middle')
      .attr('dy', d => -(nodeRadius(d) + 4))
      .attr('pointer-events', 'none');

    // Legend
    if (colorMode === 'type') {
      const legendTypes = Object.keys(TYPE_COLORS);
      const legendG = svg.append('g')
        .attr('transform', `translate(12, ${height - legendTypes.length * 18 - 12})`);

      legendG.append('rect')
        .attr('x', -6)
        .attr('y', -6)
        .attr('width', 120)
        .attr('height', legendTypes.length * 18 + 12)
        .attr('rx', 6)
        .attr('fill', 'rgba(15, 23, 42, 0.85)')
        .attr('stroke', '#334155')
        .attr('stroke-width', 1);

      legendTypes.forEach((type, i) => {
        const row = legendG.append('g').attr('transform', `translate(4, ${i * 18 + 6})`);
        row.append('circle').attr('r', 5).attr('cx', 5).attr('cy', 4).attr('fill', TYPE_COLORS[type]);
        row.append('text')
          .attr('x', 16)
          .attr('y', 8)
          .attr('font-size', '9px')
          .attr('fill', '#d1d5db')
          .text(type);
      });
    } else if (colorMode === 'community' && communityMap) {
      // Community color legend
      const communityIds = Array.from(new Set(Object.values(communityMap))).sort((a, b) => a - b);
      const legendG = svg.append('g')
        .attr('transform', `translate(12, ${height - communityIds.length * 18 - 12})`);

      legendG.append('rect')
        .attr('x', -6)
        .attr('y', -6)
        .attr('width', 130)
        .attr('height', communityIds.length * 18 + 12)
        .attr('rx', 6)
        .attr('fill', 'rgba(15, 23, 42, 0.85)')
        .attr('stroke', '#334155')
        .attr('stroke-width', 1);

      communityIds.forEach((cid, i) => {
        const row = legendG.append('g').attr('transform', `translate(4, ${i * 18 + 6})`);
        row.append('circle').attr('r', 5).attr('cx', 5).attr('cy', 4).attr('fill', getCommunityColor(cid));
        row.append('text')
          .attr('x', 16)
          .attr('y', 8)
          .attr('font-size', '9px')
          .attr('fill', '#d1d5db')
          .text(`Community ${cid}`);
      });
    }

    // Keyboard / interaction hints
    const hints = ['Shift+Click: Multi-select', 'Scroll: Zoom', 'Drag: Pan'];
    const hintsG = svg.append('g')
      .attr('transform', `translate(${width - 140}, ${height - hints.length * 16 - 12})`);

    hintsG.append('rect')
      .attr('x', -6)
      .attr('y', -6)
      .attr('width', 140)
      .attr('height', hints.length * 16 + 12)
      .attr('rx', 6)
      .attr('fill', 'rgba(15, 23, 42, 0.85)')
      .attr('stroke', '#334155')
      .attr('stroke-width', 1);

    hints.forEach((hint, i) => {
      hintsG.append('text')
        .attr('x', 4)
        .attr('y', i * 16 + 10)
        .attr('font-size', '9px')
        .attr('fill', '#9ca3af')
        .text(hint);
    });

    function tick() {
      link
        .attr('x1', d => (d.source as GraphNode).x || 0)
        .attr('y1', d => (d.source as GraphNode).y || 0)
        .attr('x2', d => (d.target as GraphNode).x || 0)
        .attr('y2', d => (d.target as GraphNode).y || 0);

      linkHover
        .attr('x1', d => (d.source as GraphNode).x || 0)
        .attr('y1', d => (d.source as GraphNode).y || 0)
        .attr('x2', d => (d.target as GraphNode).x || 0)
        .attr('y2', d => (d.target as GraphNode).y || 0);

      linkLabel
        .attr('x', d => (((d.source as GraphNode).x || 0) + ((d.target as GraphNode).x || 0)) / 2)
        .attr('y', d => (((d.source as GraphNode).y || 0) + ((d.target as GraphNode).y || 0)) / 2);

      node
        .attr('cx', d => d.x || 0)
        .attr('cy', d => d.y || 0);

      label
        .attr('x', d => d.x || 0)
        .attr('y', d => d.y || 0);
    }

    if (layout === 'force') {
      simulation.on('tick', tick);
    } else {
      // For static layouts, manually run tick once to position everything
      // Need to resolve link references first
      simulation.tick(1);
      tick();
    }

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, onNodeClick, selectedNodeId, layout, colorMode, communityMap]);

  useEffect(() => {
    render();
    return () => {
      if (simulationRef.current) simulationRef.current.stop();
    };
  }, [render]);

  return (
    <svg
      ref={svgRef}
      className="w-full h-full bg-navy-900 rounded-lg"
      style={{ minHeight: '400px' }}
    />
  );
}
