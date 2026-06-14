'use client';

import React, { useEffect, useState } from 'react';
import { Icon, Tag } from '@/components/sentinel';
import { useProject } from '@/lib/ProjectContext';
import { entitiesApi } from '@/lib/api';

interface CyberEntity {
  id: string;
  name?: string;
  entity_type?: string;
  entity_category?: string;
}

// Backend currently extracts these as named-entity types — none cyber-specific.
const CYBER_LIKE_TYPES = ['INDICATOR', 'TTP', 'THREAT_ACTOR', 'MALWARE', 'CVE'];

export function CyberView() {
  const { activeProject } = useProject();
  const [cyberEntities, setCyberEntities] = useState<CyberEntity[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeProject) { setCyberEntities([]); return; }
    setLoading(true);
    entitiesApi
      .search(activeProject.id)
      .then((res) => {
        const raw = res.data as CyberEntity[] | { entities?: CyberEntity[] };
        const list = Array.isArray(raw) ? raw : (raw?.entities ?? []);
        const match = (Array.isArray(list) ? list : []).filter((e) => {
          const t = (e.entity_type || '').toUpperCase();
          return CYBER_LIKE_TYPES.some((c) => t.includes(c));
        });
        setCyberEntities(match);
      })
      .catch(() => setCyberEntities([]))
      .finally(() => setLoading(false));
  }, [activeProject]);

  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 32px 48px' }}>
        <div style={{ paddingBottom: 16, borderBottom: '1px solid var(--line)', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--fg-3)' }}>
              CYBER LENS
            </span>
            <Tag tone="signal">PENDING BACKEND</Tag>
          </div>
          <h1 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 34, fontWeight: 500, letterSpacing: '-0.015em', color: 'var(--ink)', lineHeight: 1.1 }}>
            Cyber workspace<span style={{ color: 'var(--signal)' }}>.</span>
          </h1>
          <p style={{ margin: '8px 0 0', maxWidth: 640, fontFamily: 'var(--serif)', fontSize: 14.5, lineHeight: 1.55, color: 'var(--fg-2)' }}>
            IOCs, MITRE ATT&amp;CK technique coverage, and threat-actor profiles for this project.
          </p>
        </div>

        {loading ? (
          <p style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)', letterSpacing: '0.08em' }}>LOADING…</p>
        ) : cyberEntities.length === 0 ? (
          <PendingPanel
            icon="cyber"
            title="No cyber-typed entities in this project"
            body={
              activeProject
                ? `Backend NLP currently extracts Person / Organization / Location / Domain / Date / Financial / Quantity / Document types — no INDICATOR / TTP / THREAT_ACTOR / MALWARE / CVE types yet. Once the backend cyber namespace ships (or extends entity_type extraction), "${activeProject.name}" will render IOCs, an ATT&CK matrix, and threat-actor cards here.`
                : 'Open a project to see its cyber lens once the backend cyber namespace is wired.'
            }
          />
        ) : (
          <div>
            <p style={{ fontSize: 13, color: 'var(--fg-2)', marginBottom: 14 }}>
              Found <strong>{cyberEntities.length}</strong> cyber-typed entit{cyberEntities.length === 1 ? 'y' : 'ies'} in this project. Listing them below — full cyber namespace (IOCs, MITRE matrix, threat actors) still pending backend.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
              {cyberEntities.slice(0, 100).map((e) => (
                <div
                  key={e.id}
                  style={{
                    padding: '10px 12px', background: 'var(--paper-2)',
                    border: '1px solid var(--line)', borderRadius: 3,
                  }}
                >
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.1em', color: 'var(--cite)', fontWeight: 600 }}>
                    {(e.entity_type || 'UNKNOWN').toUpperCase()}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginTop: 3 }}>
                    {e.name || e.id}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function PendingPanel({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <div
      style={{
        padding: '36px 32px',
        background: 'var(--paper-2)',
        border: '1px dashed var(--line)',
        borderRadius: 4,
        display: 'flex',
        gap: 18,
        alignItems: 'flex-start',
      }}
    >
      <span
        style={{
          width: 40, height: 40, borderRadius: 4,
          background: 'var(--paper)', border: '1px solid var(--line)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--fg-2)', flexShrink: 0,
        }}
      >
        <Icon name={icon} size={20} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3 style={{ margin: '0 0 8px', fontFamily: 'var(--serif)', fontSize: 20, fontWeight: 500, color: 'var(--ink)' }}>
          {title}
        </h3>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55, color: 'var(--fg-2)' }}>
          {body}
        </p>
      </div>
    </div>
  );
}
