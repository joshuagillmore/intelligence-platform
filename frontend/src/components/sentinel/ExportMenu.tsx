'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/sentinel';

export interface ExportOption {
  id: string;
  label: string;
  hint?: string;
}

export const DEFAULT_EXPORTS: ExportOption[] = [
  { id: 'pdf',  label: 'PDF',          hint: 'formatted product' },
  { id: 'docx', label: 'DOCX',         hint: 'editable in Word' },
  { id: 'stix', label: 'STIX 2.1',     hint: 'cyber-threat exchange' },
  { id: 'json', label: 'JSON',         hint: 'machine-readable' },
  { id: 'csv',  label: 'CSV',          hint: 'entities + edges' },
];

/**
 * Compact export-format dropdown menu.
 * Renders as a "EXPORT" button with a chevron; opens a list of formats; calls onExport with the chosen id.
 */
export function ExportMenu({
  options = DEFAULT_EXPORTS,
  onExport,
  buttonLabel = 'Export',
}: {
  options?: ExportOption[];
  onExport?: (formatId: string) => void;
  buttonLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          padding: '5px 8px', borderRadius: 3,
          background: 'transparent', border: '1px solid var(--line)',
          color: 'var(--fg-2)', fontSize: 11.5, fontWeight: 500,
          cursor: 'pointer',
        }}
      >
        <Icon name="download" size={12} />
        {buttonLabel}
        <Icon name="chevron-down" size={11} />
      </button>

      {open && (
        <div
          style={{
            position: 'absolute', top: 'calc(100% + 4px)', right: 0,
            minWidth: 200,
            background: 'var(--paper)',
            border: '1px solid var(--line)',
            borderRadius: 4,
            boxShadow: '0 8px 24px rgba(15,18,22,0.15)',
            zIndex: 90,
            overflow: 'hidden',
          }}
        >
          <div style={{
            padding: '6px 12px',
            borderBottom: '1px solid var(--line-soft)',
            fontFamily: 'var(--mono)', fontSize: 9.5, letterSpacing: '0.18em', color: 'var(--fg-3)', fontWeight: 600,
          }}>
            EXPORT AS
          </div>
          {options.map((opt) => (
            <button
              key={opt.id}
              onClick={() => { setOpen(false); onExport?.(opt.id); }}
              style={{
                display: 'flex', alignItems: 'center', width: '100%',
                padding: '8px 12px', textAlign: 'left',
                background: 'transparent', border: 'none', cursor: 'pointer',
                fontSize: 12, color: 'var(--ink)',
                borderBottom: '1px solid var(--line-soft)',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--paper-2)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{ flex: 1, fontWeight: 500 }}>{opt.label}</span>
              {opt.hint && (
                <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)' }}>
                  {opt.hint}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
