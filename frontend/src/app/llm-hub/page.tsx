'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { llmApi, personasApi } from '@/lib/api';
import { humanize } from '@/lib/format';
import Markdown from '@/components/Markdown';
import { useNotifications } from '@/components/NotificationProvider';

interface Skill {
  name: string;
  description?: string;
  active?: boolean;
  system_prompt?: string;
  temperature?: number;
  max_tokens?: number;
}

interface Persona {
  id: string;
  name: string;
  description: string;
  skills: string[];
  temperature: number;
  active: boolean;
}

export default function LlmHubPage() {
  const { addNotification } = useNotifications();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [activePersona, setActivePersona] = useState<string>('');
  const [prompt, setPrompt] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editablePrompt, setEditablePrompt] = useState('');
  const [temperature, setTemperature] = useState(0.3);
  const [maxTokens, setMaxTokens] = useState(2048);

  // Create persona modal
  const [showCreatePersona, setShowCreatePersona] = useState(false);
  const [newPersona, setNewPersona] = useState({ id: '', name: '', description: '', skills: [] as string[], temperature: 0.3 });

  const loadSkills = useCallback(async () => {
    try {
      const res = await llmApi.skills();
      const data = res.data;
      let arr: Skill[] = [];
      if (Array.isArray(data)) {
        arr = data;
      } else if (data && Array.isArray(data.skills)) {
        arr = data.skills as Skill[];
      } else if (typeof data === 'object') {
        arr = Object.entries(data).map(([name, val]) => ({
          name,
          ...(typeof val === 'object' && val !== null ? val as Record<string, unknown> : {}),
        })) as Skill[];
      }
      setSkills(arr);
    } catch (e) {
      console.error('Failed to load skills', e);
      addNotification({
        title: 'Failed to load skills',
        message: 'Could not load analytical skills from the backend. Please try again.',
        type: 'error',
      });
    }
  }, [addNotification]);

  const loadPersonas = useCallback(async () => {
    try {
      const res = await personasApi.list();
      setPersonas(res.data.personas || []);
      setActivePersona(res.data.active_persona || '');
    } catch (e) {
      console.error('Failed to load personas', e);
      addNotification({
        title: 'Failed to load personas',
        message: 'Could not load personas from the backend. Please try again.',
        type: 'error',
      });
    }
  }, [addNotification]);

  useEffect(() => {
    loadSkills();
    loadPersonas();
  }, [loadSkills, loadPersonas]);

  useEffect(() => {
    if (!selectedSkill) return;
    let saved: { system_prompt?: string; temperature?: number; max_tokens?: number } | null = null;
    try {
      const raw = typeof window !== 'undefined' ? localStorage.getItem(`skillcfg:${selectedSkill.name}`) : null;
      if (raw) saved = JSON.parse(raw);
    } catch { /* ignore malformed cache */ }
    setEditablePrompt(saved?.system_prompt ?? selectedSkill.system_prompt ?? '');
    setTemperature(saved?.temperature ?? selectedSkill.temperature ?? 0.3);
    setMaxTokens(saved?.max_tokens ?? selectedSkill.max_tokens ?? 2048);
  }, [selectedSkill]);

  // Persist per-skill config edits so they survive reload
  useEffect(() => {
    if (!selectedSkill || typeof window === 'undefined') return;
    localStorage.setItem(
      `skillcfg:${selectedSkill.name}`,
      JSON.stringify({ system_prompt: editablePrompt, temperature, max_tokens: maxTokens }),
    );
  }, [selectedSkill, editablePrompt, temperature, maxTokens]);

  async function testSkill() {
    if (!prompt.trim()) return;
    setLoading(true);
    setResult(null);
    setResultError(null);
    try {
      const isCustom = !!selectedSkill && !builtInSkills.includes(selectedSkill.name);
      const overrides: { system_prompt?: string; temperature?: number; max_tokens?: number } = {
        temperature,
        max_tokens: maxTokens,
      };
      if (isCustom && editablePrompt.trim()) overrides.system_prompt = editablePrompt;
      const res = await llmApi.query(
        [{ role: 'user', content: prompt.trim() }],
        selectedSkill?.name || undefined,
        overrides
      );
      setResult(res.data.content || res.data.response || JSON.stringify(res.data, null, 2));
    } catch {
      setResultError('Query failed. Check that the LLM provider is configured and reachable, then try again.');
    } finally {
      setLoading(false);
    }
  }

  async function handleActivatePersona(personaId: string) {
    try {
      await personasApi.activate(personaId);
      await loadPersonas();
    } catch (e) {
      console.error('Failed to activate persona', e);
    }
  }

  async function handleCreatePersona() {
    if (!newPersona.id || !newPersona.name) return;
    try {
      await personasApi.create(newPersona);
      setShowCreatePersona(false);
      setNewPersona({ id: '', name: '', description: '', skills: [], temperature: 0.3 });
      await loadPersonas();
    } catch (e) {
      console.error('Failed to create persona', e);
    }
  }

  async function handleDeletePersona(personaId: string) {
    const name = personas.find(p => String(p.id) === String(personaId))?.name || 'this persona';
    if (!confirm(`Delete persona "${name}"? This can't be undone.`)) return;
    try {
      await personasApi.delete(personaId);
      await loadPersonas();
    } catch (e) {
      console.error('Failed to delete persona', e);
    }
  }

  const builtInSkills = ['entity_extraction', 'source_evaluation', 'hypothesis_generation', 'threat_assessment', 'gap_analysis', 'report_writing', 'collection_planning'];

  function toggleNewPersonaSkill(skillName: string) {
    setNewPersona(prev => ({
      ...prev,
      skills: prev.skills.includes(skillName)
        ? prev.skills.filter(s => s !== skillName)
        : [...prev.skills, skillName],
    }));
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-8 flex gap-6 h-screen overflow-hidden pt-16 md:pt-8">

        {/* Left Column: Analytical Skills */}
        <div className="w-72 flex-shrink-0 flex flex-col overflow-hidden">
          <h3 className="text-lg font-semibold mb-4">Analytical Skills</h3>
          <div className="space-y-2 overflow-y-auto flex-1 pr-1">
            {skills.map((skill) => (
              <div
                key={skill.name}
                className={`bg-navy-800 border rounded-lg p-3 cursor-pointer transition-colors ${
                  selectedSkill?.name === skill.name ? 'border-accent-blue bg-navy-700' : 'border-navy-600 hover:border-navy-500'
                }`}
                onClick={() => setSelectedSkill(skill)}
              >
                <div className="flex items-center justify-between">
                  <h4 className="font-medium text-sm truncate">{humanize(skill.name)}</h4>
                  <span className={`text-xs px-2 py-0.5 rounded flex-shrink-0 ml-2 ${
                    skill.active !== false ? 'bg-green-900/30 text-green-400' : 'bg-gray-900/30 text-gray-400'
                  }`}>
                    {skill.active !== false ? 'On' : 'Off'}
                  </span>
                </div>
                {skill.description && (
                  <p className="text-xs text-gray-400 mt-1 line-clamp-2">{skill.description}</p>
                )}
              </div>
            ))}
            {skills.length === 0 && (
              <p className="text-gray-500 text-sm">No skills available.</p>
            )}
          </div>
        </div>

        {/* Center Column: Skill Configuration */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <h3 className="text-lg font-semibold mb-4">Skill Configuration</h3>
          {selectedSkill ? (
            <div className="flex-1 overflow-y-auto pr-1 space-y-4">
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
                <h4 className="text-base font-semibold mb-1">{humanize(selectedSkill.name)}</h4>
                {selectedSkill.description && (
                  <p className="text-sm text-gray-400 mb-4">{selectedSkill.description}</p>
                )}

                {/* System Prompt */}
                <div className="mb-4">
                  <label className="text-xs text-gray-400 block mb-1">System Prompt</label>
                  {builtInSkills.includes(selectedSkill.name) ? (
                    <div className="bg-navy-900 border border-navy-700 rounded p-3 text-xs text-gray-400 font-mono max-h-32 overflow-y-auto whitespace-pre-wrap">
                      {selectedSkill.system_prompt || 'Built-in system prompt (read-only)'}
                    </div>
                  ) : (
                    <textarea
                      value={editablePrompt}
                      onChange={(e) => setEditablePrompt(e.target.value)}
                      className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-xs font-mono h-28 focus:outline-none focus:border-accent-blue resize-none"
                    />
                  )}
                </div>

                {/* Temperature */}
                <div className="mb-4">
                  <label className="text-xs text-gray-400 block mb-1">Temperature: {temperature.toFixed(2)}</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="w-full accent-accent-blue"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-0.5">
                    <span>Precise (0)</span>
                    <span>Creative (1)</span>
                  </div>
                </div>

                {/* Max Tokens */}
                <div className="mb-4">
                  <label className="text-xs text-gray-400 block mb-1">Max Tokens</label>
                  <input
                    type="number"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(parseInt(e.target.value) || 2048)}
                    min={128}
                    max={16384}
                    className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  />
                </div>
              </div>

              {/* Test Skill */}
              <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
                <h4 className="text-sm font-semibold mb-3">Test Skill</h4>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Enter your test prompt..."
                  className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-24 focus:outline-none focus:border-accent-blue resize-none mb-3"
                />
                <button
                  onClick={testSkill}
                  disabled={loading || !prompt.trim()}
                  className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  {loading ? 'Querying...' : 'Test Skill'}
                </button>
                {resultError && (
                  <div className="mt-3 rounded border border-red-600/40 bg-red-950/30 p-3 text-xs text-red-300 flex items-start gap-2" role="alert">
                    <span className="material-symbols-outlined text-red-400 text-sm">error</span>
                    <span>{resultError}</span>
                  </div>
                )}
                {result && (
                  <div className="mt-3 bg-navy-700 rounded p-3 max-h-48 overflow-y-auto">
                    <Markdown content={result} className="text-xs" />
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-gray-500 text-sm">Select a skill from the left panel to configure it.</p>
            </div>
          )}
        </div>

        {/* Right Column: LLM Personas */}
        <div className="w-72 flex-shrink-0 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">LLM Personas</h3>
            <button
              onClick={() => setShowCreatePersona(true)}
              className="text-xs bg-accent-blue hover:bg-blue-600 text-white px-3 py-1.5 rounded transition-colors"
            >
              + Create
            </button>
          </div>
          <div className="space-y-2 overflow-y-auto flex-1 pr-1">
            {personas.map((persona) => (
              <div
                key={persona.id}
                className={`bg-navy-800 border rounded-lg p-3 transition-colors ${
                  persona.id === activePersona
                    ? 'border-accent-blue ring-1 ring-accent-blue/30'
                    : 'border-navy-600'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <h4 className="font-medium text-sm truncate">{persona.name}</h4>
                  {persona.id === activePersona && (
                    <span className="text-xs bg-accent-blue/20 text-accent-blue px-2 py-0.5 rounded flex-shrink-0 ml-1">Active</span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mb-2 line-clamp-2">{persona.description}</p>

                {/* Skill badges */}
                <div className="flex flex-wrap gap-1 mb-2">
                  {persona.skills.map(s => (
                    <span key={s} className="text-[10px] bg-navy-700 text-gray-400 px-1.5 py-0.5 rounded">
                      {humanize(s)}
                    </span>
                  ))}
                </div>

                <div className="flex gap-2">
                  {persona.id !== activePersona && (
                    <button
                      onClick={() => handleActivatePersona(persona.id)}
                      className="text-xs text-accent-blue hover:text-blue-400 transition-colors"
                    >
                      Activate
                    </button>
                  )}
                  {!['osint_collector', 'cyber_analyst', 'allsource', 'report_writer'].includes(persona.id) && (
                    <button
                      onClick={() => handleDeletePersona(persona.id)}
                      className="text-xs text-red-400 hover:text-red-300 transition-colors"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ))}
            {personas.length === 0 && (
              <p className="text-gray-500 text-sm">No personas configured.</p>
            )}
          </div>
        </div>

        {/* Create Persona Modal */}
        {showCreatePersona && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setShowCreatePersona(false)}>
            <div className="bg-navy-800 border border-navy-600 rounded-lg p-6 w-[480px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
              <h3 className="text-lg font-semibold mb-4">Create Persona</h3>

              <div className="space-y-3">
                <div>
                  <label className="text-xs text-gray-400 block mb-1">ID (lowercase, no spaces)</label>
                  <input
                    value={newPersona.id}
                    onChange={e => setNewPersona(p => ({ ...p, id: e.target.value.toLowerCase().replace(/\s+/g, '_') }))}
                    className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Name</label>
                  <input
                    value={newPersona.name}
                    onChange={e => setNewPersona(p => ({ ...p, name: e.target.value }))}
                    className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Description</label>
                  <textarea
                    value={newPersona.description}
                    onChange={e => setNewPersona(p => ({ ...p, description: e.target.value }))}
                    className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-20 focus:outline-none focus:border-accent-blue resize-none"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Skills</label>
                  <div className="flex flex-wrap gap-2">
                    {skills.map(s => (
                      <button
                        key={s.name}
                        onClick={() => toggleNewPersonaSkill(s.name)}
                        className={`text-xs px-2 py-1 rounded border transition-colors ${
                          newPersona.skills.includes(s.name)
                            ? 'bg-accent-blue/20 border-accent-blue text-accent-blue'
                            : 'bg-navy-700 border-navy-600 text-gray-400 hover:border-navy-500'
                        }`}
                      >
                        {humanize(s.name)}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Temperature: {newPersona.temperature.toFixed(2)}</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={newPersona.temperature}
                    onChange={e => setNewPersona(p => ({ ...p, temperature: parseFloat(e.target.value) }))}
                    className="w-full accent-accent-blue"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowCreatePersona(false)}
                  className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreatePersona}
                  disabled={!newPersona.id || !newPersona.name}
                  className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  Create
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
