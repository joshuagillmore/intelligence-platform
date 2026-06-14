'use client';

import React, { useEffect, useState } from 'react';
import {
  llmApi,
  personasApi,
  adminApi,
} from '@/lib/api';
import {
  Btn,
  Tag,
} from '@/components/sentinel';

// ============================================================================
// Types
// ============================================================================

type TabId = 'skills' | 'personas' | 'models' | 'keys' | 'network' | 'system';

interface Skill {
  id: string;
  name: string;
  description: string;
}

interface PersonaRecord {
  id: string;
  name: string;
  description: string;
  skills: string[];
  temperature: number;
  active?: boolean;
}

interface ModelRecord {
  provider: string;
  model: string;
  context_window?: number;
  context?: number;
  active?: boolean;
}

interface ApiKeyRecord {
  id: string;
  provider: string;
  label: string;
  masked?: string;
  last_four?: string;
  api_key?: string;
  active?: boolean;
}

interface ProxyConfig {
  mode: string;
  proxy_url?: string;
  tor_port?: number;
}

interface SystemConfig {
  [key: string]: unknown;
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'skills',   label: 'Skills' },
  { id: 'personas', label: 'Personas' },
  { id: 'models',   label: 'Models' },
  { id: 'keys',     label: 'API Keys' },
  { id: 'network',  label: 'Network' },
  { id: 'system',   label: 'System' },
];

// ============================================================================
// Page wrapper
// ============================================================================

export function AdminView() {
  const [tab, setTab] = useState<TabId>('skills');

  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '28px 32px 64px' }}>
        <header style={{ paddingBottom: 18, borderBottom: '1px solid var(--line)' }}>
          <SectionLabel>SENTINEL · ADMIN</SectionLabel>
          <h1
            style={{
              margin: '6px 0 0',
              fontFamily: 'var(--serif)',
              fontWeight: 500,
              fontSize: 38,
              letterSpacing: '-0.02em',
              color: 'var(--ink)',
              lineHeight: 1,
            }}
          >
            Configuration<span style={{ color: 'var(--signal)' }}>.</span>
          </h1>
          <p
            style={{
              margin: '12px 0 0',
              fontFamily: 'var(--serif)',
              fontSize: 16,
              lineHeight: 1.5,
              color: 'var(--fg-2)',
              maxWidth: 720,
            }}
          >
            Skills, personas, models, credentials, and infrastructure settings for the desk.
          </p>
        </header>

        <nav
          style={{
            display: 'flex',
            gap: 0,
            marginTop: 22,
            borderBottom: '1px solid var(--line)',
          }}
        >
          {TABS.map((t) => {
            const active = t.id === tab;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  padding: '10px 16px',
                  fontFamily: 'var(--sans)',
                  fontSize: 13,
                  fontWeight: active ? 600 : 500,
                  color: active ? 'var(--ink)' : 'var(--fg-3)',
                  cursor: 'pointer',
                  borderBottom: `2px solid ${active ? 'var(--ink)' : 'transparent'}`,
                  marginBottom: -1,
                }}
              >
                {t.label}
              </button>
            );
          })}
        </nav>

        <div style={{ marginTop: 24 }}>
          {tab === 'skills'   && <SkillsTab />}
          {tab === 'personas' && <PersonasTab />}
          {tab === 'models'   && <ModelsTab />}
          {tab === 'keys'     && <ApiKeysTab />}
          {tab === 'network'  && <NetworkTab />}
          {tab === 'system'   && <SystemTab />}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Skills tab
// ============================================================================

