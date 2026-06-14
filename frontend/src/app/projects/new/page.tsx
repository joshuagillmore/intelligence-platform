'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { projectsApi, type Project } from '@/lib/api';
import { Btn } from '@/components/sentinel';
import { useNotifications } from '@/components/NotificationProvider';
import { useProject } from '@/lib/ProjectContext';

export default function NewProjectPage() {
  const router = useRouter();
  const { addNotification, updateNotification } = useNotifications();
  const { setActiveProject } = useProject();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [classification, setClassification] = useState('UNCLASSIFIED');
  const [priority, setPriority] = useState<'low' | 'medium' | 'high'>('medium');
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = name.trim().length > 0 && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    const notifId = addNotification({
      type: 'processing',
      title: 'Creating project',
      message: name.trim(),
    });
    try {
      const res = await projectsApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        classification_level: classification,
        priority,
      });
      const created = res.data as Project;
      // Set the new project as active so the Hub masthead + every view picks it up,
      // then return to the Hub (the legacy /project/[id] page is being phased out).
      setActiveProject(created);
      updateNotification(notifId, {
        type: 'success',
        title: 'Project created',
        message: name.trim(),
      });
      router.push('/');
    } catch (e) {
      updateNotification(notifId, {
        type: 'error',
        title: 'Failed to create project',
        message: (e as Error).message,
      });
      setSubmitting(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 12px',
    background: 'var(--paper)',
    border: '1px solid var(--line)',
    borderRadius: 3,
    fontFamily: 'var(--sans)',
    fontSize: 14,
    color: 'var(--ink)',
    outline: 'none',
  };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontFamily: 'var(--mono)',
    fontSize: 10,
    letterSpacing: '0.12em',
    color: 'var(--fg-3)',
    marginBottom: 6,
  };

  return (
    <div style={{ padding: '32px 40px 64px', maxWidth: 720, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <div
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 10,
            letterSpacing: '0.14em',
            color: 'var(--fg-3)',
            marginBottom: 4,
          }}
        >
          NEW PROJECT
        </div>
        <h1
          style={{
            margin: 0,
            fontFamily: 'var(--serif)',
            fontSize: 28,
            fontWeight: 500,
            color: 'var(--ink)',
          }}
        >
          Open a new line of inquiry
        </h1>
        <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--fg-3)' }}>
          A project scopes one investigation: its PIRs, collections, graph, and findings live under it.
        </p>
      </div>

      <div
        style={{
          background: 'var(--paper-2)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          padding: 24,
          display: 'flex',
          flexDirection: 'column',
          gap: 18,
        }}
      >
        <div>
          <label style={labelStyle} htmlFor="np-name">NAME *</label>
          <input
            id="np-name"
            style={inputStyle}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Semiconductor export controls 2026"
            maxLength={200}
            autoFocus
          />
        </div>

        <div>
          <label style={labelStyle} htmlFor="np-desc">DESCRIPTION</label>
          <textarea
            id="np-desc"
            style={{ ...inputStyle, minHeight: 90, fontFamily: 'var(--serif)', fontSize: 15, lineHeight: 1.5, resize: 'vertical' }}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief scope, intent, or background for this investigation."
            maxLength={2000}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
          <div>
            <label style={labelStyle} htmlFor="np-class">CLASSIFICATION</label>
            <select
              id="np-class"
              style={inputStyle}
              value={classification}
              onChange={(e) => setClassification(e.target.value)}
            >
              <option value="UNCLASSIFIED">UNCLASSIFIED</option>
              <option value="FOUO">FOUO</option>
              <option value="CONFIDENTIAL">CONFIDENTIAL</option>
              <option value="SECRET">SECRET</option>
            </select>
          </div>
          <div>
            <label style={labelStyle} htmlFor="np-prio">PRIORITY</label>
            <select
              id="np-prio"
              style={inputStyle}
              value={priority}
              onChange={(e) => setPriority(e.target.value as typeof priority)}
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
        <Btn variant="ghost" onClick={() => router.push('/')}>Cancel</Btn>
        <Btn
          icon="plus"
          onClick={canSubmit ? submit : undefined}
          style={canSubmit ? undefined : { opacity: 0.45, cursor: 'not-allowed' }}
        >
          {submitting ? 'Creating…' : 'Create project'}
        </Btn>
      </div>
    </div>
  );
}
