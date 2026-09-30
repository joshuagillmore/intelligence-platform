'use client';
import { useEffect, useRef, useCallback, useMemo } from 'react';
import * as d3 from 'd3';
import { TYPE_COLOR_HEX as TYPE_COLORS } from '@/lib/entityStyles';
import { labelledNodeIds } from '@/lib/graphLabels';

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

// TYPE_COLORS imported from '@/lib/entityStyles' (single source of truth)

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

/** The inputs that decide how nodes, edges and labels are painted. */
interface StyleInputs {
  selectedNodeId?: string | null;
  egoHighlightDepth: number;
  highlightedNodeIds?: Set<string>;
  highlightedEdgeKeys?: Set<string>;
}

interface PaintTargets {
  node: d3.Selection<SVGCircleElement, GraphNode, SVGGElement, unknown>;
  link: d3.Selection<SVGLineElement, GraphEdge, SVGGElement, unknown>;
  label: d3.Selection<SVGTextElement, GraphNode, SVGGElement, unknown>;
  colorFn: (d: GraphNode) => string;
  adjacency: Record<string, string[]>;
  labelled: Set<string>;
}

const NO_IDS: Set<string> = new Set();

function edgeEndpointIds(d: GraphEdge): [string, string] {
  const sid = typeof d.source === 'string' ? d.source : (d.source as GraphNode).id;
  const tid = typeof d.target === 'string' ? d.target : (d.target as GraphNode).id;
  return [sid, tid];
}

