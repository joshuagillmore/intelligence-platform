'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import GraphVisualization from '@/components/GraphVisualization';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi, graphApi, queryApi, llmApi } from '@/lib/api';

interface Entity {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, unknown>;
  confidence?: number;
}

interface Relationship {
  id?: string;
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  source_name?: string;
  target_name?: string;
}

interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
}

interface GraphEdge {
  source_id: string;
  target_id: string;
  rel_type: string;
  confidence?: number;
  source: string;
  target: string;
}

const ENTITY_TYPES = ['All', 'Person', 'Organization', 'Location', 'ThreatActor', 'Document', 'IPAddress', 'Domain', 'Event', 'Hash', 'Vulnerability'];

const TYPE_COLORS: Record<string, string> = {
  Person: 'bg-orange-500',
  Organization: 'bg-blue-500',
  Location: 'bg-green-500',
  ThreatActor: 'bg-red-500',
  Document: 'bg-gray-500',
  IPAddress: 'bg-cyan-500',
  Domain: 'bg-purple-500',
  Event: 'bg-yellow-500',
  Hash: 'bg-pink-500',
  Vulnerability: 'bg-rose-500',
};

export default function NetworkPage() {
  const { activeProject } = useProject();
  const [entities, setEntities] = useState<Entity[]>([]);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null);
  const [entityRelationships, setEntityRelationships] = useState<Relationship[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('All');
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<string | null>(null);

  const loadGraph = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await graphApi.full(activeProject.id);
      setGraphNodes(res.data.nodes || []);
      setGraphEdges(res.data.edges || []);
    } catch (e) {
      console.error('Failed to load graph', e);
    }
  }, [activeProject]);

  const loadEntities = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await entitiesApi.search(
        activeProject.id,
        searchQuery || undefined,
        typeFilter === 'All' ? undefined : typeFilter
      );
      setEntities(res.data);
    } catch (e) {
      console.error('Failed to load entities', e);
    }
  }, [activeProject, searchQuery, typeFilter]);

  useEffect(() => {
    loadGraph();
    loadEntities();
  }, [loadGraph, loadEntities]);

  async function selectEntity(entity: Entity) {
    setSelectedEntity(entity);
    setAiResult(null);
    try {
      const res = await entitiesApi.get(entity.id);
      if (res.data.relationships) {
        setEntityRelationships(res.data.relationships);
      }
      if (res.data.entity) {
        setSelectedEntity(res.data.entity);
      }
    } catch (e) {
      console.error('Failed to load entity details', e);
    }
  }

  function handleNodeClick(node: GraphNode) {
    selectEntity({ id: node.id, name: node.name, entity_type: node.entity_type });
  }

  async function sendChat() {
    if (!chatInput.trim() || !activeProject) return;
    const userMsg = chatInput.trim();
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setChatLoading(true);
    try {
      const res = await queryApi.rag(activeProject.id, userMsg);
      const answer = res.data.answer || res.data.response || JSON.stringify(res.data);
      setChatMessages(prev => [...prev, { role: 'assistant', content: answer }]);
    } catch {
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Error processing query.' }]);
    } finally {
      setChatLoading(false);
    }
  }

  async function generateAssessment() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      const res = await llmApi.query(
        [{ role: 'user', content: `Generate an intelligence assessment for entity "${selectedEntity.name}" (type: ${selectedEntity.entity_type}). Include analysis of significance, connections, and potential implications.` }],
        'entity_assessment'
      );
      setAiResult(res.data.response || res.data.content || JSON.stringify(res.data));
    } catch {
      setAiResult('Failed to generate assessment.');
    } finally {
      setAiLoading(false);
    }
  }

  async function gapAnalysis() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      const res = await llmApi.query(
        [{ role: 'user', content: `Perform a gap analysis for entity "${selectedEntity.name}" (type: ${selectedEntity.entity_type}). Identify missing information, intelligence gaps, and recommended collection priorities.` }],
        'gap_analysis'
      );
      setAiResult(res.data.response || res.data.content || JSON.stringify(res.data));
    } catch {
      setAiResult('Failed to perform gap analysis.');
    } finally {
      setAiLoading(false);
    }
  }

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-56 flex-1 p-8">
          <h2 className="text-2xl font-bold mb-4">Network Analysis</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p className="text-lg mb-2">No Project Selected</p>
            <p className="text-sm">Go to Projects and select one to begin analysis.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="ml-56 flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top bar */}
        <div className="flex-none px-4 py-2 border-b border-navy-600 bg-navy-800 flex items-center justify-between">
          <h2 className="text-lg font-bold">Network Analysis</h2>
          <span className="text-sm text-gray-400">{graphNodes.length} nodes, {graphEdges.length} edges</span>
        </div>

        {/* Main content area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left sidebar - Entity list */}
          <div className="w-64 flex-none bg-navy-800 border-r border-navy-600 flex flex-col overflow-hidden">
            <div className="p-3 border-b border-navy-600 space-y-2">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search entities..."
                className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue"
              />
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="w-full bg-navy-700 border border-navy-600 rounded px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue"
              >
                {ENTITY_TYPES.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="flex-1 overflow-y-auto">
              {entities.map((entity) => (
                <button
                  key={entity.id}
                  onClick={() => selectEntity(entity)}
                  className={`w-full text-left px-3 py-2 text-sm border-b border-navy-700 hover:bg-navy-700 transition-colors flex items-center gap-2 ${
                    selectedEntity?.id === entity.id ? 'bg-navy-700 text-accent-blue' : 'text-gray-300'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full flex-none ${TYPE_COLORS[entity.entity_type] || 'bg-gray-500'}`} />
                  <span className="truncate">{entity.name}</span>
                  <span className="text-xs text-gray-500 flex-none">{entity.entity_type}</span>
                </button>
              ))}
              {entities.length === 0 && (
                <p className="text-xs text-gray-500 p-3">No entities found.</p>
              )}
            </div>
          </div>

          {/* Center - Graph */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 relative">
              {graphNodes.length > 0 ? (
                <GraphVisualization
                  nodes={graphNodes}
                  edges={graphEdges}
                  onNodeClick={handleNodeClick}
                  selectedNodeId={selectedEntity?.id}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <p>No graph data. Ingest documents to populate the knowledge graph.</p>
                </div>
              )}
            </div>

            {/* Bottom chat panel */}
            <div className={`flex-none border-t border-navy-600 bg-navy-800 transition-all ${bottomPanelOpen ? 'h-48' : 'h-8'}`}>
              <button
                onClick={() => setBottomPanelOpen(!bottomPanelOpen)}
                className="w-full h-8 flex items-center justify-center text-xs text-gray-400 hover:text-gray-200 border-b border-navy-600"
              >
                {bottomPanelOpen ? 'Hide' : 'Show'} Graph RAG Chat
              </button>
              {bottomPanelOpen && (
                <div className="flex flex-col h-40">
                  <div className="flex-1 overflow-y-auto p-2 space-y-2">
                    {chatMessages.map((msg, i) => (
                      <div key={i} className={`text-xs p-2 rounded ${msg.role === 'user' ? 'bg-navy-700 text-gray-200' : 'bg-navy-600 text-gray-300'}`}>
                        <span className="font-bold text-accent-blue">{msg.role === 'user' ? 'You' : 'AI'}:</span> {msg.content}
                      </div>
                    ))}
                    {chatLoading && <div className="text-xs text-gray-400 p-2">Thinking...</div>}
                  </div>
                  <div className="flex gap-2 p-2 border-t border-navy-600">
                    <input
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && sendChat()}
                      placeholder="Ask about the knowledge graph..."
                      className="flex-1 bg-navy-700 border border-navy-600 rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-blue"
                    />
                    <button
                      onClick={sendChat}
                      disabled={chatLoading}
                      className="bg-accent-blue hover:bg-blue-600 text-white px-3 py-1 rounded text-xs disabled:opacity-50"
                    >
                      Send
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right sidebar - Detail panel */}
          <div className="w-80 flex-none bg-navy-800 border-l border-navy-600 overflow-y-auto">
            {selectedEntity ? (
              <div className="p-4 space-y-4">
                <div>
                  <h3 className="font-bold text-lg">{selectedEntity.name}</h3>
                  <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded ${TYPE_COLORS[selectedEntity.entity_type] || 'bg-gray-500'} text-white`}>
                    {selectedEntity.entity_type}
                  </span>
                </div>

                {selectedEntity.properties && Object.keys(selectedEntity.properties).length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">Properties</h4>
                    <div className="space-y-1">
                      {Object.entries(selectedEntity.properties).map(([key, value]) => (
                        <div key={key} className="text-xs">
                          <span className="text-gray-500">{key}:</span>{' '}
                          <span className="text-gray-300">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {entityRelationships.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">Relationships ({entityRelationships.length})</h4>
                    <div className="space-y-1">
                      {entityRelationships.map((rel, i) => (
                        <div key={i} className="text-xs bg-navy-700 rounded p-2">
                          <span className="text-accent-blue">{rel.rel_type}</span>
                          {rel.confidence !== undefined && (
                            <span className="text-gray-500 ml-2">({(rel.confidence * 100).toFixed(0)}%)</span>
                          )}
                          <div className="text-gray-400 mt-0.5">
                            {rel.source_name || rel.source_id} &rarr; {rel.target_name || rel.target_id}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-gray-400">AI Actions</h4>
                  <button
                    onClick={generateAssessment}
                    disabled={aiLoading}
                    className="w-full bg-accent-blue hover:bg-blue-600 text-white px-3 py-2 rounded text-xs font-medium disabled:opacity-50"
                  >
                    {aiLoading ? 'Generating...' : 'Generate Assessment'}
                  </button>
                  <button
                    onClick={gapAnalysis}
                    disabled={aiLoading}
                    className="w-full bg-navy-600 hover:bg-navy-700 text-gray-200 px-3 py-2 rounded text-xs font-medium disabled:opacity-50 border border-navy-600"
                  >
                    Gap Analysis
                  </button>
                </div>

                {aiResult && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">AI Result</h4>
                    <div className="bg-navy-700 rounded p-3 text-xs text-gray-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {aiResult}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4 text-center text-gray-500 text-sm mt-8">
                <p>Select an entity from the list or click a node in the graph to see details.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
