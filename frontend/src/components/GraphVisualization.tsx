'use client';
import { useEffect, useRef, useCallback } from 'react';
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
  first_seen?: string;
  last_seen?: string;
}

export type LayoutMode = 'force' | 'radial' | 'hierarchical';
export type ColorMode = 'type' | 'community';

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode, event?: MouseEvent) => void;
  onEdgeClick?: (edge: GraphEdge, event?: MouseEvent) => void;
  selectedNodeId?: string | null;
  highlightedNodeIds?: Set<string>;
  highlightedEdgeKeys?: Set<string>;
  layout?: LayoutMode;
  colorMode?: ColorMode;
  communityMap?: Record<string, number>;
  egoHighlightDepth?: number;
  onPositionsUpdate?: (positions: Record<string, { x: number; y: number }>) => void;
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

/** Abbreviate relationship type for edge labels: COMMUNICATES_WITH -> Comm. With */
function abbreviateRelType(rel: string): string {
  const words = rel.split('_');
  if (words.length === 1) return rel.charAt(0).toUpperCase() + rel.slice(1).toLowerCase();
  return words.map(w => w.charAt(0).toUpperCase() + w.slice(1, 4).toLowerCase()).join(' ');
}

export default function GraphVisualization({
  nodes, edges, onNodeClick, onEdgeClick, selectedNodeId,
  highlightedNodeIds, highlightedEdgeKeys,
  layout = 'force', colorMode = 'type', communityMap,
  egoHighlightDepth = 1,
  onPositionsUpdate,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const onClickRef = useRef(onNodeClick);
  const onEdgeClickRef = useRef(onEdgeClick);
  const onPositionsRef = useRef(onPositionsUpdate);
  onClickRef.current = onNodeClick;
  onEdgeClickRef.current = onEdgeClick;
  onPositionsRef.current = onPositionsUpdate;

  const currentZoomRef = useRef(1);

  // Refs for selection styling (updated without re-rendering the sim)
  const nodeSelRef = useRef<d3.Selection<SVGCircleElement, GraphNode, SVGGElement, unknown> | null>(null);
  const linkSelRef = useRef<d3.Selection<SVGLineElement, GraphEdge, SVGGElement, unknown> | null>(null);
  const labelSelRef = useRef<d3.Selection<SVGTextElement, GraphNode, SVGGElement, unknown> | null>(null);
  const colorFnRef = useRef<(d: GraphNode) => string>(() => '#78716c');
  const adjacencyRef = useRef<Record<string, string[]>>({});

  const emitPositions = useCallback((simNodes: GraphNode[]) => {
    if (!onPositionsRef.current) return;
    const positions: Record<string, { x: number; y: number }> = {};
    simNodes.forEach(n => {
      if (n.x != null && n.y != null) {
        positions[n.id] = { x: n.x, y: n.y };
      }
    });
    onPositionsRef.current(positions);
  }, []);

  // === Main effect: builds the simulation (does NOT depend on selectedNodeId) ===
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

    // Build adjacency for layout algorithms
    const adjacencySet: Record<string, Set<string>> = {};
    edges.forEach(e => {
      if (!adjacencySet[e.source_id]) adjacencySet[e.source_id] = new Set();
      if (!adjacencySet[e.target_id]) adjacencySet[e.target_id] = new Set();
      adjacencySet[e.source_id].add(e.target_id);
      adjacencySet[e.target_id].add(e.source_id);
    });
    const adjacency: Record<string, string[]> = {};
    Object.keys(adjacencySet).forEach(k => { adjacency[k] = Array.from(adjacencySet[k]); });
    adjacencyRef.current = adjacency;

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
    colorFnRef.current = color;

    // Convert Set props to lookup-friendly form
    const hlNodeSet = highlightedNodeIds || new Set<string>();
    const hlEdgeSet = highlightedEdgeKeys || new Set<string>();
    const isHighlighted = (id: string) => hlNodeSet.size > 0 && hlNodeSet.has(id);
    const isEdgeHighlighted = (sid: string, tid: string) => {
      if (hlEdgeSet.size === 0) return false;
      return hlEdgeSet.has(`${sid}-${tid}`) || hlEdgeSet.has(`${tid}-${sid}`);
    };
    const hasHighlights = hlNodeSet.size > 0;

    // Container with zoom
    const g = svg.append('g');
    const zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
        currentZoomRef.current = event.transform.k;
        g.selectAll('.edge-label')
          .attr('opacity', event.transform.k > 1.2 ? 0.8 : 0);
      });
    svg.call(zoomBehavior);

    // --- Apply layout-specific forces or positions ---
    const sim = d3.forceSimulation<GraphNode>(simNodes);

    // Use a stored ref for radial/hierarchical center (not live selectedNodeId)
    const layoutCenterId = selectedNodeId || (simNodes.length > 0 ? simNodes[0].id : '');

    if (layout === 'radial') {
      const hopMap: Record<string, number> = {};
      if (layoutCenterId) {
        const queue: string[] = [layoutCenterId];
        hopMap[layoutCenterId] = 0;
        while (queue.length > 0) {
          const current = queue.shift()!;
          const neighbors = adjacency[current] || [];
          for (const neighbor of neighbors) {
            if (hopMap[neighbor] === undefined) {
              hopMap[neighbor] = hopMap[current] + 1;
              queue.push(neighbor);
            }
          }
        }
      }

      const maxHop = Math.max(1, ...Object.values(hopMap));
      const ringDistance = Math.min(width, height) / (2 * (maxHop + 1));

      simNodes.forEach(n => {
        if ((hopMap[n.id] ?? maxHop + 1) === 0) {
          n.fx = width / 2;
          n.fy = height / 2;
        }
      });

      sim
        .force('link', d3.forceLink<GraphNode, GraphEdge>(simEdges).id(d => d.id).distance(60).strength(0.3))
        .force('radial', d3.forceRadial<GraphNode>(
          d => (hopMap[d.id] ?? maxHop + 1) * ringDistance,
          width / 2, height / 2
        ).strength(0.8))
        .force('collide', d3.forceCollide<GraphNode>().radius(d => radius(d) + 5));

    } else if (layout === 'hierarchical') {
      const layers: Record<string, number> = {};
      const layerNodes: Record<number, string[]> = {};

      if (layoutCenterId) {
        const queue: string[] = [layoutCenterId];
        layers[layoutCenterId] = 0;
        while (queue.length > 0) {
          const current = queue.shift()!;
          const neighbors = adjacency[current] || [];
          for (const neighbor of neighbors) {
            if (layers[neighbor] === undefined) {
              layers[neighbor] = layers[current] + 1;
              queue.push(neighbor);
            }
          }
        }
      }

      const maxLayer = Math.max(0, ...Object.values(layers));
      simNodes.forEach(n => {
        if (layers[n.id] === undefined) layers[n.id] = maxLayer + 1;
      });

      simNodes.forEach(n => {
        const layer = layers[n.id];
        if (!layerNodes[layer]) layerNodes[layer] = [];
        layerNodes[layer].push(n.id);
      });

      const layerHeight = height / (maxLayer + 3);
      simNodes.forEach(n => {
        const layer = layers[n.id];
        const siblings = layerNodes[layer];
        const idx = siblings.indexOf(n.id);
        const layerWidth = width / (siblings.length + 1);
        n.fx = layerWidth * (idx + 1);
        n.fy = layerHeight * (layer + 1);
      });

      sim
        .force('link', d3.forceLink<GraphNode, GraphEdge>(simEdges).id(d => d.id).distance(40).strength(0))
        .force('collide', d3.forceCollide<GraphNode>().radius(d => radius(d) + 3));
      sim.alpha(0.1);

    } else {
      sim
        .force('link', d3.forceLink<GraphNode, GraphEdge>(simEdges).id(d => d.id).distance(80))
        .force('charge', d3.forceManyBody().strength(-200))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collide', d3.forceCollide<GraphNode>().radius(d => radius(d) + 5));
    }

    // --- Edge lines ---
    const linkG = g.append('g');

    linkG.selectAll<SVGLineElement, GraphEdge>('.edge-hit')
      .data(simEdges)
      .join('line')
      .attr('class', 'edge-hit')
      .attr('stroke', 'transparent')
      .attr('stroke-width', 12)
      .attr('cursor', 'pointer')
      .on('click', (event, d) => {
        if (onEdgeClickRef.current) {
          onEdgeClickRef.current(d, event as unknown as MouseEvent);
        }
      });

    const link = linkG.selectAll<SVGLineElement, GraphEdge>('.edge-visible')
      .data(simEdges)
      .join('line')
      .attr('class', 'edge-visible')
      .attr('stroke', d => {
        const sid = typeof d.source === 'string' ? d.source : (d.source as GraphNode).id;
        const tid = typeof d.target === 'string' ? d.target : (d.target as GraphNode).id;
        if (isEdgeHighlighted(sid, tid)) return '#fbbf24';
        return hasHighlights ? '#1e293b' : '#4b5563';
      })
      .attr('stroke-width', d => {
        const sid = typeof d.source === 'string' ? d.source : (d.source as GraphNode).id;
        const tid = typeof d.target === 'string' ? d.target : (d.target as GraphNode).id;
        if (isEdgeHighlighted(sid, tid)) return 3;
        return Math.min(3, d.weight || 1);
      })
      .attr('stroke-opacity', d => {
        const sid = typeof d.source === 'string' ? d.source : (d.source as GraphNode).id;
        const tid = typeof d.target === 'string' ? d.target : (d.target as GraphNode).id;
        if (hasHighlights && !isEdgeHighlighted(sid, tid)) return 0.15;
        return 0.5;
      })
      .attr('pointer-events', 'none');

    // Store ref for selection effect
    linkSelRef.current = link as unknown as d3.Selection<SVGLineElement, GraphEdge, SVGGElement, unknown>;

    // Edge labels
    const edgeLabelG = g.append('g');
    edgeLabelG.selectAll<SVGTextElement, GraphEdge>('.edge-label')
      .data(simEdges)
      .join('text')
      .attr('class', 'edge-label')
      .text(d => abbreviateRelType(d.rel_type))
      .attr('font-size', '7px')
      .attr('fill', '#9ca3af')
      .attr('text-anchor', 'middle')
      .attr('pointer-events', 'none')
      .attr('opacity', 0);

    const edgeConfG = g.append('g');
    const edgeConf = edgeConfG.selectAll<SVGCircleElement, GraphEdge>('.edge-conf')
      .data(simEdges.filter(d => d.confidence != null))
      .join('circle')
      .attr('class', 'edge-conf')
      .attr('r', 2.5)
      .attr('fill', d => {
        const c = d.confidence || 0;
        if (c >= 0.8) return '#22c55e';
        if (c >= 0.5) return '#eab308';
        return '#ef4444';
      })
      .attr('opacity', 0)
      .attr('pointer-events', 'none');

    // Nodes
    const node = g.append('g')
      .selectAll<SVGCircleElement, GraphNode>('circle')
      .data(simNodes)
      .join('circle')
      .attr('r', d => radius(d))
      .attr('fill', d => {
        if (hasHighlights && !isHighlighted(d.id)) {
          return '#374151';
        }
        return color(d);
      })
      .attr('stroke', d => {
        if (isHighlighted(d.id)) return '#fbbf24';
        if (d.isCommunity) return '#8b5cf6';
        return 'none';
      })
      .attr('stroke-width', d => {
        if (isHighlighted(d.id)) return 2;
        if (d.isCommunity) return 2;
        return 0;
      })
      .attr('stroke-dasharray', d => d.isCommunity ? '4,2' : 'none')
      .attr('opacity', d => hasHighlights && !isHighlighted(d.id) ? 0.3 : 1)
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

    // Store ref for selection effect
    nodeSelRef.current = node as unknown as d3.Selection<SVGCircleElement, GraphNode, SVGGElement, unknown>;

    // Node labels
    const label = g.append('g')
      .selectAll<SVGTextElement, GraphNode>('text')
      .data(simNodes)
      .join('text')
      .text(d => d.name.length > 25 ? d.name.slice(0, 22) + '...' : d.name)
      .attr('font-size', '9px')
      .attr('fill', d => hasHighlights && !isHighlighted(d.id) ? '#4b5563' : '#d1d5db')
      .attr('text-anchor', 'middle')
      .attr('dy', d => -(radius(d) + 3))
      .attr('pointer-events', 'none');

    labelSelRef.current = label as unknown as d3.Selection<SVGTextElement, GraphNode, SVGGElement, unknown>;

    // Legend
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
    let tickCount = 0;
    sim.on('tick', () => {
      tickCount++;

      const getX = (d: GraphNode | string) => typeof d === 'string' ? 0 : (d.x || 0);
      const getY = (d: GraphNode | string) => typeof d === 'string' ? 0 : (d.y || 0);

      linkG.selectAll<SVGLineElement, GraphEdge>('line')
        .attr('x1', d => getX(d.source as GraphNode))
        .attr('y1', d => getY(d.source as GraphNode))
        .attr('x2', d => getX(d.target as GraphNode))
        .attr('y2', d => getY(d.target as GraphNode));

      edgeLabelG.selectAll<SVGTextElement, GraphEdge>('.edge-label')
        .attr('x', d => (getX(d.source as GraphNode) + getX(d.target as GraphNode)) / 2)
        .attr('y', d => (getY(d.source as GraphNode) + getY(d.target as GraphNode)) / 2 - 4);

      edgeConf
        .attr('cx', d => (getX(d.source as GraphNode) + getX(d.target as GraphNode)) / 2)
        .attr('cy', d => (getY(d.source as GraphNode) + getY(d.target as GraphNode)) / 2 + 4)
        .attr('opacity', currentZoomRef.current > 1.5 ? 0.7 : 0);

      node.attr('cx', d => d.x || 0).attr('cy', d => d.y || 0);
      label.attr('x', d => d.x || 0).attr('y', d => (d.y || 0) - radius(d) - 3);

      if (tickCount % 50 === 0) {
        emitPositions(simNodes);
      }
    });

    sim.on('end', () => emitPositions(simNodes));

    return () => { sim.stop(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    nodes.length, edges.length, layout, colorMode,
    nodes.map(n => n.id).join(','),
    // eslint-disable-next-line no-nested-ternary
    highlightedNodeIds ? highlightedNodeIds.size : 0,
    highlightedEdgeKeys ? highlightedEdgeKeys.size : 0,
  ]);

  // === Selection highlight effect: updates visuals WITHOUT rebuilding simulation ===
  useEffect(() => {
    const nodeSel = nodeSelRef.current;
    const linkSel = linkSelRef.current;
    const labelSel = labelSelRef.current;
    if (!nodeSel || !linkSel || !labelSel) return;

    const adj = adjacencyRef.current;
    const colorFn = colorFnRef.current;

    // Compute ego network nodes within egoHighlightDepth hops
    const egoSet = new Set<string>();
    if (selectedNodeId) {
      egoSet.add(selectedNodeId);
      let frontier = [selectedNodeId];
      for (let d = 0; d < egoHighlightDepth; d++) {
        const nextFrontier: string[] = [];
        for (const nid of frontier) {
          for (const neighbor of (adj[nid] || [])) {
            if (!egoSet.has(neighbor)) {
              egoSet.add(neighbor);
              nextFrontier.push(neighbor);
            }
          }
        }
        frontier = nextFrontier;
      }
    }

    const hasEgo = egoSet.size > 0;

    // Update node visuals
    nodeSel
      .attr('fill', d => {
        if (hasEgo && !egoSet.has(d.id)) return '#374151';
        return colorFn(d);
      })
      .attr('stroke', d => {
        if (d.id === selectedNodeId) return '#fff';
        if (hasEgo && egoSet.has(d.id) && d.id !== selectedNodeId) return '#fbbf24';
        if (d.isCommunity) return '#8b5cf6';
        return 'none';
      })
      .attr('stroke-width', d => {
        if (d.id === selectedNodeId) return 3;
        if (hasEgo && egoSet.has(d.id)) return 2;
        if (d.isCommunity) return 2;
        return 0;
      })
      .attr('opacity', d => hasEgo && !egoSet.has(d.id) ? 0.2 : 1);

    // Update edge visuals
    linkSel
      .attr('stroke', d => {
        const sid = typeof d.source === 'string' ? d.source : (d.source as GraphNode).id;
        const tid = typeof d.target === 'string' ? d.target : (d.target as GraphNode).id;
        if (hasEgo && egoSet.has(sid) && egoSet.has(tid)) return '#fbbf24';
        return hasEgo ? '#1e293b' : '#4b5563';
      })
      .attr('stroke-width', d => {
        const sid = typeof d.source === 'string' ? d.source : (d.source as GraphNode).id;
        const tid = typeof d.target === 'string' ? d.target : (d.target as GraphNode).id;
        if (hasEgo && egoSet.has(sid) && egoSet.has(tid)) return 2.5;
        return Math.min(3, d.weight || 1);
      })
      .attr('stroke-opacity', d => {
        const sid = typeof d.source === 'string' ? d.source : (d.source as GraphNode).id;
        const tid = typeof d.target === 'string' ? d.target : (d.target as GraphNode).id;
        if (hasEgo && !(egoSet.has(sid) && egoSet.has(tid))) return 0.08;
        return 0.6;
      });

    // Update label visuals
    labelSel
      .attr('fill', d => hasEgo && !egoSet.has(d.id) ? '#374151' : '#d1d5db')
      .attr('font-weight', d => d.id === selectedNodeId ? 'bold' : 'normal');
  }, [selectedNodeId, egoHighlightDepth]);

  return (
    <svg ref={svgRef} className="w-full h-full bg-navy-900 rounded-lg" style={{ minHeight: '400px' }} />
  );
}
