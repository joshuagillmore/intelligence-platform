/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';
import { useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';

export interface TreeNode {
  name: string;
  id: string;
  entity_type?: string;
  count?: number;
  summary?: string;
  children?: TreeNode[];
  _children?: TreeNode[];
}

export type LayoutMode = 'radial' | 'horizontal';

interface CrossReference {
  doc_id: string;
  doc_name: string;
  topic_ids: string[];
}

interface TopicMindMapProps {
  data: TreeNode;
  onNodeClick?: (node: TreeNode) => void;
  selectedNodeId?: string | null;
  layout?: LayoutMode;
  searchQuery?: string;
  crossReferences?: CrossReference[];
  onBreadcrumbsChange?: (breadcrumbs: { id: string; name: string }[]) => void;
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
  if (node.data?.entity_type === 'topic') return '#a855f7';
  let current = node;
  while (current) {
    const id = current.data?.id || '';
    if (BRANCH_COLORS[id]) return BRANCH_COLORS[id];
    current = current.parent;
  }
  return '#6b7280';
}

function getNodeRadius(node: any): number {
  const count = node.data?.count || 0;
  if (count === 0) return 4;
  return Math.max(4, Math.min(14, 4 + Math.log2(count + 1) * 2.5));
}

function getAncestorPath(node: any): { id: string; name: string }[] {
  const path: { id: string; name: string }[] = [];
  let current = node;
  while (current) {
    path.unshift({ id: current.data?.id || '', name: current.data?.name || '' });
    current = current.parent;
  }
  return path;
}

function matchesSearch(node: any, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  const name = (node.data?.name || '').toLowerCase();
  const keywords = (node.data?.keywords || []).join(' ').toLowerCase();
  return name.includes(q) || keywords.includes(q);
}

function hasMatchingDescendant(node: any, query: string): boolean {
  if (matchesSearch(node, query)) return true;
  const children = node.children || node._children || [];
  return children.some((c: any) => hasMatchingDescendant(c, query));
}

export default function TopicMindMap({
  data,
  onNodeClick,
  selectedNodeId,
  layout = 'radial',
  searchQuery = '',
  crossReferences = [],
  onBreadcrumbsChange,
}: TopicMindMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const onClickRef = useRef(onNodeClick);
  const onBreadcrumbsRef = useRef(onBreadcrumbsChange);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  onClickRef.current = onNodeClick;
  onBreadcrumbsRef.current = onBreadcrumbsChange;

  // Expose zoom controls
  const zoomIn = useCallback(() => {
    if (svgRef.current && zoomRef.current) {
      d3.select(svgRef.current)
        .transition().duration(300)
        .call(zoomRef.current.scaleBy, 1.3);
    }
  }, []);

  const zoomOut = useCallback(() => {
    if (svgRef.current && zoomRef.current) {
      d3.select(svgRef.current)
        .transition().duration(300)
        .call(zoomRef.current.scaleBy, 0.7);
    }
  }, []);

  const zoomReset = useCallback(() => {
    if (svgRef.current && zoomRef.current) {
      d3.select(svgRef.current)
        .transition().duration(500)
        .call(zoomRef.current.transform, d3.zoomIdentity);
    }
  }, []);

  // Attach zoom methods to the SVG element for external access
  useEffect(() => {
    const el = svgRef.current as any;
    if (el) {
      el.__zoomIn = zoomIn;
      el.__zoomOut = zoomOut;
      el.__zoomReset = zoomReset;
    }
  }, [zoomIn, zoomOut, zoomReset]);

  useEffect(() => {
    if (!svgRef.current || !data || !data.children?.length) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 500;
    const isRadial = layout === 'radial';

    const g = svg.append('g');

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => g.attr('transform', event.transform));
    svg.call(zoom);
    zoomRef.current = zoom;

    // Initial transform
    if (isRadial) {
      g.attr('transform', `translate(${width / 2},${height / 2})`);
      svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));
    } else {
      g.attr('transform', `translate(100,${height / 2})`);
      svg.call(zoom.transform, d3.zoomIdentity.translate(100, height / 2));
    }

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'mindmap-tooltip')
      .style('position', 'absolute')
      .style('pointer-events', 'none')
      .style('background', '#1a1f2e')
      .style('border', '1px solid #313849')
      .style('border-radius', '6px')
      .style('padding', '8px 12px')
      .style('font-size', '11px')
      .style('color', '#e5e7eb')
      .style('max-width', '280px')
      .style('z-index', '9999')
      .style('opacity', 0)
      .style('box-shadow', '0 4px 12px rgba(0,0,0,0.4)');

    // Hierarchy
    const root = d3.hierarchy<TreeNode>(data) as any;

    // Collapse beyond depth 1
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

    root.x0 = 0;
    root.y0 = 0;

    // Tree layout
    const treeLayout = isRadial
      ? d3.tree<TreeNode>().size([2 * Math.PI, Math.min(width, height) / 3])
        .separation((a: any, b: any) => (a.parent === b.parent ? 1 : 2) / a.depth)
      : d3.tree<TreeNode>().nodeSize([28, 200]);

    let nodeId = 0;
    const duration = 400;

    // Cross-reference lookup: topic_id -> [other_topic_ids that share docs]
    const crossRefMap = new Map<string, Set<string>>();
    for (const cr of crossReferences) {
      for (const tid of cr.topic_ids) {
        if (!crossRefMap.has(tid)) crossRefMap.set(tid, new Set());
        for (const other of cr.topic_ids) {
          if (other !== tid) crossRefMap.get(tid)!.add(other);
        }
      }
    }

    function update(source: any) {
      const treeData = treeLayout(root);
      const nodes = treeData.descendants();
      const links = treeData.links();

      if (!isRadial) {
        nodes.forEach((d: any) => { d.y = d.depth * 200; });
      }

      // Coordinate projection helpers
      function projectX(d: any): number {
        if (isRadial) {
          const angle = d.x - Math.PI / 2;
          return d.y * Math.cos(angle);
        }
        return d.y;
      }
      function projectY(d: any): number {
        if (isRadial) {
          const angle = d.x - Math.PI / 2;
          return d.y * Math.sin(angle);
        }
        return d.x;
      }

      // ---- LINKS ----
      const link = g.selectAll<SVGPathElement, any>('path.link')
        .data(links, (d: any) => d.target.id || (d.target.id = ++nodeId));

      const linkEnter = link.enter().insert('path', 'g')
        .attr('class', 'link')
        .attr('fill', 'none')
        .attr('stroke', '#313849')
        .attr('stroke-width', 1.5)
        .attr('stroke-opacity', 0.5)
        .attr('d', () => {
          const o = { x: source.x0 || 0, y: source.y0 || 0 };
          return linkPath(o, o);
        });

      linkEnter.merge(link as any).transition().duration(duration)
        .attr('d', (d: any) => linkPath(d.source, d.target))
        .attr('stroke-opacity', (d: any) => {
          if (!searchQuery) return 0.5;
          return hasMatchingDescendant(d.target, searchQuery) ? 0.6 : 0.1;
        });

      (link as any).exit().transition().duration(duration)
        .attr('d', () => {
          const o = { x: source.x, y: source.y };
          return linkPath(o, o);
        })
        .remove();

      function linkPath(s: any, d: any): string {
        const sx = projectX(s), sy = projectY(s);
        const dx = projectX(d), dy = projectY(d);
        if (isRadial) {
          return `M${sx},${sy}C${(sx + dx) / 2},${sy} ${(sx + dx) / 2},${dy} ${dx},${dy}`;
        }
        return `M${sx},${sy}C${(sx + dx) / 2},${sy} ${(sx + dx) / 2},${dy} ${dx},${dy}`;
      }

      // ---- NODES ----
      const node = g.selectAll<SVGGElement, any>('g.node')
        .data(nodes, (d: any) => d.id || (d.id = ++nodeId));

      const nodeEnter = node.enter().append('g')
        .attr('class', 'node')
        .attr('transform', () => `translate(${projectX(source)},${projectY(source)})`)
        .attr('cursor', 'pointer')
        .on('click', (_event: any, d: any) => {
          const hasHiddenChildren = !!d._children;
          const hasVisibleChildren = !!d.children;

          if (hasVisibleChildren) {
            d._children = d.children;
            d.children = null;
          } else if (hasHiddenChildren) {
            d.children = d._children;
            d._children = null;
          }

          update(d);

          if (onClickRef.current && !hasHiddenChildren) {
            onClickRef.current(d.data);
          }

          // Update breadcrumbs
          if (onBreadcrumbsRef.current) {
            onBreadcrumbsRef.current(getAncestorPath(d));
          }
        })
        .on('mouseover', (event: any, d: any) => {
          const name = d.data.name || 'Unnamed';
          const count = d.data.count;
          const summary = d.data.summary || '';
          const keywords = d.data.keywords || [];

          let html = `<div style="font-weight:700;margin-bottom:4px">${name}</div>`;
          if (count != null) html += `<div style="color:#9ca3af">${count} document${count !== 1 ? 's' : ''}</div>`;
          if (keywords.length > 0) html += `<div style="color:#a855f7;margin-top:3px;font-size:10px">${keywords.slice(0, 5).join(', ')}</div>`;
          if (summary) html += `<div style="color:#9ca3af;margin-top:4px;font-size:10px;font-style:italic">${summary}</div>`;

          tooltip.html(html)
            .style('left', (event.pageX + 12) + 'px')
            .style('top', (event.pageY - 10) + 'px')
            .transition().duration(150)
            .style('opacity', 1);
        })
        .on('mousemove', (event: any) => {
          tooltip
            .style('left', (event.pageX + 12) + 'px')
            .style('top', (event.pageY - 10) + 'px');
        })
        .on('mouseout', () => {
          tooltip.transition().duration(200).style('opacity', 0);
        });

      // Node circle with size encoding
      nodeEnter.append('circle')
        .attr('r', 1e-6)
        .attr('fill', (d: any) => getBranchColor(d))
        .attr('fill-opacity', 0.25)
        .attr('stroke', (d: any) => getBranchColor(d))
        .attr('stroke-width', (d: any) => d.data.id === selectedNodeId ? 2.5 : 1);

      // Node text
      nodeEnter.append('text')
        .attr('dy', '0.31em')
        .attr('fill', '#e5e7eb')
        .attr('font-size', '11px')
        .text((d: any) => {
          const name = d.data.name || d.data.entity_type || 'Unnamed';
          const count = d.data.count;
          const suffix = count != null ? ` (${count})` : '';
          const label = name.length > 35 ? name.slice(0, 32) + '...' : name;
          return label + suffix;
        });

      // Expand/collapse indicator
      nodeEnter.append('text')
        .attr('class', 'toggle')
        .attr('dy', '0.35em')
        .attr('text-anchor', 'middle')
        .attr('fill', '#9ca3af')
        .attr('font-size', '10px');

      // Update
      const nodeUpdate = nodeEnter.merge(node as any);

      nodeUpdate.transition().duration(duration)
        .attr('transform', (d: any) => `translate(${projectX(d)},${projectY(d)})`)
        .attr('opacity', (d: any) => {
          if (!searchQuery) {
            // Selection spotlight: dim siblings of selected node
            if (selectedNodeId && d.data.id !== selectedNodeId && d.parent) {
              const selectedSibling = (d.parent.children || []).some(
                (c: any) => c.data.id === selectedNodeId
              );
              if (selectedSibling) return 0.4;
            }
            return 1;
          }
          return hasMatchingDescendant(d, searchQuery) || matchesSearch(d, searchQuery) ? 1 : 0.15;
        });

      // Update circles
      nodeUpdate.select('circle')
        .attr('r', (d: any) => getNodeRadius(d))
        .attr('fill-opacity', (d: any) => d.data.id === selectedNodeId ? 0.5 : 0.25)
        .attr('stroke-width', (d: any) => d.data.id === selectedNodeId ? 2.5 : 1);

      // Position text relative to node
      nodeUpdate.select('text:not(.toggle)')
        .attr('x', (d: any) => {
          const r = getNodeRadius(d);
          if (isRadial) {
            return d.x < Math.PI === !d.children ? r + 4 : -(r + 4);
          }
          return r + 6;
        })
        .attr('text-anchor', (d: any) => {
          if (isRadial) {
            return d.x < Math.PI === !d.children ? 'start' : 'end';
          }
          return 'start';
        });

      // Toggle indicator position
      nodeUpdate.select('.toggle')
        .attr('x', (d: any) => {
          const r = getNodeRadius(d);
          if (isRadial) {
            return d.x < Math.PI === !d.children ? -(r + 8) : r + 8;
          }
          return -(r + 8);
        })
        .text((d: any) => d._children ? '+' : d.children ? '\u2212' : '');

      // Exit
      const nodeExit = (node as any).exit().transition().duration(duration)
        .attr('transform', () => `translate(${projectX(source)},${projectY(source)})`)
        .attr('opacity', 0)
        .remove();
      nodeExit.select('circle').attr('r', 1e-6);

      // ---- CROSS-REFERENCE LINKS ----
      g.selectAll('path.cross-ref').remove();

      if (selectedNodeId && crossRefMap.has(selectedNodeId)) {
        const selectedNode = nodes.find((n: any) => n.data.id === selectedNodeId);
        const linkedTopicIds = crossRefMap.get(selectedNodeId)!;

        for (const linkedId of Array.from(linkedTopicIds)) {
          const linkedNode = nodes.find((n: any) => n.data.id === linkedId);
          if (selectedNode && linkedNode) {
            g.append('path')
              .attr('class', 'cross-ref')
              .attr('fill', 'none')
              .attr('stroke', '#f59e0b')
              .attr('stroke-width', 1)
              .attr('stroke-dasharray', '4,4')
              .attr('stroke-opacity', 0.5)
              .attr('d', linkPath(selectedNode, linkedNode));
          }
        }
      }

      // Stash old positions
      nodes.forEach((d: any) => {
        d.x0 = d.x;
        d.y0 = d.y;
      });
    }

    update(root);

    // Cleanup tooltip on unmount
    return () => {
      tooltip.remove();
    };
  }, [data, layout, searchQuery, crossReferences]); // selectedNodeId removed to prevent tree rebuild

  // Separate effect to update selection visuals without rebuilding the tree
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);

    // Update circle styles for selection
    svg.selectAll<SVGGElement, any>('g.node').each(function(d: any) {
      const g = d3.select(this);
      const isSelected = d.data?.id === selectedNodeId;

      g.select('circle')
        .attr('fill-opacity', isSelected ? 0.5 : 0.25)
        .attr('stroke-width', isSelected ? 2.5 : 1);

      // Selection spotlight: dim siblings of selected node
      if (!searchQuery) {
        let opacity = 1;
        if (selectedNodeId && d.data?.id !== selectedNodeId && d.parent) {
          const selectedSibling = (d.parent.children || []).some(
            (c: any) => c.data.id === selectedNodeId
          );
          if (selectedSibling) opacity = 0.4;
        }
        g.attr('opacity', opacity);
      }
    });

    // Update cross-reference links
    svg.selectAll('path.cross-ref').remove();
  }, [selectedNodeId, searchQuery]);

  return (
    <svg
      ref={svgRef}
      className="w-full bg-[#0a0f1c] rounded-lg border border-[#1a1f2e]"
      style={{ height: '100%', minHeight: '300px' }}
    />
  );
}