/** The selected node and everything within `depth` hops of it. */
function egoNeighbourhood(adj: Record<string, string[]>, selectedNodeId: string | null | undefined, depth: number): Set<string> {
  const egoSet = new Set<string>();
  if (!selectedNodeId) return egoSet;
  egoSet.add(selectedNodeId);
  let frontier = [selectedNodeId];
  for (let d = 0; d < depth; d++) {
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
  return egoSet;
}

/**
 * Paint selection, ego and path-highlight styling onto the rendered graph.
 *
 * Runs after every simulation build and whenever the styling inputs change, so
 * a rebuild never drops the selected node's ring. A path highlight, when there
 * is one, decides what is dimmed (it is an explicit overlay the analyst clears);
 * otherwise the selection's ego neighbourhood does. The selected node keeps its
 * ring and bold label either way.
 */
function paintGraph(t: PaintTargets, inputs: StyleInputs) {
  const { selectedNodeId, egoHighlightDepth } = inputs;
  const hlNodes = inputs.highlightedNodeIds ?? NO_IDS;
  const hlEdges = inputs.highlightedEdgeKeys ?? NO_IDS;
  const hasPath = hlNodes.size > 0;
  const onPath = (id: string) => hasPath && hlNodes.has(id);
  const edgeOnPath = (sid: string, tid: string) =>
    hlEdges.size > 0 && (hlEdges.has(`${sid}-${tid}`) || hlEdges.has(`${tid}-${sid}`));

  const ego = hasPath ? NO_IDS : egoNeighbourhood(t.adjacency, selectedNodeId, egoHighlightDepth);
  const hasEgo = ego.size > 0;
  const emphasised = (id: string) => (hasPath ? onPath(id) : ego.has(id));
  const dimmed = (id: string) => (hasPath || hasEgo) && !emphasised(id);
  const edgeEmphasised = (sid: string, tid: string) =>
    hasPath ? edgeOnPath(sid, tid) : hasEgo && ego.has(sid) && ego.has(tid);

  t.node
    .attr('fill', d => (dimmed(d.id) ? '#374151' : t.colorFn(d)))
    .attr('stroke', d => {
      if (d.id === selectedNodeId) return '#fff';
      if (emphasised(d.id)) return '#fbbf24';
      if (d.isCommunity) return '#8b5cf6';
      return 'none';
    })
    .attr('stroke-width', d => {
      if (d.id === selectedNodeId) return 3;
      if (emphasised(d.id)) return 2;
      if (d.isCommunity) return 2;
      return 0;
    })
    .attr('opacity', d => (dimmed(d.id) ? (hasPath ? 0.3 : 0.2) : 1));

  t.link
    .attr('stroke', d => {
      const [sid, tid] = edgeEndpointIds(d);
      if (edgeEmphasised(sid, tid)) return '#fbbf24';
      return hasPath || hasEgo ? '#1e293b' : '#4b5563';
    })
    .attr('stroke-width', d => {
      const [sid, tid] = edgeEndpointIds(d);
      if (edgeEmphasised(sid, tid)) return hasPath ? 3 : 2.5;
      return Math.min(3, d.weight || 1);
    })
    .attr('stroke-opacity', d => {
      const [sid, tid] = edgeEndpointIds(d);
      if (hasPath) return edgeOnPath(sid, tid) ? 0.5 : 0.15;
      if (hasEgo && !edgeEmphasised(sid, tid)) return 0.08;
      return 0.6;
    });

  // A selected node is always named, budget or not — clicking a node to find
  // out what it is and getting no name back would make the unlabelled
  // majority a dead end rather than a hover away.
  t.label
    .attr('display', d => (d.id === selectedNodeId || t.labelled.has(d.id) ? null : 'none'))
    .attr('fill', d => (dimmed(d.id) ? (hasPath ? '#4b5563' : '#374151') : '#e5e7eb'))
    .attr('font-weight', d => (d.id === selectedNodeId ? 'bold' : 'normal'));
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
  // Which ids the last render gave a label to, so the selection effect can add
  // the selected node without recomputing the ranking.
  const labelledRef = useRef<Set<string>>(new Set());
  const colorFnRef = useRef<(d: GraphNode) => string>(() => '#78716c');
  const adjacencyRef = useRef<Record<string, string[]>>({});

  // Latest props for the build effect, which re-runs on the data's content
  // (below) rather than on array identity: the page hands over fresh arrays
  // whenever any filter input settles, even when the result is unchanged, and
  // rebuilding on each would restart the layout for nothing.
  const dataRef = useRef({ nodes, edges });
  dataRef.current = { nodes, edges };
  const styleInputsRef = useRef<StyleInputs>({ selectedNodeId, egoHighlightDepth, highlightedNodeIds, highlightedEdgeKeys });
  styleInputsRef.current = { selectedNodeId, egoHighlightDepth, highlightedNodeIds, highlightedEdgeKeys };
  const nodesKey = useMemo(() => nodes.map(n => n.id).join(','), [nodes]);
  const edgesKey = useMemo(() => edges.map(e => `${e.source_id}>${e.target_id}:${e.rel_type}`).join(','), [edges]);

  const paint = useCallback((inputs: StyleInputs) => {
    const node = nodeSelRef.current;
    const link = linkSelRef.current;
    const label = labelSelRef.current;
    if (!node || !link || !label) return;
    paintGraph({
      node, link, label,
      colorFn: colorFnRef.current,
      adjacency: adjacencyRef.current,
      labelled: labelledRef.current,
    }, inputs);
  }, []);

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
    const { nodes } = dataRef.current;
    if (!svgRef.current || nodes.length === 0) return;

    // An edge whose endpoint is not among the nodes makes d3's forceLink throw
    // "node not found" and takes the whole view down. Callers should not send
    // one; this makes sure a caller that does costs an edge, not the page.
    const nodeIds = new Set(nodes.map(n => n.id));
    const edges = dataRef.current.edges.filter(e => nodeIds.has(e.source_id) && nodeIds.has(e.target_id));

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

    // Radial/hierarchical centre on whatever is selected at build time; a later
    // selection restyles the graph without re-laying it out.
    const layoutCenterId = styleInputsRef.current.selectedNodeId || (simNodes.length > 0 ? simNodes[0].id : '');

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
        // Repulsion is capped by distance so it stays a local separating force.
        // Uncapped, every node pushes every other node forever, and with ~440
        // of 500 nodes carrying no edge to hold them, the whole cloud expands
        // until it meets the clamp below.
        .force('charge', d3.forceManyBody().strength(-200).distanceMax(400))
        .force('center', d3.forceCenter(width / 2, height / 2))
        // The restoring force the layout was missing. forceCenter only shifts
        // the mean position — it pulls on nothing individually — so nothing
        // opposed the outward drift and the clamp became the only thing
        // stopping it. A clamp with no counter-force does not contain nodes,
        // it collects them: each one that reaches the edge stays exactly on
        // it, which is why the graph rendered as a hollow rectangle with the
        // connected core marooned inside.
        .force('x', d3.forceX(width / 2).strength(0.06))
        .force('y', d3.forceY(height / 2).strength(0.06))
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

    // Stroke colour, width and opacity are set by paintGraph below.
    const link = linkG.selectAll<SVGLineElement, GraphEdge>('.edge-visible')
      .data(simEdges)
      .join('line')
      .attr('class', 'edge-visible')
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

    // Nodes. Fill, stroke and opacity are set by paintGraph below.
    const node = g.append('g')
      .selectAll<SVGCircleElement, GraphNode>('circle')
      .data(simNodes)
      .join('circle')
      .attr('r', d => radius(d))
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

    // Full name on hover — recovers any label the on-canvas text truncates or
    // clips at the container edge (e.g. long TTP names, a CVE near the boundary).
    node.append('title').text(d => d.name);

    // Store ref for selection effect
    nodeSelRef.current = node as unknown as d3.Selection<SVGCircleElement, GraphNode, SVGGElement, unknown>;

    // Node labels — only for the nodes that earn one. See lib/graphLabels:
    // labelling all 500 rendered text over text and left none of it readable.
    const labelled = labelledNodeIds(simNodes, deg);

    // Display, fill and weight are set by paintGraph below.
    const label = g.append('g')
      .selectAll<SVGTextElement, GraphNode>('text')
      .data(simNodes)
      .join('text')
      .text(d => d.name.length > 32 ? d.name.slice(0, 29) + '…' : d.name)
      .attr('font-size', '10px')
      // A dark halo painted behind the glyphs. Labels sit over edges and other
      // nodes, and 10px grey on a navy canvas crossed by a link is the case
      // where it stops being readable.
      .attr('stroke', '#0f172a')
      .attr('stroke-width', 3)
      .attr('paint-order', 'stroke')
      .attr('stroke-linejoin', 'round')
      .attr('text-anchor', 'middle')
      .attr('dy', d => -(radius(d) + 3))
      .attr('pointer-events', 'none');

    labelSelRef.current = label as unknown as d3.Selection<SVGTextElement, GraphNode, SVGGElement, unknown>;
    labelledRef.current = labelled;

    // Selection, ego and path styling for the freshly built graph — the styling
    // effect below only runs when those inputs change, not on a rebuild.
    paint(styleInputsRef.current);

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

      // A backstop against a node escaping entirely, not the thing that shapes
      // the layout — forceX/forceY above do that now. Deliberately outside the
      // viewport: a bound drawn at the visible edge is one nodes come to rest
      // against, and a row of nodes resting on a straight line reads as a
      // border the data does not have. Pinned layouts (radial/hierarchical set
      // fx/fy) are left alone.
      const escapeMargin = 400;
      const minX = -escapeMargin, maxX = width + escapeMargin;
      const minY = -escapeMargin, maxY = height + escapeMargin;
      for (const d of simNodes) {
        if (d.fx == null && d.x != null) d.x = Math.max(minX, Math.min(maxX, d.x));
        if (d.fy == null && d.y != null) d.y = Math.max(minY, Math.min(maxY, d.y));
      }

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
    // nodesKey/edgesKey stand in for the data (read through dataRef); a
    // highlight or selection change restyles without a rebuild (effect below).
    // communityMap is here because colour-by-community reads it and the
    // communities usually arrive after the graph.
  }, [nodesKey, edgesKey, layout, colorMode, communityMap, emitPositions, paint]);

  // === Styling effect: updates visuals WITHOUT rebuilding the simulation ===
  useEffect(() => {
    paint({ selectedNodeId, egoHighlightDepth, highlightedNodeIds, highlightedEdgeKeys });
  }, [paint, selectedNodeId, egoHighlightDepth, highlightedNodeIds, highlightedEdgeKeys]);

  return (
    <svg ref={svgRef} className="w-full h-full bg-navy-900 rounded-lg" style={{ minHeight: '400px' }} />
  );
}
