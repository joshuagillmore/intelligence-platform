'use client';
import { useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import Sidebar from '@/components/Sidebar';
import LoadingSpinner from '@/components/LoadingSpinner';
import { useProject } from '@/lib/ProjectContext';
import { geoApi, queryApi, entitiesApi } from '@/lib/api';

const GeoMap = dynamic(() => import('@/components/GeoMap'), { ssr: false });

interface GeoLocation {
  id: string;
  name: string;
  latitude?: number | null;
  longitude?: number | null;
  lat?: number | null;
  lng?: number | null;
  geocoded?: boolean;
  connections?: number;
  entity_type?: string;
  properties?: Record<string, unknown>;
}

interface LocationRelationship {
  source_name?: string;
  target_name?: string;
  source_id: string;
  target_id: string;
  rel_type: string;
}

/* ── color tokens (inline styles for custom palette) ── */
const C = {
  primary: '#adc6ff',
  tertiary: '#ff5451',
  surface: '#0e1321',
  sidebarBg: '#161b2a',
  elevated: '#252a39',
  border: '#313849',
  textMuted: '#6b7a99',
  textDim: '#8a95ab',
  green: '#34d399',
};

export default function GeoPage() {
  const { activeProject } = useProject();
  const [locations, setLocations] = useState<GeoLocation[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedLocation, setSelectedLocation] = useState<GeoLocation | null>(null);
  const [selectedRels, setSelectedRels] = useState<LocationRelationship[]>([]);
  const [relsLoading, setRelsLoading] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [queryResult, setQueryResult] = useState<string | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [geoEdges, setGeoEdges] = useState<Array<{
    source_coords?: number[]; target_coords?: number[];
    source_name: string; target_name: string;
    weight: number; shared_entities: string[];
  }>>([]);

  /* ── layer control state ── */
  const [layers, setLayers] = useState({
    threatActors: true,
    infrastructure: true,
    targets: false,
    relationships: true,
    heatMap: false,
  });
  const toggleLayer = (key: keyof typeof layers) =>
    setLayers(prev => ({ ...prev, [key]: !prev[key] }));

  /* ── chat overlay state ── */
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<{ role: 'user' | 'ai'; text: string }[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const getLat = (loc: GeoLocation) => loc.latitude ?? loc.lat ?? (loc.properties?.latitude as number | undefined);
  const getLng = (loc: GeoLocation) => loc.longitude ?? loc.lng ?? (loc.properties?.longitude as number | undefined);
  const isGeocoded = (loc: GeoLocation) => loc.geocoded ?? !!(getLat(loc) && getLng(loc));

  const loadLocations = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    try {
      const res = await geoApi.locations(activeProject.id);
      const data = res.data;
      if (Array.isArray(data)) {
        setLocations(data);
      } else if (data && data.locations) {
        setLocations(data.locations);
        if (data.edges) setGeoEdges(data.edges);
      } else {
        setLocations([]);
      }
    } catch {
      try {
        const res = await entitiesApi.search(activeProject.id, undefined, 'Location');
        const entities = res.data || [];
        setLocations(entities.map((e: { id: string; name: string; properties?: Record<string, unknown> }) => ({
          id: e.id,
          name: e.name,
          latitude: e.properties?.latitude as number | undefined,
          longitude: e.properties?.longitude as number | undefined,
          geocoded: !!(e.properties?.latitude && e.properties?.longitude),
          connections: 0,
          properties: e.properties,
        })));
      } catch {
        setLocations([]);
      }
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

  async function handleLocationClick(loc: GeoLocation) {
    if (selectedLocation?.id === loc.id) {
      setSelectedLocation(null);
      setSelectedRels([]);
      return;
    }
    setSelectedLocation(loc);
    setSelectedRels([]);
    setRelsLoading(true);
    try {
      const res = await entitiesApi.get(loc.id);
      setSelectedRels(res.data?.relationships || []);
    } catch {
      setSelectedRels([]);
    } finally {
      setRelsLoading(false);
    }
  }

  async function askGeoQuery() {
    if (!queryInput.trim() || !activeProject) return;
    setQueryLoading(true);
    setQueryResult(null);
    try {
      const res = await queryApi.rag(activeProject.id, queryInput);
      setQueryResult(res.data.answer || res.data.response || JSON.stringify(res.data));
    } catch {
      setQueryResult('Failed to process query.');
    } finally {
      setQueryLoading(false);
    }
  }

  async function sendChatMessage() {
    if (!chatInput.trim() || !activeProject) return;
    const userMsg = chatInput.trim();
    setChatMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setChatInput('');
    setChatLoading(true);
    try {
      const res = await queryApi.rag(activeProject.id, userMsg);
      const answer = res.data.answer || res.data.response || JSON.stringify(res.data);
      setChatMessages(prev => [...prev, { role: 'ai', text: answer }]);
    } catch {
      setChatMessages(prev => [...prev, { role: 'ai', text: 'Failed to process query.' }]);
    } finally {
      setChatLoading(false);
    }
  }

  const totalConnections = locations.reduce((sum, l) => sum + (l.connections || 0), 0);
  const geocodedCount = locations.filter(l => isGeocoded(l)).length;

  /* ── derive related locations from relationships ── */
  const relatedLocations = selectedRels.reduce<{ name: string; count: number }[]>((acc, rel) => {
    const name =
      rel.source_name === selectedLocation?.name
        ? (rel.target_name || rel.target_id)
        : (rel.source_name || rel.source_id);
    const existing = acc.find(r => r.name === name);
    if (existing) existing.count++;
    else acc.push({ name, count: 1 });
    return acc;
  }, []);

  /* ── entity timeline data (real temporal data) ── */
  const [entityTimeline, setEntityTimeline] = useState<{
    events: Array<{ date: string; type: string; label: string }>;
    buckets: Array<{ date: string; count: number }>;
    date_range: { start: string; end: string } | null;
  }>({ events: [], buckets: [], date_range: null });
  const [timelineLoading, setTimelineLoading] = useState(false);

  /* ── temporal window filter state ── */
  const [temporalStart, setTemporalStart] = useState('');
  const [temporalEnd, setTemporalEnd] = useState('');

  // Load entity timeline when a location is selected
  useEffect(() => {
    if (!selectedLocation?.id || !activeProject) {
      setEntityTimeline({ events: [], buckets: [], date_range: null });
      return;
    }
    setTimelineLoading(true);
    geoApi.entityTimeline(selectedLocation.id, activeProject.id)
      .then(({ data }) => {
        setEntityTimeline({
          events: data.events || [],
          buckets: data.buckets || [],
          date_range: data.date_range || null,
        });
        if (data.date_range) {
          setTemporalStart(data.date_range.start?.slice(0, 10) || '');
          setTemporalEnd(data.date_range.end?.slice(0, 10) || '');
        }
      })
      .catch(() => setEntityTimeline({ events: [], buckets: [], date_range: null }))
      .finally(() => setTimelineLoading(false));
  }, [selectedLocation?.id, activeProject]);

  const trafficBars = entityTimeline.buckets.length > 0
    ? entityTimeline.buckets.map(b => b.count)
    : [0];

  if (!activeProject) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="md:ml-56 flex-1 p-8 pt-14 md:pt-8">
          <h2 className="text-2xl font-bold mb-4">Geo-Intelligence</h2>
          <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
            <p>Select a project first.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 flex flex-col md:flex-row h-screen overflow-hidden pt-14 md:pt-0" style={{ background: C.surface }}>
        {/* ═══════════════ MAP AREA (75%) ═══════════════ */}
        <div className="relative w-full md:w-[75%] min-h-[50vh] md:min-h-0 md:h-full">
          {/* Map */}
          <div className="w-full h-full">
            {loading ? (
              <div className="w-full h-full flex items-center justify-center">
                <LoadingSpinner size="lg" />
              </div>
            ) : (
              <GeoMap
                locations={locations}
                connectionLines={geoEdges
                  .filter(e => e.source_coords && e.target_coords)
                  .map(e => ({
                    from: [e.source_coords![0], e.source_coords![1]] as [number, number],
                    to: [e.target_coords![0], e.target_coords![1]] as [number, number],
                    names: `${e.source_name} ↔ ${e.target_name}`,
                    weight: e.weight,
                    shared_entities: e.shared_entities,
                  }))}
                onLocationClick={handleLocationClick}
                selectedLocationId={selectedLocation?.id}
              />
            )}
          </div>

          {/* ── Layer Control (floating top-left) ── */}
          <div
            className="absolute top-4 left-4 rounded-lg p-4 w-52 shadow-xl hidden md:block"
            style={{ background: C.elevated, border: `1px solid ${C.border}` }}
          >
            <h4 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: C.textDim }}>
              Layer Control
            </h4>
            {([
              ['threatActors', 'Threat Actors'],
              ['infrastructure', 'Infrastructure'],
              ['targets', 'Targets'],
              ['relationships', 'Relationships'],
              ['heatMap', 'Heat Map'],
            ] as const).map(([key, label]) => (
              <label key={key} className="flex items-center justify-between mb-2 cursor-pointer text-sm text-gray-300">
                <span>{label}</span>
                <button
                  onClick={() => toggleLayer(key as keyof typeof layers)}
                  className="relative w-9 h-5 rounded-full transition-colors"
                  style={{
                    background: layers[key as keyof typeof layers] ? C.primary : C.border,
                  }}
                >
                  <span
                    className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform"
                    style={{
                      left: layers[key as keyof typeof layers] ? '18px' : '2px',
                    }}
                  />
                </button>
              </label>
            ))}
          </div>

          {/* ── Temporal Window (below layer control) ── */}
          <div
            className="absolute top-64 left-4 rounded-lg p-4 w-52 shadow-xl hidden md:block"
            style={{ background: C.elevated, border: `1px solid ${C.border}` }}
          >
            <h4 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: C.textDim }}>
              Temporal Window
            </h4>
            <div className="space-y-2">
              <div>
                <label className="text-[10px] uppercase" style={{ color: C.textMuted }}>From</label>
                <input
                  type="date"
                  value={temporalStart}
                  onChange={e => setTemporalStart(e.target.value)}
                  className="w-full rounded px-2 py-1 text-xs focus:outline-none"
                  style={{ background: C.surface, border: `1px solid ${C.border}`, color: '#e5e7eb' }}
                />
              </div>
              <div>
                <label className="text-[10px] uppercase" style={{ color: C.textMuted }}>To</label>
                <input
                  type="date"
                  value={temporalEnd}
                  onChange={e => setTemporalEnd(e.target.value)}
                  className="w-full rounded px-2 py-1 text-xs focus:outline-none"
                  style={{ background: C.surface, border: `1px solid ${C.border}`, color: '#e5e7eb' }}
                />
              </div>
              {entityTimeline.date_range && (
                <div className="text-[10px]" style={{ color: C.textMuted }}>
                  Data: {entityTimeline.date_range.start?.slice(0, 10)} — {entityTimeline.date_range.end?.slice(0, 10)}
                </div>
              )}
            </div>
          </div>

          {/* ── Stats overlay (top-right of map) ── */}
          <div className="absolute top-4 right-4 flex flex-wrap gap-2 text-xs">
            <span className="px-3 py-1.5 rounded-md" style={{ background: C.elevated, border: `1px solid ${C.border}`, color: C.textDim }}>
              {locations.length} Locations
            </span>
            <span className="px-3 py-1.5 rounded-md" style={{ background: C.elevated, border: `1px solid ${C.border}`, color: C.primary }}>
              {geocodedCount} Geocoded
            </span>
            <span className="px-3 py-1.5 rounded-md" style={{ background: C.elevated, border: `1px solid ${C.border}`, color: C.textDim }}>
              {totalConnections} Connections
            </span>
          </div>

          {/* ═══════════════ CHAT OVERLAY (bottom of map) ═══════════════ */}
          <div
            className="absolute bottom-4 left-4 right-4 rounded-lg shadow-2xl flex flex-col overflow-hidden"
            style={{
              background: C.elevated,
              border: `1px solid ${C.border}`,
              maxHeight: chatOpen ? '320px' : '44px',
              transition: 'max-height 0.25s ease',
            }}
          >
            {/* Chat header */}
            <button
              onClick={() => setChatOpen(o => !o)}
              className="flex items-center gap-2 px-4 py-2.5 w-full text-left shrink-0"
              style={{ borderBottom: chatOpen ? `1px solid ${C.border}` : 'none' }}
            >
              {/* AI icon */}
              <span
                className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                style={{ background: C.primary, color: C.surface }}
              >
                AI
              </span>
              <span className="text-sm font-medium text-gray-200 flex-1">Aegis Intelligence Assistant</span>
              <svg
                className="w-4 h-4 text-gray-400 transition-transform"
                style={{ transform: chatOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
              </svg>
            </button>

            {chatOpen && (
              <>
                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0" style={{ maxHeight: '220px' }}>
                  {chatMessages.length === 0 && (
                    <p className="text-xs" style={{ color: C.textMuted }}>
                      Ask questions about geographic intelligence, threat vectors, or entity relationships.
                    </p>
                  )}
                  {chatMessages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div
                        className="max-w-[80%] rounded-lg px-3 py-2 text-xs"
                        style={{
                          background: msg.role === 'user' ? C.primary : C.surface,
                          color: msg.role === 'user' ? C.surface : '#d1d5db',
                        }}
                      >
                        <pre className="whitespace-pre-wrap font-sans">{msg.text}</pre>
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="flex justify-start">
                      <div className="rounded-lg px-3 py-2 text-xs" style={{ background: C.surface, color: C.textDim }}>
                        Thinking...
                      </div>
                    </div>
                  )}
                </div>

                {/* Input */}
                <div className="px-4 py-3 flex gap-2 shrink-0" style={{ borderTop: `1px solid ${C.border}` }}>
                  <input
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && sendChatMessage()}
                    placeholder="Ask Aegis..."
                    className="flex-1 rounded px-3 py-1.5 text-sm focus:outline-none"
                    style={{ background: C.surface, border: `1px solid ${C.border}`, color: '#e5e7eb' }}
                  />
                  <button
                    onClick={sendChatMessage}
                    disabled={chatLoading || !chatInput.trim()}
                    className="px-4 py-1.5 rounded text-sm font-medium disabled:opacity-40 transition-opacity"
                    style={{ background: C.primary, color: C.surface }}
                  >
                    Send
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {/* ═══════════════ RIGHT SIDEBAR (25%) ═══════════════ */}
        <div
          className="flex flex-col w-full md:w-[25%] h-auto md:h-full overflow-y-auto pb-16 md:pb-0 border-t md:border-t-0 md:border-l"
          style={{ background: C.sidebarBg, borderColor: C.border }}
        >
          <div className="p-5 flex flex-col gap-5 flex-1">
            {selectedLocation ? (
              <>
                {/* ── Entity Profile header ── */}
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: C.tertiary }}>
                    Entity Profile
                  </span>
                  <h2 className="text-xl font-bold text-white mt-1">{selectedLocation.name}</h2>
                  {getLat(selectedLocation) != null && (
                    <p className="text-xs mt-0.5" style={{ color: C.textMuted }}>
                      {Number(getLat(selectedLocation)).toFixed(4)}, {Number(getLng(selectedLocation)).toFixed(4)}
                    </p>
                  )}
                  {/* ACTIVE badge */}
                  <span
                    className="inline-block mt-2 text-[10px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full border"
                    style={{ color: C.green, borderColor: C.green }}
                  >
                    Active
                  </span>
                </div>

                {/* ── Property cards grid ── */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-lg p-3" style={{ background: C.elevated }}>
                    <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: C.textMuted }}>Class</div>
                    <div className="text-sm font-medium text-white">{selectedLocation.entity_type || 'Location'}</div>
                  </div>
                  <div className="rounded-lg p-3" style={{ background: C.elevated }}>
                    <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: C.textMuted }}>Origin</div>
                    <div className="text-sm font-medium text-white">
                      {(selectedLocation.properties?.region as string) || (selectedLocation.properties?.country as string) || 'N/A'}
                    </div>
                  </div>
                  <div className="rounded-lg p-3" style={{ background: C.elevated }}>
                    <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: C.textMuted }}>Connections</div>
                    <div className="text-sm font-medium" style={{ color: C.primary }}>{selectedRels.length}</div>
                  </div>
                  <div className="rounded-lg p-3" style={{ background: C.elevated }}>
                    <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: C.textMuted }}>Status</div>
                    <div className="text-sm font-medium" style={{ color: C.green }}>Geocoded</div>
                  </div>
                </div>

                {/* ── Geographic Clusters ── */}
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: C.textDim }}>
                    Geographic Clusters
                  </h4>
                  <div className="space-y-1">
                    {relsLoading ? (
                      <p className="text-xs" style={{ color: C.textMuted }}>Loading relationships...</p>
                    ) : relatedLocations.length === 0 ? (
                      <p className="text-xs" style={{ color: C.textMuted }}>No clusters found.</p>
                    ) : (
                      relatedLocations.map((rel, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm cursor-default"
                          style={{ background: C.elevated }}
                        >
                          {/* dot indicator */}
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: C.primary }} />
                          <span className="flex-1 text-gray-200 truncate">{rel.name}</span>
                          <span className="text-[10px] font-mono" style={{ color: C.textMuted }}>{rel.count}</span>
                          {/* chevron_right */}
                          <svg className="w-4 h-4" style={{ color: C.textMuted }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* ── Relationships (preserved) ── */}
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: C.textDim }}>
                    Relationships
                  </h4>
                  <div className="space-y-1">
                    {relsLoading ? (
                      <p className="text-xs" style={{ color: C.textMuted }}>Loading relationships...</p>
                    ) : selectedRels.length === 0 ? (
                      <p className="text-xs" style={{ color: C.textMuted }}>No relationships found.</p>
                    ) : (
                      selectedRels.map((rel, i) => (
                        <div key={i} className="text-xs rounded-md px-3 py-2" style={{ background: C.elevated }}>
                          <span style={{ color: C.primary }}>{rel.rel_type}</span>
                          <span style={{ color: C.textMuted }}> &rarr; </span>
                          <span className="text-gray-200">
                            {rel.source_name === selectedLocation.name
                              ? (rel.target_name || rel.target_id)
                              : (rel.source_name || rel.source_id)}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* ── Intelligence Ops ── */}
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: C.textDim }}>
                    Intelligence Ops
                  </h4>
                  <div className="flex flex-col gap-2">
                    <button
                      className="w-full rounded-md py-2 text-sm font-medium transition-opacity hover:opacity-90"
                      style={{ background: C.primary, color: C.surface }}
                    >
                      Gap Analysis
                    </button>
                    <button
                      className="w-full rounded-md py-2 text-sm font-medium transition-opacity hover:opacity-90 border"
                      style={{ background: 'transparent', color: C.primary, borderColor: C.primary }}
                    >
                      Generate Assessment
                    </button>
                    <button
                      className="w-full rounded-md py-2 text-sm font-medium transition-opacity hover:opacity-90 border"
                      style={{ background: 'transparent', color: C.primary, borderColor: C.primary }}
                    >
                      Hypothesis Generation
                    </button>
                  </div>
                </div>

                {/* ── Activity Timeline ── */}
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: C.textDim }}>
                    {timelineLoading ? 'Loading Timeline...' : `Activity Timeline (${entityTimeline.events.length} events)`}
                  </h4>

                  {/* Events list */}
                  {entityTimeline.events.length > 0 && (
                    <div className="space-y-1 mb-3 max-h-24 overflow-y-auto">
                      {entityTimeline.events.slice(0, 8).map((evt, i) => (
                        <div key={i} className="text-[10px] flex gap-2" style={{ color: C.textMuted }}>
                          <span className="font-mono shrink-0">{evt.date?.slice(0, 10) || '?'}</span>
                          <span className="truncate text-gray-300">{evt.label}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Sparkline bars */}
                  <div className="flex items-end gap-px h-10">
                    {trafficBars.map((v, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-sm"
                        style={{
                          height: `${(v / 9) * 100}%`,
                          background: C.primary,
                          opacity: 0.6 + (v / 9) * 0.4,
                        }}
                      />
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
                <div
                  className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
                  style={{ background: C.elevated }}
                >
                  <svg className="w-7 h-7" style={{ color: C.textMuted }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-400 mb-1">No Entity Selected</p>
                <p className="text-xs" style={{ color: C.textMuted }}>Click a location on the map to view its profile</p>
              </div>
            )}

            {/* ── RAG Query (always visible at bottom) ── */}
            <div className="mt-auto pt-4" style={{ borderTop: `1px solid ${C.border}` }}>
              <h4 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: C.textDim }}>
                Geographic Query
              </h4>
              <div className="flex gap-2">
                <input
                  value={queryInput}
                  onChange={e => setQueryInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && askGeoQuery()}
                  placeholder="Ask about locations..."
                  className="flex-1 rounded px-3 py-1.5 text-sm focus:outline-none"
                  style={{ background: C.elevated, border: `1px solid ${C.border}`, color: '#e5e7eb' }}
                />
                <button
                  onClick={askGeoQuery}
                  disabled={queryLoading || !queryInput.trim()}
                  className="px-3 py-1.5 rounded text-sm font-medium disabled:opacity-40 transition-opacity"
                  style={{ background: C.primary, color: C.surface }}
                >
                  {queryLoading ? '...' : 'Ask'}
                </button>
              </div>
              {queryResult && (
                <div className="mt-3 text-xs max-h-48 overflow-y-auto rounded-md p-3" style={{ background: C.elevated, color: '#d1d5db' }}>
                  <pre className="whitespace-pre-wrap">{queryResult}</pre>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
