'use client';
import { nodeEntity, type Entity, type GraphNode } from '../types';

interface NetworkTopBarProps {
  selectedEntity: Entity | null;
  onOpenLeft: () => void;
  onOpenRight: () => void;
  // Shortest path between the two most recently clicked nodes.
  pathEndpoints: Entity[];
  pathLoading: boolean;
  pathResult: { path: string[]; length: number } | null;
  onFindPath: () => void;
  onClearPath: () => void;
  // Multi-selection and the actions over it.
  multiSelected: Entity[];
  setMultiSelected: (entities: Entity[]) => void;
  onOpenAssess: () => void;
  onOpenMerge: () => void;
  // What the canvas is showing.
  shownNodes: number;
  shownEdges: number;
  collapseCommunities: boolean;
  truncationNote: string | null;
  filteredGraphNodes: GraphNode[];
  communityMap: Record<string, number>;
}

/** Title, path finder, multi-selection actions and the node/edge counts. */
export default function NetworkTopBar({
  selectedEntity, onOpenLeft, onOpenRight,
  pathEndpoints, pathLoading, pathResult, onFindPath, onClearPath,
  multiSelected, setMultiSelected, onOpenAssess, onOpenMerge,
  shownNodes, shownEdges, collapseCommunities, truncationNote, filteredGraphNodes, communityMap,
}: NetworkTopBarProps) {
  return (
    <div className="flex-none px-4 py-2 border-b border-navy-600 bg-navy-800 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button onClick={onOpenLeft} className="md:hidden text-gray-400 hover:text-white p-1">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" /></svg>
        </button>
        <h2 className="text-lg font-bold">Network Analysis</h2>
      </div>
      <div className="flex items-center gap-4">
        {selectedEntity && (
          <button onClick={onOpenRight} className="md:hidden text-gray-400 hover:text-accent-blue p-1" title="Show details">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" /></svg>
          </button>
        )}
        {pathEndpoints.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-400">Path:</span>
            {pathEndpoints.map((e, i) => (
              <span key={e.id}>
                <span className="text-accent-blue">{e.name}</span>
                {i < pathEndpoints.length - 1 && <span className="text-gray-500 mx-1">&rarr;</span>}
              </span>
            ))}
            {pathEndpoints.length === 2 && (
              <button
                onClick={onFindPath}
                disabled={pathLoading}
                className="ml-2 bg-accent-blue hover:bg-blue-600 text-white px-3 py-1 rounded text-xs disabled:opacity-50"
              >
                {pathLoading ? 'Finding...' : 'Find Path'}
              </button>
            )}
            <button onClick={onClearPath} className="text-gray-500 hover:text-gray-300 text-xs ml-1">Clear</button>
            {pathResult && pathResult.length >= 0 && (
              <span className="text-green-400 ml-2">Path length: {pathResult.length}</span>
            )}
            {pathResult && pathResult.length < 0 && (
              <span className="text-red-400 ml-2">No path found</span>
            )}
          </div>
        )}
        {multiSelected.length > 0 && (
          <div className="hidden md:flex items-center gap-2 text-xs">
            <span className="text-gray-400">{multiSelected.length} selected</span>
            <button
              onClick={onOpenAssess}
              className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
            >
              Generate Assessment
            </button>
            {multiSelected.length >= 2 && (
              <button
                onClick={onOpenMerge}
                className="bg-purple-600 hover:bg-purple-700 text-white px-3 py-1 rounded text-xs font-medium transition-colors"
              >
                Merge Entities
              </button>
            )}
            <button
              onClick={() => setMultiSelected([])}
              className="text-gray-500 hover:text-gray-300 text-xs"
            >
              Clear
            </button>
          </div>
        )}
        <span className="text-xs md:text-sm text-gray-400">{shownNodes} nodes, {shownEdges} edges{collapseCommunities ? ' (collapsed)' : ''}</span>
        {truncationNote && (
          <span
            className="text-[10px] md:text-xs text-amber-400/80"
            title="The graph view loads the most-connected entities first. The entity list searches the whole project."
          >
            {truncationNote}
          </span>
        )}
        <div className="hidden md:flex items-center gap-2">
          <button
            onClick={() => {
              const allEntities = filteredGraphNodes.map(nodeEntity);
              setMultiSelected(allEntities);
            }}
            className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
          >
            Select All
          </button>
          {selectedEntity && communityMap[selectedEntity.id] !== undefined && (
            <button
              onClick={() => {
                const cid = communityMap[selectedEntity.id];
                const communityEntities = filteredGraphNodes
                  .filter(n => communityMap[n.id] === cid)
                  .map(nodeEntity);
                setMultiSelected(communityEntities);
              }}
              className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
            >
              Select Community ({filteredGraphNodes.filter(n => communityMap[n.id] === communityMap[selectedEntity.id]).length} members)
            </button>
          )}
          {multiSelected.length > 0 && (
            <>
              <span className="text-[10px] text-accent-blue font-medium">{multiSelected.length} selected</span>
              <button
                onClick={() => setMultiSelected([])}
                className="text-[10px] px-2 py-0.5 rounded bg-navy-600 text-gray-300 hover:bg-navy-500"
              >
                Clear
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
