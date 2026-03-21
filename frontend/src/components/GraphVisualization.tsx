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
  onNodeClick: (node: GraphNode) => void;
  selectedNodeId?: string | null;
}

const TYPE_COLORS: Record<string, string> = {
  Person: '#f97316',
  Organization: '#3b82f6',
  Location: '#22c55e',
  ThreatActor: '#ef4444',
  Document: '#6b7280',
  IPAddress: '#06b6d4',
  Domain: '#a855f7',
  Event: '#eab308',
  Hash: '#ec4899',
  Vulnerability: '#f43f5e',
};

function getColor(entityType: string): string {
  return TYPE_COLORS[entityType] || '#6b7280';
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

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(edgeData).id(d => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30));

    simulationRef.current = simulation;

    // Draw edges
    const link = g.append('g')
      .selectAll('line')
      .data(edgeData)
      .join('line')
      .attr('stroke', '#313849')
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.6);

    // Edge labels
    const linkLabel = g.append('g')
      .selectAll('text')
      .data(edgeData)
      .join('text')
      .text(d => d.rel_type || '')
      .attr('font-size', '8px')
      .attr('fill', '#6b7280')
      .attr('text-anchor', 'middle')
      .attr('pointer-events', 'none');

    // Draw nodes
    const node = g.append('g')
      .selectAll<SVGCircleElement, GraphNode>('circle')
      .data(nodes)
      .join('circle')
      .attr('r', d => Math.max(6, Math.min(20, 6 + (degreeMap[d.id] || 0) * 2)))
      .attr('fill', d => getColor(d.entity_type))
      .attr('stroke', d => d.id === selectedNodeId ? '#ffffff' : 'transparent')
      .attr('stroke-width', d => d.id === selectedNodeId ? 3 : 0)
      .attr('cursor', 'pointer')
      .on('click', (_event, d) => {
        onNodeClick(d);
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
      .attr('dy', d => -(Math.max(6, Math.min(20, 6 + (degreeMap[d.id] || 0) * 2)) + 4))
      .attr('pointer-events', 'none');

    simulation.on('tick', () => {
      link
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
