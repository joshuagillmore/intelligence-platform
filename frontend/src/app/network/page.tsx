'use client';
import { useEffect, useRef, useState, Suspense } from 'react';
import Sidebar from '@/components/Sidebar';
import type { LayoutMode, ColorMode } from '@/components/GraphVisualization';
import { useProject } from '@/lib/ProjectContext';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAssistant } from '@/lib/AssistantContext';
import { graphTruncationNote } from './graphFilters';
import {
  nodeEntity,
  type EgoNetworkData, type Entity, type GraphEdge, type GraphNode, type LeftTab,
} from './types';
import { useNetworkGraph } from './hooks/useNetworkGraph';
import { useEntitySearch } from './hooks/useEntitySearch';
import { useGraphFilters } from './hooks/useGraphFilters';
import { useSnapshots } from './hooks/useSnapshots';
import { useEntitySelection } from './hooks/useEntitySelection';
import { useAiActions } from './hooks/useAiActions';
import { useEntityActions } from './hooks/useEntityActions';
import { useShortestPath } from './hooks/useShortestPath';
import { useNetworkAnalysis } from './hooks/useNetworkAnalysis';
import { useHistogram } from './hooks/useHistogram';
import { useStatisticsTable } from './hooks/useStatisticsTable';
import NetworkTopBar from './components/NetworkTopBar';
import GraphToolbar from './components/GraphToolbar';
import EntitySearchFilters from './components/EntitySearchFilters';
import GraphFilterSliders from './components/GraphFilterSliders';
import EntityList from './components/EntityList';
import SnapshotsPanel from './components/SnapshotsPanel';
import EdgeOverview from './components/EdgeOverview';
import AnalysisTab from './components/AnalysisTab';
import StatisticsTable from './components/StatisticsTable';
import GraphCanvas from './components/GraphCanvas';
import EntityPanel from './components/EntityPanel';
import EdgeDetailPanel from './components/EdgeDetailPanel';
import { AssessModal, MergeModal } from './components/NetworkModals';

/**
 * The network view: the knowledge graph on a d3 canvas, the entity browser and
 * analytics beside it, and the selected entity's or edge's detail panel. State
 * lives in the hooks under `./hooks`; `./components` render it.
 */
