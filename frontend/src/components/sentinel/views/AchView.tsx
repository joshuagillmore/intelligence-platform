'use client';

import React from 'react';
import { Icon, Tag } from '@/components/sentinel';
import { useProject } from '@/lib/ProjectContext';

export function AchView() {
  const { activeProject } = useProject();
  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1000, margin: '0 auto', padding: '28px 32px 48px' }}>
        <div style={{ paddingBottom: 16, borderBottom: '1px solid var(--line)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--fg-3)' }}>
              ANALYSIS · COMPETING HYPOTHESES
            </span>
            <Tag tone="signal">PENDING BACKEND</Tag>
          </div>
          <h1 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 36, fontWeight: 500, color: 'var(--ink)', letterSpacing: '-0.02em' }}>
            ACH workspace<span style={{ color: 'var(--signal)' }}>.</span>
          </h1>
          <p style={{ margin: '10px 0 0', maxWidth: 680, fontFamily: 'var(--serif)', fontSize: 14.5, lineHeight: 1.5, color: 'var(--fg-2)' }}>
            Heuer-style Analysis of Competing Hypotheses. Score each piece of evidence against each hypothesis to find which is most consistent with the data — and which gaps to close.
          </p>
        </div>

        <PendingPanel
          icon="bolt"
          title="ACH endpoint not yet available"
          body={
            activeProject
              ? `Once the backend exposes an ACH namespace (or accepts reports with report_type='ach'), this view will pivot to: managing hypotheses, scoring evidence on a consistency matrix, and surfacing agent-suggested evidence to seek — all scoped to "${activeProject.name}".`
              : 'Open a project and an ACH workspace will load here once the backend ACH endpoint is wired.'
          }
        />
      </div>
    </div>
  );
}

function PendingPanel({ icon, title, body }: { icon: string; title: string; body: string }) {
  return (
    <div
      style={{
        marginTop: 28,
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
