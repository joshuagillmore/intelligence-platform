'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Icon, PulseDot } from '@/components/sentinel';
import { useProject } from '@/lib/ProjectContext';
import { projectsApi, type Project } from '@/lib/api';

export function ProjectSwitcher() {
  const { activeProject, setActiveProject } = useProject();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    projectsApi
      .list()
      .then((res) => {
        if (cancelled) return;
        const raw = res.data;
        const list = Array.isArray(raw)
          ? raw
          : (raw as { projects?: unknown[] })?.projects ?? [];
        setProjects((Array.isArray(list) ? list : []) as Project[]);
      })
      .catch(() => { if (!cancelled) setProjects([]); });
    return () => { cancelled = true; };
  }, [open]);

  const label = activeProject?.name || 'No project';

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '0 10px',
          height: 32,
          background: open ? 'var(--paper-2)' : 'transparent',
          border: '1px solid var(--line)',
          borderRadius: 4,
          cursor: 'pointer',
          color: 'var(--ink)',
        }}
      >
        <PulseDot />
        <span
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 8.5,
            letterSpacing: '0.08em',
            color: 'var(--fg-3)',
          }}
        >
          ACTIVE
        </span>
        <span style={{ fontSize: 13, fontWeight: 500, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {label}
        </span>
        <Icon name="chevron-down" size={14} />
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            minWidth: 280,
            maxWidth: 360,
            maxHeight: 420,
            overflowY: 'auto',
            background: 'var(--paper)',
            border: '1px solid var(--line)',
            borderRadius: 4,
            boxShadow: '0 12px 32px rgba(15,18,22,0.18)',
            zIndex: 100,
          }}
        >
          <div
            style={{
              padding: '8px 12px',
              borderBottom: '1px solid var(--line-soft)',
              fontFamily: 'var(--mono)',
              fontSize: 9.5,
              letterSpacing: '0.18em',
              color: 'var(--fg-3)',
              fontWeight: 600,
            }}
          >
            PROJECTS · {projects.length}
          </div>

          {projects.length === 0 ? (
            <div style={{ padding: '14px 12px', fontSize: 12, color: 'var(--fg-3)' }}>
              No projects yet.
            </div>
          ) : (
            projects.map((p) => {
              const isActive = activeProject?.id === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => {
                    setActiveProject(p);
                    setOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    padding: '9px 12px',
                    background: isActive ? 'var(--paper-2)' : 'transparent',
                    border: 'none',
                    borderBottom: '1px solid var(--line-soft)',
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = 'var(--paper-2)'; }}
                  onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
                >
                  <span
                    style={{
                      width: 6, height: 6, borderRadius: '50%',
                      background: isActive ? 'var(--live)' : 'var(--fg-4)',
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 12.5,
                        fontWeight: 500,
                        color: 'var(--ink)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {p.name}
                    </div>
                    {p.description && (
                      <div
                        style={{
                          fontSize: 11,
                          color: 'var(--fg-3)',
                          marginTop: 1,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {p.description}
                      </div>
                    )}
                  </div>
                  {isActive && (
                    <span style={{ flexShrink: 0, color: 'var(--live)' }}>
                      <Icon name="check" size={13} stroke={2.5} />
                    </span>
                  )}
                </button>
              );
            })
          )}

          <button
            onClick={() => {
              setOpen(false);
              router.push('/projects/new');
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              padding: '10px 12px',
              background: 'transparent',
              border: 'none',
              borderTop: '1px solid var(--line)',
              color: 'var(--ink)',
              fontSize: 12.5,
              fontWeight: 500,
              cursor: 'pointer',
              textAlign: 'left',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--paper-2)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <Icon name="plus" size={14} />
            New project
          </button>
        </div>
      )}
    </div>
  );
}