function SkillsTab() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [active, setActive] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    llmApi
      .skills()
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { data?: unknown[] })?.data ?? [];
        const items = Array.isArray(list) ? (list as Skill[]) : [];
        setSkills(items);
        const map: Record<string, boolean> = {};
        items.forEach((s) => (map[s.id] = true));
        setActive(map);
      })
      .catch(() => setSkills([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <TabFrame
      label="LLM SKILLS"
      title="Available analytic skills"
      action={null}
    >
      {loading ? (
        <Loading />
      ) : skills.length === 0 ? (
        <EmptyRow text="No skills registered." />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 12,
          }}
        >
          {skills.map((s) => {
            const isActive = !!active[s.id];
            return (
              <article
                key={s.id}
                style={{
                  padding: '14px 16px',
                  background: 'var(--paper-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 3,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span
                    style={{
                      fontFamily: 'var(--mono)',
                      fontSize: 11,
                      fontWeight: 600,
                      color: 'var(--ink)',
                      letterSpacing: '0.06em',
                    }}
                  >
                    {s.name}
                  </span>
                  <Toggle
                    on={isActive}
                    onChange={() =>
                      setActive((prev) => ({ ...prev, [s.id]: !prev[s.id] }))
                    }
                  />
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: 12.5,
                    lineHeight: 1.45,
                    color: 'var(--fg-2)',
                  }}
                >
                  {s.description}
                </p>
              </article>
            );
          })}
        </div>
      )}
    </TabFrame>
  );
}

// ============================================================================
// Personas tab
// ============================================================================

