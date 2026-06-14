'use client';

import React from 'react';
import { Icon, Tag } from '@/components/sentinel';
import { useProject } from '@/lib/ProjectContext';

export function ReviewView() {
  const { activeProject } = useProject();
  return (
    <div style={{ height: '100%', overflow: 'auto', background: 'var(--paper)' }}>
      <div style={{ maxWidth: 1000, margin: '0 auto', padding: '24px 32px 48px' }}>
        <div style={{ paddingBottom: 16, borderBottom: '1px solid var(--line)', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.2em', color: 'var(--fg-3)' }}>
              ANALYST REVIEW · QUEUE
            </span>
            <Tag tone="signal">PENDING BACKEND</Tag>
          </div>
          <h1 style={{ margin: 0, fontFamily: 'var(--serif)', fontSize: 34, fontWeight: 500, letterSpacing: '-0.015em', color: 'var(--ink)', lineHeight: 1.1 }}>
            Second pair of eyes<span style={{ color: 'var(--signal)' }}>.</span>
          </h1>
          <p style={{ margin: '8px 0 0', maxWidth: 620, fontFamily: 'var(--serif)', fontSize: 14.5, lineHeight: 1.55, color: 'var(--fg-2)' }}>
            The agent will flag inferred, single-source, and auto-tagged claims here so an analyst can approve them before they enter a published product.
          </p>
        </div>

        <PendingPanel
          icon="check"
          title="Review queue endpoint not yet available"
          body={
            activeProject
              ? `Once the backend exposes a review API (or returns low-confidence claims via the entities or graph endpoints), this view will list claims from "${activeProject.name}" with Approve / Reject / Reopen actions, filterable by status and reason taxonomy.`
              : 'Open a project to see its review queue once the backend review endpoint is wired.'
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
