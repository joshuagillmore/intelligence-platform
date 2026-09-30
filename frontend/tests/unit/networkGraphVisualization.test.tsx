import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import GraphVisualization from '@/components/GraphVisualization';

/**
 * GraphVisualization rebuilds its d3 simulation when the data changes. The
 * selection/ego styling lived in a separate effect that only ran when the
 * selection changed, so any rebuild (a filter tweak, a path highlight) drew
 * the graph with no selected node. Community colours had the same problem
 * with communities that load after the graph.
 */

type Node = { id: string; name: string; entity_type: string };
type Edge = { source_id: string; target_id: string; rel_type: string; source: string; target: string };

const n = (id: string, entity_type = 'Organization'): Node => ({ id, name: id.toUpperCase(), entity_type });
const e = (s: string, t: string): Edge => ({ source_id: s, target_id: t, rel_type: 'LINKED_TO', source: s, target: t });

const noop = () => {};

function circleFor(container: HTMLElement, name: string): SVGCircleElement {
  const circles = Array.from(container.querySelectorAll('circle'));
  const hit = circles.find(c => c.querySelector('title')?.textContent === name);
  if (!hit) throw new Error(`no circle titled ${name}`);
  return hit as SVGCircleElement;
}

afterEach(() => cleanup());

describe('GraphVisualization styling survives a rebuild', () => {
  it('keeps the selected node ringed after the data changes', () => {
    const { container, rerender } = render(
      <GraphVisualization nodes={[n('a'), n('b'), n('c')]} edges={[e('a', 'b')]} onNodeClick={noop} selectedNodeId="a" />,
    );
    expect(circleFor(container, 'A').getAttribute('stroke')).toBe('#fff');

    // A filter change hands over a different node set: the simulation rebuilds.
    rerender(
      <GraphVisualization nodes={[n('a'), n('b'), n('c'), n('d')]} edges={[e('a', 'b'), e('c', 'd')]} onNodeClick={noop} selectedNodeId="a" />,
    );
    expect(circleFor(container, 'A').getAttribute('stroke')).toBe('#fff');
    // The ego styling came back too: c is outside a's 1-hop neighbourhood.
    expect(circleFor(container, 'C').getAttribute('opacity')).toBe('0.2');
  });

  it('shows a path highlight and still marks the selected node', () => {
    const nodes = [n('a'), n('b'), n('c')];
    const edges = [e('a', 'b'), e('b', 'c')];
    const { container, rerender } = render(
      <GraphVisualization nodes={nodes} edges={edges} onNodeClick={noop} selectedNodeId="c" />,
    );
    rerender(
      <GraphVisualization
        nodes={nodes} edges={edges} onNodeClick={noop} selectedNodeId="c"
        highlightedNodeIds={new Set(['a', 'b'])} highlightedEdgeKeys={new Set(['a-b'])}
      />,
    );
    expect(circleFor(container, 'A').getAttribute('stroke')).toBe('#fbbf24');
    expect(circleFor(container, 'B').getAttribute('stroke')).toBe('#fbbf24');
    // Off the path, so dimmed — but still ringed as the selection.
    expect(circleFor(container, 'C').getAttribute('stroke')).toBe('#fff');
    expect(circleFor(container, 'C').getAttribute('opacity')).toBe('0.3');
  });

  it('recolours by community when communities arrive after the graph', () => {
    const nodes = [n('a'), n('b')];
    const edges = [e('a', 'b')];
    const { container, rerender } = render(
      <GraphVisualization nodes={nodes} edges={edges} onNodeClick={noop} colorMode="community" communityMap={{}} />,
    );
    const before = circleFor(container, 'A').getAttribute('fill');
    rerender(
      <GraphVisualization nodes={nodes} edges={edges} onNodeClick={noop} colorMode="community" communityMap={{ a: 0, b: 0 }} />,
    );
    const after = circleFor(container, 'A').getAttribute('fill');
    expect(after).toBe('#f97316'); // COMMUNITY_PALETTE[0]
    expect(after).not.toBe(before);
  });

  it('does not crash when handed an edge to a node it was not given (P-6)', () => {
    expect(() => render(
      <GraphVisualization nodes={[n('a'), n('b')]} edges={[e('a', 'b'), e('a', 'gone')]} onNodeClick={noop} />,
    )).not.toThrow();
  });
});