function PersonasTab() {
  const [personas, setPersonas] = useState<PersonaRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formTemp, setFormTemp] = useState(0.3);
  const [formSubmitting, setFormSubmitting] = useState(false);

  function load() {
    setLoading(true);
    personasApi
      .list()
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { data?: unknown[] })?.data ?? [];
        setPersonas(Array.isArray(list) ? (list as PersonaRecord[]) : []);
      })
      .catch(() => setPersonas([]))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleActivate(id: string) {
    try {
      await personasApi.activate(id);
      load();
    } catch {
      // ignore
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this persona?')) return;
    try {
      await personasApi.delete(id);
      load();
    } catch {
      // ignore
    }
  }

  async function handleCreate() {
    if (!formName.trim()) return;
    setFormSubmitting(true);
    try {
      await personasApi.create({
        id: formName.trim().toLowerCase().replace(/\s+/g, '-'),
        name: formName.trim(),
        description: formDesc.trim(),
        skills: [],
        temperature: formTemp,
      });
      setFormName('');
      setFormDesc('');
      setFormTemp(0.3);
      setShowForm(false);
      load();
    } catch {
      // ignore
    } finally {
      setFormSubmitting(false);
    }
  }

  return (
    <TabFrame
      label="PERSONAS"
      title="Voices on the desk"
      action={
        <Btn
          variant="outline"
          icon="plus"
          size="sm"
          onClick={() => setShowForm((v) => !v)}
        >
          New persona
        </Btn>
      }
    >
      {showForm && (
        <div
          style={{
            padding: '14px 16px',
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            marginBottom: 16,
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <Input
            label="Name"
            value={formName}
            onChange={setFormName}
            placeholder="e.g. Counter-narcotics analyst"
          />
          <TextArea
            label="Description"
            value={formDesc}
            onChange={setFormDesc}
            placeholder="Tone, audience, framing conventions…"
          />
          <div>
            <FieldLabel>TEMPERATURE · {formTemp.toFixed(2)}</FieldLabel>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={formTemp}
              onChange={(e) => setFormTemp(Number(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--ink)' }}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" size="sm" onClick={() => setShowForm(false)}>
              Cancel
            </Btn>
            <Btn variant="solid" icon="check" size="sm" onClick={handleCreate}>
              {formSubmitting ? 'Creating…' : 'Create'}
            </Btn>
          </div>
        </div>
      )}

      {loading ? (
        <Loading />
      ) : personas.length === 0 ? (
        <EmptyRow text="No personas yet." />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: 12,
          }}
        >
          {personas.map((p) => (
            <article
              key={p.id}
              style={{
                padding: '16px',
                background: 'var(--paper-2)',
                border: `1px solid ${p.active ? 'var(--ink)' : 'var(--line)'}`,
                borderRadius: 3,
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <div
                  style={{
                    fontFamily: 'var(--serif)',
                    fontSize: 17,
                    fontWeight: 500,
                    color: 'var(--ink)',
                    letterSpacing: '-0.005em',
                  }}
                >
                  {p.name}
                </div>
                {p.active && <Tag tone="signal">ACTIVE</Tag>}
              </div>
              <p
                style={{
                  margin: 0,
                  fontSize: 12.5,
                  lineHeight: 1.45,
                  color: 'var(--fg-2)',
                }}
              >
                {p.description}
              </p>

              {p.skills && p.skills.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {p.skills.map((s) => (
                    <Tag key={s}>{s}</Tag>
                  ))}
                </div>
              )}

              <div>
                <FieldLabel>TEMPERATURE · {(p.temperature ?? 0).toFixed(2)}</FieldLabel>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={p.temperature ?? 0}
                  readOnly
                  style={{ width: '100%', accentColor: 'var(--fg-3)' }}
                />
              </div>

              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
                <Btn
                  variant="ghost"
                  icon="x"
                  size="sm"
                  onClick={() => handleDelete(p.id)}
                >
                  Delete
                </Btn>
                <Btn
                  variant={p.active ? 'outline' : 'solid'}
                  icon="check"
                  size="sm"
                  onClick={() => handleActivate(p.id)}
                >
                  {p.active ? 'Active' : 'Activate'}
                </Btn>
              </div>
            </article>
          ))}
        </div>
      )}
    </TabFrame>
  );
}

// ============================================================================
// Models tab
// ============================================================================

function ModelsTab() {
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  function load() {
    setLoading(true);
    adminApi
      .listModels()
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { models?: unknown[] })?.models ?? [];
        const items = Array.isArray(list) ? (list as ModelRecord[]) : [];
        setModels(items);
        const cur = items.find((m) => m.active);
        if (cur) setActiveKey(`${cur.provider}/${cur.model}`);
      })
      .catch(() => setModels([]))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleSelect(m: ModelRecord) {
    setActiveKey(`${m.provider}/${m.model}`);
    try {
      await adminApi.selectModel(m.provider, m.model);
      load();
    } catch {
      // ignore
    }
  }

  const grouped = groupByProvider(models);

  return (
    <TabFrame label="MODELS" title="Backends">
      {loading ? (
        <Loading />
      ) : models.length === 0 ? (
        <EmptyRow text="No models discovered. Check provider configuration." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          {Object.keys(grouped).map((provider) => (
            <section key={provider}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  gap: 10,
                  marginBottom: 10,
                }}
              >
                <SectionLabel>{provider.toUpperCase()}</SectionLabel>
                <span style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
                  {grouped[provider].length} model{grouped[provider].length === 1 ? '' : 's'}
                </span>
              </div>
              <div
                style={{
                  background: 'var(--paper-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 3,
                  overflow: 'hidden',
                }}
              >
                {grouped[provider].map((m, i) => {
                  const key = `${m.provider}/${m.model}`;
                  const isActive = key === activeKey || m.active;
                  const ctx = m.context_window ?? m.context ?? 0;
                  return (
                    <div
                      key={key}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 140px 110px',
                        alignItems: 'center',
                        gap: 16,
                        padding: '12px 16px',
                        borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                        <span
                          style={{
                            fontFamily: 'var(--mono)',
                            fontSize: 12.5,
                            fontWeight: 600,
                            color: 'var(--ink)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {m.model}
                        </span>
                        {isActive && <Tag tone="signal">ACTIVE</Tag>}
                      </div>
                      <span
                        style={{
                          fontFamily: 'var(--mono)',
                          fontSize: 11,
                          color: 'var(--fg-3)',
                          letterSpacing: '0.06em',
                        }}
                      >
                        {ctx ? `${ctx.toLocaleString()} CTX` : '—'}
                      </span>
                      <div style={{ justifySelf: 'end' }}>
                        <Btn
                          variant={isActive ? 'outline' : 'solid'}
                          size="sm"
                          icon={isActive ? 'check' : 'arrow-right'}
                          onClick={() => handleSelect(m)}
                        >
                          {isActive ? 'Selected' : 'Select'}
                        </Btn>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </TabFrame>
  );
}

function groupByProvider(models: ModelRecord[]): Record<string, ModelRecord[]> {
  const grouped: Record<string, ModelRecord[]> = {};
  models.forEach((m) => {
    const key = (m.provider || 'unknown').toLowerCase();
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(m);
  });
  return grouped;
}

// ============================================================================
// API keys tab
// ============================================================================

function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const [showForm, setShowForm] = useState(false);
  const [formProvider, setFormProvider] = useState('openai');
  const [formLabel, setFormLabel] = useState('');
  const [formKey, setFormKey] = useState('');
  const [formSubmitting, setFormSubmitting] = useState(false);

  function load() {
    setLoading(true);
    adminApi
      .listApiKeys()
      .then((res) => {
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { keys?: unknown[] })?.keys ?? [];
        setKeys(Array.isArray(list) ? (list as ApiKeyRecord[]) : []);
      })
      .catch(() => setKeys([]))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleActivate(k: ApiKeyRecord) {
    try {
      await adminApi.activateApiKey(k.id, k.provider);
      load();
    } catch {
      // ignore
    }
  }

  async function handleDelete(k: ApiKeyRecord) {
    if (!confirm('Delete this API key?')) return;
    try {
      await adminApi.deleteApiKey(k.id);
      load();
    } catch {
      // ignore
    }
  }

  async function handleAdd() {
    if (!formProvider.trim() || !formKey.trim()) return;
    setFormSubmitting(true);
    try {
      await adminApi.addApiKey(formProvider.trim(), formLabel.trim() || formProvider.trim(), formKey.trim());
      setFormProvider('openai');
      setFormLabel('');
      setFormKey('');
      setShowForm(false);
      load();
    } catch {
      // ignore
    } finally {
      setFormSubmitting(false);
    }
  }

  return (
    <TabFrame
      label="API KEYS"
      title="Provider credentials"
      action={
        <Btn
          variant="outline"
          icon="plus"
          size="sm"
          onClick={() => setShowForm((v) => !v)}
        >
          Add key
        </Btn>
      }
    >
      {showForm && (
        <div
          style={{
            padding: '14px 16px',
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            marginBottom: 16,
            display: 'grid',
            gridTemplateColumns: '180px 1fr 1fr auto',
            gap: 10,
            alignItems: 'end',
          }}
        >
          <div>
            <FieldLabel>PROVIDER</FieldLabel>
            <select
              value={formProvider}
              onChange={(e) => setFormProvider(e.target.value)}
              style={selectStyle}
            >
              <option value="openai">openai</option>
              <option value="anthropic">anthropic</option>
              <option value="ollama">ollama</option>
              <option value="other">other</option>
            </select>
          </div>
          <Input label="Label" value={formLabel} onChange={setFormLabel} placeholder="e.g. team key" />
          <Input label="Key" value={formKey} onChange={setFormKey} placeholder="sk-…" type="password" />
          <Btn variant="solid" icon="check" size="sm" onClick={handleAdd}>
            {formSubmitting ? 'Saving…' : 'Save'}
          </Btn>
        </div>
      )}

      {loading ? (
        <Loading />
      ) : keys.length === 0 ? (
        <EmptyRow text="No API keys configured." />
      ) : (
        <div
          style={{
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          {keys.map((k, i) => {
            const masked = k.masked
              ? k.masked
              : k.last_four
              ? `••••${k.last_four}`
              : k.api_key
              ? `••••${k.api_key.slice(-4)}`
              : '••••';
            return (
              <div
                key={k.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '120px 1fr 140px auto',
                  alignItems: 'center',
                  gap: 16,
                  padding: '12px 16px',
                  borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 11,
                    color: 'var(--ink)',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    fontWeight: 600,
                  }}
                >
                  {k.provider}
                </span>
                <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: 13, color: 'var(--ink)' }}>{k.label || '—'}</span>
                  {k.active && <Tag tone="signal" style={{ alignSelf: 'flex-start', marginTop: 4 }}>ACTIVE</Tag>}
                </div>
                <span
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 11.5,
                    color: 'var(--fg-2)',
                    letterSpacing: '0.05em',
                  }}
                >
                  {masked}
                </span>
                <div style={{ display: 'flex', gap: 6, justifySelf: 'end' }}>
                  <Btn variant="ghost" icon="check" size="sm" onClick={() => handleActivate(k)}>
                    Activate
                  </Btn>
                  <Btn variant="ghost" icon="x" size="sm" onClick={() => handleDelete(k)}>
                    Delete
                  </Btn>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </TabFrame>
  );
}

// ============================================================================
// Network tab
// ============================================================================

function NetworkTab() {
  const [mode, setMode] = useState<string>('direct');
  const [proxyUrl, setProxyUrl] = useState<string>('');
  const [torPort, setTorPort] = useState<number>(9050);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    adminApi
      .getProxy()
      .then((res) => {
        const data = (res.data ?? {}) as ProxyConfig;
        setMode(data.mode || 'direct');
        if (data.proxy_url) setProxyUrl(data.proxy_url);
        if (typeof data.tor_port === 'number') setTorPort(data.tor_port);
      })
      .catch(() => {
        // keep defaults
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!statusMsg) return;
    const t = setTimeout(() => setStatusMsg(null), 2400);
    return () => clearTimeout(t);
  }, [statusMsg]);

  async function handleSave() {
    setSaving(true);
    try {
      const payload: { mode: string; proxy_url?: string; tor_port?: number } = { mode };
      if (mode === 'proxy') payload.proxy_url = proxyUrl;
      if (mode === 'tor') payload.tor_port = torPort;
      await adminApi.updateProxy(payload);
      setStatusMsg('Saved.');
    } catch {
      setStatusMsg('Save failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <TabFrame label="NETWORK" title="Egress routing">
      {loading ? (
        <Loading />
      ) : (
        <div
          style={{
            padding: '18px 20px',
            background: 'var(--paper-2)',
            border: '1px solid var(--line)',
            borderRadius: 3,
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
            maxWidth: 540,
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <FieldLabel>MODE</FieldLabel>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(['direct', 'proxy', 'tor'] as const).map((m) => {
                const active = m === mode;
                return (
                  <label
                    key={m}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '8px 12px',
                      border: `1px solid ${active ? 'var(--ink)' : 'var(--line)'}`,
                      borderRadius: 3,
                      cursor: 'pointer',
                      background: active ? 'var(--paper)' : 'transparent',
                    }}
                  >
                    <input
                      type="radio"
                      name="proxy-mode"
                      checked={active}
                      onChange={() => setMode(m)}
                      style={{ accentColor: 'var(--ink)' }}
                    />
                    <span
                      style={{
                        fontSize: 13,
                        color: 'var(--ink)',
                        textTransform: 'capitalize',
                        fontWeight: active ? 600 : 500,
                      }}
                    >
                      {m}
                    </span>
                    <span
                      style={{
                        fontSize: 11.5,
                        color: 'var(--fg-3)',
                        marginLeft: 'auto',
                      }}
                    >
                      {m === 'direct'
                        ? 'No intermediary'
                        : m === 'proxy'
                        ? 'HTTP/HTTPS proxy'
                        : 'Local Tor SOCKS'}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          {mode === 'proxy' && (
            <Input
              label="Proxy URL"
              value={proxyUrl}
              onChange={setProxyUrl}
              placeholder="http://proxy.local:8080"
            />
          )}
          {mode === 'tor' && (
            <div>
              <FieldLabel>TOR PORT</FieldLabel>
              <input
                type="number"
                value={torPort}
                onChange={(e) => setTorPort(Number(e.target.value))}
                style={inputStyle}
              />
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'flex-end' }}>
            {statusMsg && (
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10.5,
                  color: 'var(--signal-ink)',
                  letterSpacing: '0.08em',
                }}
              >
                {statusMsg.toUpperCase()}
              </span>
            )}
            <Btn variant="solid" icon="check" size="sm" onClick={handleSave}>
              {saving ? 'Saving…' : 'Save'}
            </Btn>
          </div>
        </div>
      )}
    </TabFrame>
  );
}

// ============================================================================
// System tab
// ============================================================================

function SystemTab() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminApi
      .config()
      .then((res) => setConfig((res.data ?? {}) as SystemConfig))
      .catch(() => setConfig({}))
      .finally(() => setLoading(false));
  }, []);

  const entries = config ? Object.entries(config) : [];

  return (
    <TabFrame label="SYSTEM" title="Runtime configuration">
      {loading ? (
        <Loading />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          <section>
            <div style={{ marginBottom: 8 }}>
              <SectionLabel>CONFIG</SectionLabel>
            </div>
            {entries.length === 0 ? (
              <EmptyRow text="No configuration available." />
            ) : (
              <div
                style={{
                  background: 'var(--paper-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 3,
                  overflow: 'hidden',
                }}
              >
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: 'var(--paper)' }}>
                      <th style={thStyle}>Key</th>
                      <th style={thStyle}>Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map(([k, v], i) => (
                      <tr
                        key={k}
                        style={{
                          borderTop: i === 0 ? 'none' : '1px solid var(--line-soft)',
                        }}
                      >
                        <td
                          style={{
                            ...tdStyle,
                            fontFamily: 'var(--mono)',
                            fontSize: 11.5,
                            color: 'var(--ink)',
                            fontWeight: 600,
                            width: '34%',
                          }}
                        >
                          {k}
                        </td>
                        <td
                          style={{
                            ...tdStyle,
                            fontFamily: 'var(--mono)',
                            fontSize: 11.5,
                            color: 'var(--fg-2)',
                            wordBreak: 'break-all',
                          }}
                        >
                          {formatValue(v)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Live request log removed — backend access-log endpoint not yet available. */}
        </div>
      )}
    </TabFrame>
  );
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

// ============================================================================
// Shared
// ============================================================================

function TabFrame({
  label,
  title,
  action,
  children,
}: {
  label: string;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 16,
          paddingBottom: 10,
          borderBottom: '1px solid var(--line-soft)',
        }}
      >
        <div>
          <SectionLabel>{label}</SectionLabel>
          <h2
            style={{
              margin: '2px 0 0',
              fontFamily: 'var(--serif)',
              fontWeight: 500,
              fontSize: 22,
              color: 'var(--ink)',
              letterSpacing: '-0.01em',
            }}
          >
            {title}
          </h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--mono)',
        fontSize: 9.5,
        letterSpacing: '0.2em',
        color: 'var(--fg-3)',
        fontWeight: 600,
        textTransform: 'uppercase',
      }}
    >
      {children}
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--mono)',
        fontSize: 9.5,
        letterSpacing: '0.18em',
        color: 'var(--fg-3)',
        fontWeight: 600,
        textTransform: 'uppercase',
        marginBottom: 6,
      }}
    >
      {children}
    </div>
  );
}

function Loading() {
  return (
    <div
      style={{
        padding: '32px 20px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px solid var(--line)',
        borderRadius: 3,
        fontFamily: 'var(--mono)',
        fontSize: 11,
        color: 'var(--fg-3)',
        letterSpacing: '0.1em',
      }}
    >
      LOADING…
    </div>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: '24px 20px',
        textAlign: 'center',
        background: 'var(--paper-2)',
        border: '1px dashed var(--line)',
        borderRadius: 3,
        color: 'var(--fg-3)',
        fontSize: 12.5,
      }}
    >
      {text}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  background: 'var(--paper)',
  border: '1px solid var(--line)',
  borderRadius: 3,
  fontFamily: 'var(--sans)',
  fontSize: 13,
  color: 'var(--ink)',
  outline: 'none',
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  appearance: 'auto',
};

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '10px 14px',
  fontFamily: 'var(--mono)',
  fontSize: 9.5,
  letterSpacing: '0.18em',
  color: 'var(--fg-3)',
  fontWeight: 600,
  textTransform: 'uppercase',
  borderBottom: '1px solid var(--line-soft)',
};

const tdStyle: React.CSSProperties = {
  padding: '10px 14px',
  fontSize: 12.5,
  color: 'var(--ink)',
  verticalAlign: 'top',
};

function Input({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <FieldLabel>{label.toUpperCase()}</FieldLabel>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={inputStyle}
      />
    </div>
  );
}

function TextArea({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <FieldLabel>{label.toUpperCase()}</FieldLabel>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={3}
        style={{ ...inputStyle, resize: 'vertical', minHeight: 64, fontFamily: 'var(--sans)' }}
      />
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button
      onClick={onChange}
      style={{
        position: 'relative',
        width: 32,
        height: 18,
        background: on ? 'var(--ink)' : 'var(--line)',
        border: 'none',
        borderRadius: 9,
        cursor: 'pointer',
        transition: 'background 0.15s',
        padding: 0,
        flexShrink: 0,
      }}
      aria-pressed={on}
    >
      <span
        style={{
          position: 'absolute',
          top: 2,
          left: on ? 16 : 2,
          width: 14,
          height: 14,
          borderRadius: '50%',
          background: 'var(--paper)',
          transition: 'left 0.15s',
        }}
      />
    </button>
  );
}
