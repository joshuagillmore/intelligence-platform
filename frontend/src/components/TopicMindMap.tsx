/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';
import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface TreeNode {
  name: string;
  id: string;
  entity_type?: string;
  count?: number;
  children?: TreeNode[];
  _children?: TreeNode[];
}

interface TopicMindMapProps {
  data: TreeNode;
  onNodeClick?: (node: TreeNode) => void;
  selectedNodeId?: string | null;
}

const BRANCH_COLORS: Record<string, string> = {
  'branch-themes': '#a855f7',
  'branch-docs': '#3b82f6',
  'branch-types': '#22c55e',
  'branch-geo': '#f97316',
  'branch-actors': '#ef4444',
  'branch-categories': '#06b6d4',
  'root': '#adc6ff',
};

function getBranchColor(node: any): string {
  let current = node;
  while (current) {
    const id = current.data?.id || '';
    if (BRANCH_COLORS[id]) return BRANCH_COLORS[id];
    current = current.parent;
  }
  return '#6b7280';
}

export default function TopicMindMap({ data, onNodeClick, selectedNodeId }: TopicMindMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const onClickRef = useRef(onNodeClick);
  onClickRef.current = onNodeClick;

  useEffect(() => {
    if (!svgRef.current || !data || !data.children?.length) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const height = svgRef.current.clientHeight || 400;
    const margin = { top: 20, bottom: 20, left: 120 };

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    // Zoom
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on('zoom', (event) => g.attr('transform', event.transform))
    );

    // Create hierarchy -- start with only first level expanded
    const root = d3.hierarchy<TreeNode>(data) as d3.HierarchyPointNode<TreeNode> & { _children?: any; x0?: number; y0?: number };

    // Collapse all children beyond depth 1
    function collapse(d: any) {
      if (d.children && d.depth >= 1) {
        d._children = d.children;
        d._children.forEach(collapse);
        d.children = null;
      } else if (d.children) {
        d.children.forEach(collapse);
      }
    }
    root.children?.forEach(collapse);

    root.x0 = (height - margin.top - margin.bottom) / 2;
    root.y0 = 0;

    const treeLayout = d3.tree<TreeNode>().nodeSize([28, 220]);

    let i = 0;
    const duration = 400;

    function update(source: any) {
      const treeData = treeLayout(root);
      const nodes = treeData.descendants();
      const links = treeData.links();

      // Normalize depth
      nodes.forEach((d: any) => { d.y = d.depth * 220; });

      // ---- NODES ----
      const node = g.selectAll<SVGGElement, any>('g.node')
        .data(nodes, (d: any) => d.id || (d.id = ++i));

      const nodeEnter = node.enter().append('g')
        .attr('class', 'node')
        .attr('transform', () => `translate(${source.y0 || 0},${source.x0 || 0})`)
        .attr('cursor', 'pointer')
        .on('click', (_event: any, d: any) => {
          if (d.children) {
            d._children = d.children;
            d.children = null;
          } else if (d._children) {
            d.children = d._children;
            d._children = null;
          }
          update(d);
          if (onClickRef.current) {
            onClickRef.current(d.data);
          }
        });

      // Node rectangle
      nodeEnter.append('rect')
        .attr('rx', 6)
        .attr('ry', 6)
        .attr('width', 1e-6)
        .attr('height', 1e-6)
        .attr('fill', (d: any) => getBranchColor(d))
        .attr('fill-opacity', 0.15)
        .attr('stroke', (d: any) => getBranchColor(d))
        .attr('stroke-width', (d: any) => d.data.id === selectedNodeId ? 2 : 1);

      // Node text
      nodeEnter.append('text')
        .attr('dy', '0.35em')
        .attr('x', 8)
        .attr('text-anchor', 'start')
        .attr('fill', '#e5e7eb')
        .attr('font-size', '11px')
        .text((d: any) => {
          const name = d.data.name || '';
          const count = d.data.count;
          const suffix = count != null ? ` (${count})` : '';
          return name.length > 30 ? name.slice(0, 27) + '...' + suffix : name + suffix;
        });

      // Expand/collapse indicator
      nodeEnter.append('text')
        .attr('class', 'toggle')
        .attr('dy', '0.35em')
        .attr('x', -12)
        .attr('text-anchor', 'middle')
        .attr('fill', '#9ca3af')
        .attr('font-size', '10px')
        .text((d: any) => d._children ? '+' : d.children ? '\u2212' : '');

      // Update
      const nodeUpdate = nodeEnter.merge(node as any);

      nodeUpdate.transition().duration(duration)
        .attr('transform', (d: any) => `translate(${d.y},${d.x})`);

      // Size rectangles to fit text
      nodeUpdate.each(function(this: SVGGElement, d: any) {
        const textEl = d3.select(this).select('text:not(.toggle)');
        const bbox = (textEl.node() as SVGTextElement)?.getBBox();
        const w = bbox ? bbox.width + 16 : 100;
        const h = 22;
        d3.select(this).select('rect')
          .attr('x', 0)
          .attr('y', -h / 2)
          .attr('width', w)
          .attr('height', h)
          .attr('fill-opacity', d.data.id === selectedNodeId ? 0.3 : 0.15)
          .attr('stroke-width', d.data.id === selectedNodeId ? 2 : 1);
      });

      // Update toggle text
      nodeUpdate.select('.toggle')
        .text((d: any) => d._children ? '+' : d.children ? '\u2212' : '');

      // Exit
      const nodeExit = (node as any).exit().transition().duration(duration)
        .attr('transform', () => `translate(${source.y},${source.x})`)
        .remove();
      nodeExit.select('rect').attr('width', 1e-6).attr('height', 1e-6);

      // ---- LINKS ----
      const link = g.selectAll<SVGPathElement, any>('path.link')
        .data(links, (d: any) => d.target.id);

      const linkEnter = link.enter().insert('path', 'g')
        .attr('class', 'link')
        .attr('fill', 'none')
        .attr('stroke', '#313849')
        .attr('stroke-width', 1.5)
        .attr('d', () => {
          const o = { x: source.x0 || 0, y: source.y0 || 0 };
          return diagonal(o, o);
        });

      linkEnter.merge(link as any).transition().duration(duration)
        .attr('d', (d: any) => diagonal(d.source, d.target));

      (link as any).exit().transition().duration(duration)
        .attr('d', () => {
          const o = { x: source.x, y: source.y };
          return diagonal(o, o);
        })
        .remove();

      // Stash old positions
      nodes.forEach((d: any) => {
        d.x0 = d.x;
        d.y0 = d.y;
      });
    }

    function diagonal(s: any, d: any) {
      return `M ${s.y} ${s.x}
              C ${(s.y + d.y) / 2} ${s.x},
                ${(s.y + d.y) / 2} ${d.x},
                ${d.y} ${d.x}`;
    }

    update(root);
  }, [data, selectedNodeId]);

  return (
    <svg
      ref={svgRef}
      className="w-full bg-[#0a0f1c] rounded-lg border border-[#1a1f2e]"
      style={{ height: '350px' }}
    />
  );
}
