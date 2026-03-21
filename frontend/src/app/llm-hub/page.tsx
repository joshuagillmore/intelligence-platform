'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { llmApi } from '@/lib/api';

interface Skill {
  name: string;
  description?: string;
  active?: boolean;
  system_prompt?: string;
}

export default function LlmHubPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<string>('');
  const [prompt, setPrompt] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadSkills = useCallback(async () => {
    try {
      const res = await llmApi.skills();
      const data = res.data;
      // Handle both array and object responses
      if (Array.isArray(data)) {
        setSkills(data);
      } else if (typeof data === 'object') {
        const arr = Object.entries(data).map(([name, val]) => ({
          name,
          ...(typeof val === 'object' && val !== null ? val as Record<string, unknown> : {}),
        })) as Skill[];
        setSkills(arr);
      }
    } catch (e) {
      console.error('Failed to load skills', e);
    }
  }, []);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  async function testSkill() {
    if (!prompt.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await llmApi.query(
        [{ role: 'user', content: prompt.trim() }],
        selectedSkill || undefined
      );
      setResult(res.data.content || res.data.response || JSON.stringify(res.data, null, 2));
    } catch {
      setResult('Failed to query LLM.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-6">LLM Analyst Hub</h2>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Skills list */}
          <div>
            <h3 className="text-lg font-semibold mb-4">Available Skills</h3>
            <div className="space-y-2">
              {skills.map((skill) => (
                <div
                  key={skill.name}
                  className={`bg-navy-800 border rounded-lg p-4 cursor-pointer transition-colors ${
                    selectedSkill === skill.name ? 'border-accent-blue' : 'border-navy-600 hover:border-navy-600'
                  }`}
                  onClick={() => setSelectedSkill(skill.name)}
                >
                  <div className="flex items-center justify-between">
                    <h4 className="font-medium text-sm">{skill.name}</h4>
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      skill.active !== false ? 'bg-green-900/30 text-green-400' : 'bg-gray-900/30 text-gray-400'
                    }`}>
                      {skill.active !== false ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  {skill.description && (
                    <p className="text-xs text-gray-400 mt-1">{skill.description}</p>
                  )}
                </div>
              ))}
              {skills.length === 0 && (
                <p className="text-gray-500 text-sm">No skills available.</p>
              )}
            </div>
          </div>

          {/* Test area */}
          <div>
            <h3 className="text-lg font-semibold mb-4">Test Skill</h3>
            <div className="bg-navy-800 border border-navy-600 rounded-lg p-4">
              <div className="mb-3">
                <label className="text-xs text-gray-400 block mb-1">Skill</label>
                <select
                  value={selectedSkill}
                  onChange={(e) => setSelectedSkill(e.target.value)}
                  className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-blue"
                >
                  <option value="">Default (no skill)</option>
                  {skills.map(s => (
                    <option key={s.name} value={s.name}>{s.name}</option>
                  ))}
                </select>
              </div>
              <div className="mb-3">
                <label className="text-xs text-gray-400 block mb-1">Prompt</label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Enter your test prompt..."
                  className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-2 text-sm h-32 focus:outline-none focus:border-accent-blue resize-none"
                />
              </div>
              <button
                onClick={testSkill}
                disabled={loading || !prompt.trim()}
                className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-50 transition-colors"
              >
                {loading ? 'Querying...' : 'Test'}
              </button>

              {result && (
                <div className="mt-4 bg-navy-700 rounded p-3 max-h-64 overflow-y-auto">
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">{result}</pre>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
