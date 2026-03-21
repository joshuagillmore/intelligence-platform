'use client';
import { useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';

interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
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

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode, event?: MouseEvent) => void;
  selectedNodeId?: string | null;
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
};

const DEFAULT_COLOR = '#9ca3af';

function getColor(entityType: string): string {
  return TYPE_COLORS[entityType] || DEFAULT_COLOR;
}

export default function GraphVisualization({ nodes, edges, onNodeClick, selectedNodeId }: Props) {
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

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(edgeData).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<GraphNode>().radius(d => nodeRadius(d) + 10));

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
      .attr('fill', d => getColor(d.entity_type))
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
          d.fx = null;
          d.fy = null;
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

    simulation.on('tick', () => {
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
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, onNodeClick, selectedNodeId]);

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
