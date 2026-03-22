interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
  community_id?: number;
  pagerank?: number;
  degree?: number;
  members?: string[];
  isCommunity?: boolean;
  [key: string]: unknown;
}

interface GraphEdge {
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  weight?: number;
  [key: string]: unknown;
}

export function collapseToCommunities(
  nodes: GraphNode[],
  edges: GraphEdge[]
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  // Group nodes by community_id
  const communities: Record<number, GraphNode[]> = {};
  nodes.forEach(node => {
    const cid = node.community_id ?? -1;
    if (!communities[cid]) communities[cid] = [];
    communities[cid].push(node);
  });

  // Create community super-nodes
  const collapsedNodes: GraphNode[] = [];
  const nodeToComm: Record<string, string> = {};

  Object.entries(communities).forEach(([cidStr, members]) => {
    const cid = parseInt(cidStr);
    if (members.length <= 1) {
      // Keep single nodes as-is
      collapsedNodes.push(members[0]);
      nodeToComm[members[0].id] = members[0].id;
    } else {
      // Find the most central node as the community label
      const central = members.reduce((a, b) =>
        (a.pagerank || 0) > (b.pagerank || 0) ? a : b
      );
      const superNode: GraphNode = {
        id: `community-${cid}`,
        name: `${central.name} (+${members.length - 1})`,
        entity_type: 'Community',
        community_id: cid,
        pagerank: Math.max(...members.map(m => m.pagerank || 0)),
        degree: members.reduce((sum, m) => sum + (m.degree || 0), 0),
        members: members.map(m => m.name),
        isCommunity: true,
      };
      collapsedNodes.push(superNode);
      members.forEach(m => { nodeToComm[m.id] = superNode.id; });
    }
  });

  // Aggregate edges between communities
  const edgeMap: Record<string, GraphEdge> = {};
  edges.forEach(edge => {
    const src = nodeToComm[edge.source_id] || edge.source_id;
    const tgt = nodeToComm[edge.target_id] || edge.target_id;
    if (src === tgt) return; // Skip intra-community edges
    const key = `${src}-${tgt}`;
    const revKey = `${tgt}-${src}`;
    if (edgeMap[key]) {
      edgeMap[key].weight = (edgeMap[key].weight || 1) + 1;
    } else if (edgeMap[revKey]) {
      edgeMap[revKey].weight = (edgeMap[revKey].weight || 1) + 1;
    } else {
      edgeMap[key] = { source_id: src, target_id: tgt, rel_type: edge.rel_type, weight: 1 };
    }
  });

  return {
    nodes: collapsedNodes,
    edges: Object.values(edgeMap),
  };
}