function NetworkPageInner() {
  const { activeProject } = useProject();
  // Chat + notebook moved to the shared, app-wide AssistantPanel (see
  // components/AssistantPanel.tsx). This page only feeds it the current
  // multi-selection so new notebook entries stay linked to those entities.
  const { setLinkedEntities } = useAssistant();
  const networkRouter = useRouter();
  const searchParams = useSearchParams();
  const selectParam = searchParams.get('select');

  // View state shared across the panels.
  const [leftTab, setLeftTab] = useState<LeftTab>('entities');
  const [mobileLeftOpen, setMobileLeftOpen] = useState(false);
  const [mobileRightOpen, setMobileRightOpen] = useState(false);
  const [typeFilterOpen, setTypeFilterOpen] = useState(false);
  const [relFilterOpen, setRelFilterOpen] = useState(false);
  const [expandedEntityTypes, setExpandedEntityTypes] = useState<Set<string>>(new Set());
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('force');
  const [colorMode, setColorMode] = useState<ColorMode>('type');
  // Ego highlight depth for graph selection
  const [egoHighlightDepth, setEgoHighlightDepth] = useState(1);
  // De-emphasize noise-tier ASSOCIATED_WITH edges in the Edge Overview stats
  const [showLowSignalRel, setShowLowSignalRel] = useState(false);
  const [multiSelected, setMultiSelected] = useState<Entity[]>([]);
  const [aiResult, setAiResult] = useState<string | null>(null);
  const [typeDropdownOpen, setTypeDropdownOpen] = useState(false);
  // Selected edge for detail panel
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  const graph = useNetworkGraph(activeProject);
  const { graphNodes, graphEdges, stats, communityMap } = graph;
  const selection = useEntitySelection(activeProject, () => {
    setMobileRightOpen(true);
    setAiResult(null);
    setTypeDropdownOpen(false);
  });
  const { selectedEntity, selectEntity } = selection;
  const search = useEntitySearch(activeProject);
  const snaps = useSnapshots(activeProject, multiSelected);
  const filters = useGraphFilters({ graphNodes, graphEdges, stats, activeSnapshotIds: snaps.activeSnapshotIds });
  const { setEventRange } = filters;
  const path = useShortestPath();
  const analysis = useNetworkAnalysis(activeProject);
  const ai = useAiActions({ activeProject, selectedEntity, multiSelected, stats, setAiResult });
  const hist = useHistogram(activeProject);
  const { histogramBucket } = hist;
  const table = useStatisticsTable(stats);
  const actions = useEntityActions({
    activeProject, selectedEntity, setSelectedEntity: selection.setSelectedEntity, multiSelected, setMultiSelected,
    setAiResult, setTypeDropdownOpen,
    reloadGraph: graph.loadGraph, reloadEntities: search.loadEntities, reloadStatistics: graph.loadStatistics,
  });

  // A new bucket clears the brush: bin keys differ between buckets.
  useEffect(() => {
    setEventRange([null, null]);
  }, [histogramBucket, setEventRange]);

  // Project-level loads. Kept apart from the entity search: they used to share
  // one effect with it, so every keystroke re-fetched the graph and five
  // analytics endpoints and unmounted the canvas while the graph reloaded.
  const { loadGraph, loadStatistics, loadCommunities, loadStructuralHoles } = graph;
  const { loadSnapshots } = snaps;
  useEffect(() => {
    loadGraph();
    loadStatistics();
    loadCommunities();
    loadSnapshots();
    loadStructuralHoles();
  }, [loadGraph, loadStatistics, loadCommunities, loadSnapshots, loadStructuralHoles]);

  // Auto-select entity from URL param (e.g., from Cyber "View in Graph").
  // Consumed once per distinct param value: re-applying it whenever graphNodes
  // changed snapped the selection back to it after the analyst had moved on.
  const consumedSelectRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectParam || graphNodes.length === 0 || consumedSelectRef.current === selectParam) return;
    consumedSelectRef.current = selectParam;
    const node = graphNodes.find(n => n.id === selectParam);
    if (node) {
      selectEntity(nodeEntity(node));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectParam, graphNodes]);

  // Keep the shared assistant's Notebook tab linked to whatever is
  // multi-selected here — preserving the entity linking the in-page notebook
  // used to do before it moved into components/AssistantPanel.
  useEffect(() => {
    setLinkedEntities(multiSelected.map(e => ({ id: e.id, name: e.name })));
  }, [multiSelected, setLinkedEntities]);

  /** Shift+click: add an entity to the multi-selection, or take it out. */
  function toggleMultiSelected(entity: Entity) {
    setMultiSelected(prev => {
      const exists = prev.find(e => e.id === entity.id);
      if (exists) return prev.filter(e => e.id !== entity.id);
      return [...prev, entity];
    });
  }

  function handleNodeClick(node: GraphNode, event?: MouseEvent) {
    const entity = nodeEntity(node);
    // Shift+click for multi-select
    if (event?.shiftKey) {
      toggleMultiSelected(entity);
      return;
    }
    selectEntity(entity);
    // Track selections for shortest path (toggle: add if not present, remove if already selected)
    path.trackPathEndpoint(entity);
  }

  // Edge click handler for detail panel (P0.4)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleEdgeClick(edge: any) {
    selection.abandonSelection(); // abandon the entity loads still in flight
    setSelectedEdge(edge as GraphEdge);
    selection.setSelectedEntity(null);
  }

  function focusEgoNetwork(ego: EgoNetworkData) {
    // Focus the graph on the ego network by filtering
    const egoIds = new Set(ego.nodes.map(n => n.id));
    filters.setFilteredGraphNodes(graphNodes.filter(n => egoIds.has(n.id)));
    filters.setFilteredGraphEdges(graphEdges.filter(e => {
      const srcId = e.source_id || e.source;
      const tgtId = e.target_id || e.target;
      return egoIds.has(srcId) && egoIds.has(tgtId);
    }));
  }

  function openDocument(docId: string) {
    networkRouter.push(`/documents/${docId}`);
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-8 pt-14 md:pt-8">
          <h2 className="text-2xl font-bold mb-4">Network Analysis</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p className="text-lg mb-2">No Project Selected</p>
            <p className="text-sm">Go to Projects and select one to begin analysis.</p>
          </div>
        </main>
      </div>
    );
  }

  const { sortedStats, maxVals } = table;
  // The statistics endpoint counts the same node population /graph samples.
  const truncationNote = graphTruncationNote(graph.graphTruncated, graphNodes.length, stats?.total_nodes);
  const { displayData, filteredGraphNodes } = filters;

  return (
    <div className="flex overflow-hidden" style={{ height: 'calc(100vh - 28px)' }}>
      <Sidebar />
      <div className="md:ml-56 flex-1 flex flex-col overflow-hidden pt-14 md:pt-0" style={{ height: 'calc(100vh - 28px)' }}>
        <NetworkTopBar
          selectedEntity={selectedEntity}
          onOpenLeft={() => setMobileLeftOpen(true)}
          onOpenRight={() => setMobileRightOpen(true)}
          pathEndpoints={path.selectedEntities}
          pathLoading={path.pathLoading}
          pathResult={path.pathResult}
          onFindPath={path.findShortestPath}
          onClearPath={path.clearPath}
          multiSelected={multiSelected}
          setMultiSelected={setMultiSelected}
          onOpenAssess={() => ai.setAssessModalOpen(true)}
          onOpenMerge={() => { actions.setMergePrimaryId(multiSelected[0].id); actions.setMergeModalOpen(true); }}
          shownNodes={displayData.nodes.length}
          shownEdges={displayData.edges.length}
          collapseCommunities={filters.collapseCommunities}
          truncationNote={truncationNote}
          filteredGraphNodes={filteredGraphNodes}
          communityMap={communityMap}
        />

        <GraphToolbar
          allRelTypes={filters.allRelTypes}
          hiddenRelTypes={filters.hiddenRelTypes}
          setHiddenRelTypes={filters.setHiddenRelTypes}
          toggleRelType={filters.toggleRelType}
          relFilterOpen={relFilterOpen}
          setRelFilterOpen={setRelFilterOpen}
          layoutMode={layoutMode}
          setLayoutMode={setLayoutMode}
          colorMode={colorMode}
          setColorMode={setColorMode}
          collapseCommunities={filters.collapseCommunities}
          setCollapseCommunities={filters.setCollapseCommunities}
          canUndo={filters.canUndo}
          canRedo={filters.canRedo}
          onUndo={filters.undo}
          onRedo={filters.redo}
        />

        {/* Main content area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left sidebar - Entity list / Statistics */}
          <div className={`${mobileLeftOpen ? 'fixed inset-0 z-40 w-full' : 'hidden'} md:relative md:block md:w-64 flex-none bg-navy-800 border-r border-navy-600 flex flex-col overflow-hidden`}>
            {/* Mobile close button */}
            <button onClick={() => setMobileLeftOpen(false)} className="md:hidden absolute top-2 right-2 z-50 text-gray-400 hover:text-white p-1">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
            </button>
            {/* Tab toggle */}
            <div className="flex border-b border-navy-600">
              {([
                ['entities', 'Entities'],
                ['statistics', 'Statistics'],
                ['analysis', 'Analysis'],
              ] as [LeftTab, string][]).map(([tab, label]) => (
                <button
                  key={tab}
                  onClick={() => setLeftTab(tab)}
                  className={`flex-1 py-2 text-xs font-medium transition-colors ${leftTab === tab ? 'text-accent-blue border-b-2 border-accent-blue' : 'text-gray-400 hover:text-gray-200'}`}
                >
                  {label}
                </button>
              ))}
            </div>

            {leftTab === 'entities' ? (
              <>
                <EntitySearchFilters
                  searchQuery={search.searchQuery}
                  setSearchQuery={search.setSearchQuery}
                  setTypeFilter={search.setTypeFilter}
                  activeTypeFilters={filters.activeTypeFilters}
                  setActiveTypeFilters={filters.setActiveTypeFilters}
                  typeFilterOpen={typeFilterOpen}
                  setTypeFilterOpen={setTypeFilterOpen}
                  graphNodes={graphNodes}
                />
                {/* Stats cards + filters (moved from Statistics tab) */}
                {stats && (
                  <GraphFilterSliders
                    stats={stats}
                    maxVals={maxVals}
                    confidenceThreshold={filters.confidenceThreshold}
                    setConfidenceThreshold={filters.setConfidenceThreshold}
                    islandMetric={filters.islandMetric}
                    setIslandMetric={filters.setIslandMetric}
                    islandThreshold={filters.islandThreshold}
                    setIslandThreshold={filters.setIslandThreshold}
                    egoHighlightDepth={egoHighlightDepth}
                    setEgoHighlightDepth={setEgoHighlightDepth}
                  />
                )}
                <EntityList
                  entities={search.entities}
                  entityTotal={search.entityTotal}
                  expandedEntityTypes={expandedEntityTypes}
                  setExpandedEntityTypes={setExpandedEntityTypes}
                  selectedEntity={selectedEntity}
                  multiSelected={multiSelected}
                  toggleMultiSelected={toggleMultiSelected}
                  selectEntity={selectEntity}
                />
                {/* Snapshots (Bins) + Mass Select Section */}
                <SnapshotsPanel
                  snapshots={snaps.snapshots}
                  activeSnapshotId={snaps.activeSnapshotId}
                  snapshotFormOpen={snaps.snapshotFormOpen}
                  setSnapshotFormOpen={snaps.setSnapshotFormOpen}
                  snapshotNameInput={snaps.snapshotNameInput}
                  setSnapshotNameInput={snaps.setSnapshotNameInput}
                  onSave={snaps.saveSnapshot}
                  onView={snaps.loadSnapshotView}
                  onClearView={snaps.clearSnapshotView}
                  onDelete={snaps.deleteSnapshot}
                  filteredGraphNodes={filteredGraphNodes}
                  selectedEntity={selectedEntity}
                  communityMap={communityMap}
                  multiSelected={multiSelected}
                  setMultiSelected={setMultiSelected}
                />
              </>
            ) : leftTab === 'statistics' ? (
              <EdgeOverview
                graphEdges={graphEdges}
                showLowSignalRel={showLowSignalRel}
                toggleLowSignalRel={() => setShowLowSignalRel(v => !v)}
              />
            ) : leftTab === 'analysis' ? (
              <AnalysisTab
                structuralHoles={graph.structuralHoles}
                selectEntity={selectEntity}
                selectedEntity={selectedEntity}
                multiSelected={multiSelected}
                influenceSteps={analysis.influenceSteps}
                setInfluenceSteps={analysis.setInfluenceSteps}
                influenceThreshold={analysis.influenceThreshold}
                setInfluenceThreshold={analysis.setInfluenceThreshold}
                influenceLoading={analysis.influenceLoading}
                influenceResult={analysis.influenceResult}
                runInfluencePropagation={analysis.runInfluencePropagation}
              />
            ) : null}
          </div>

          {/* Center - Graph or Statistics Table */}
          <div className="flex-1 flex flex-col overflow-hidden relative">
            {leftTab === 'statistics' && stats?.entity_statistics ? (
              <StatisticsTable rows={sortedStats} maxVals={maxVals} onSort={table.handleSort} sortArrow={table.sortArrow} />
            ) : (
              <GraphCanvas
                graphLoading={graph.graphLoading}
                graphError={graph.graphError}
                onRetry={loadGraph}
                hasNodes={filteredGraphNodes.length > 0}
                nodes={displayData.nodes as GraphNode[]}
                edges={displayData.edges as GraphEdge[]}
                onNodeClick={handleNodeClick}
                onEdgeClick={handleEdgeClick}
                selectedNodeId={selectedEntity?.id}
                highlightedNodeIds={path.highlightedNodeIds}
                highlightedEdgeKeys={path.highlightedEdgeKeys}
                layout={layoutMode}
                colorMode={colorMode}
                communityMap={communityMap}
                egoHighlightDepth={egoHighlightDepth}
                projectMissing={graph.projectMissing}
                projectId={activeProject?.id}
                histogram={hist.histogram}
                histogramLoading={hist.histogramLoading}
                histogramError={hist.histogramError}
                eventRange={filters.eventRange}
                setEventRange={setEventRange}
                hideUndated={filters.hideUndated}
                setHideUndated={filters.setHideUndated}
                setHistogramBucket={hist.setHistogramBucket}
                graphEdges={graphEdges}
                temporalRange={filters.temporalRange}
                setTemporalRange={filters.setTemporalRange}
              />
            )}
          </div>

          {/* Assessment modal */}
          {ai.assessModalOpen && (
            <AssessModal
              multiSelected={multiSelected}
              judgment={ai.assessJudgment}
              setJudgment={ai.setAssessJudgment}
              probability={ai.assessProbability}
              setProbability={ai.setAssessProbability}
              analyst={ai.assessAnalyst}
              setAnalyst={ai.setAssessAnalyst}
              loading={ai.assessLoading}
              onSubmit={ai.submitAssessment}
              onGenerate={ai.generateAssessmentFromModal}
              onCancel={() => ai.setAssessModalOpen(false)}
            />
          )}

          {/* Merge modal */}
          {actions.mergeModalOpen && (
            <MergeModal
              multiSelected={multiSelected}
              primaryId={actions.mergePrimaryId}
              setPrimaryId={actions.setMergePrimaryId}
              onMerge={actions.mergeEntities}
              onCancel={() => actions.setMergeModalOpen(false)}
            />
          )}

          {/* Right sidebar - Detail panel. pb-20 leaves the scroll tail clear of
              the fixed StatusBar and the assistant launcher at bottom-right. */}
          <div className={`${mobileRightOpen ? 'fixed inset-x-0 bottom-0 z-40 h-2/3 rounded-t-xl border-t' : 'hidden'} md:relative md:block md:w-80 md:h-auto md:rounded-none flex-none bg-navy-800 border-l border-navy-600 overflow-y-auto pb-20`}>
            {/* Mobile close button */}
            <button onClick={() => setMobileRightOpen(false)} className="md:hidden absolute top-2 right-2 z-50 text-gray-400 hover:text-white p-1">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
            </button>
            {selectedEntity ? (
              <EntityPanel
                entity={selectedEntity}
                selection={selection}
                analysis={analysis}
                graphEdges={graphEdges}
                onFocusEgo={focusEgoNetwork}
                aiLoading={ai.aiLoading}
                onGenerateAssessment={ai.generateAssessment}
                onGapAnalysis={ai.gapAnalysis}
                onCompetingHypotheses={ai.competingHypotheses}
                aiResult={aiResult}
                typeDropdownOpen={typeDropdownOpen}
                setTypeDropdownOpen={setTypeDropdownOpen}
                onChangeType={actions.changeEntityType}
                onOpenDocument={openDocument}
              />
            ) : selectedEdge ? (
              <EdgeDetailPanel edge={selectedEdge} onOpenDocument={openDocument} onDismiss={() => setSelectedEdge(null)} />
            ) : (
              <div className="p-4 text-center text-gray-500 text-sm mt-8">
                <p>Select an entity from the list or click a node/edge in the graph to see details.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function NetworkPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen"><LoadingSpinner size="lg" /></div>}>
      <NetworkPageInner />
    </Suspense>
  );
}
