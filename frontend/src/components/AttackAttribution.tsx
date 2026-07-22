'use client';
import React, { useCallback, useEffect, useState } from 'react';
import { attackApi, AttackAttribution as AttackAttributionData } from '@/lib/api';
import LoadingSpinner from '@/components/LoadingSpinner';

const ACCENT = '#adc6ff';
const CARD_BG = '#1a1f2e';
const BORDER = '#2f3444';

/**
 * Candidate threat-actor attribution by ATT&CK technique overlap.
 *
 * Ranks ATT&CK Groups that share observed techniques with the project. This is
 * deliberately framed as *suggestive overlap, not confirmed attribution* — the
 * signal is "these groups are known to use techniques you've observed", which is
 * a lead to investigate, not a conclusion.
 *
 * `onTechniqueClick` deep-links a shared technique into the ATT&CK matrix's
 * technique drawer (the parent switches to the ATT&CK tab).
 */
export default function AttackAttribution({
  projectId,
  onTechniqueClick,
}: {
  projectId: string;
  onTechniqueClick?: (techniqueId: string) => void;
}) {
  const [data, setData] = useState<AttackAttributionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(false);
    try {
      const res = await attackApi.attribution(projectId);
      setData(res.data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="rounded-lg" style={{ backgroundColor: CARD_BG, border: `1px solid ${BORDER}` }}>
      {/* Header */}
      <div className="px-4 py-3 flex items-start justify-between gap-3" style={{ borderBottom: `1px solid ${BORDER}` }}>
        <div>
          <h3 className="text-[10px] uppercase tracking-widest font-bold text-gray-400 flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[15px]" style={{ color: ACCENT }}>
              hub
            </span>
            Candidate Attribution
          </h3>
          <p className="text-[11px] text-gray-500 mt-1 max-w-md">
            Suggestive technique overlap with known ATT&amp;CK Groups &mdash; a lead to investigate,{' '}
            <span className="text-gray-400">not confirmed attribution</span>.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] rounded-md font-medium transition-colors disabled:opacity-50 flex-shrink-0"
          style={{ backgroundColor: 'transparent', color: ACCENT, border: `1px solid ${BORDER}` }}
          title="Recompute candidate attribution from observed techniques"
          aria-label="Refresh candidate attribution"
        >
          <span className={`material-symbols-outlined text-[14px] ${loading ? 'animate-spin' : ''}`}>refresh</span>
          Refresh
        </button>
      </div>

      <div className="p-4">
        {loading ? (
          <LoadingSpinner size="md" />
        ) : error ? (
          <div className="text-center py-6">
            <p className="text-sm text-gray-400">Couldn&apos;t load attribution candidates.</p>
            <button
              onClick={load}
              className="mt-3 px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
              style={{ backgroundColor: 'rgba(173,198,255,0.15)', color: ACCENT, border: '1px solid rgba(173,198,255,0.3)' }}
            >
              Retry
            </button>
          </div>
        ) : !data || data.observed_total === 0 ? (
          // No observed techniques mapped yet — attribution can't be computed.
          <div className="text-center py-6">
            <span className="material-symbols-outlined text-[32px]" style={{ color: '#4b5563' }}>
              group_off
            </span>
            <p className="text-sm text-gray-400 mt-2">No observed ATT&amp;CK techniques yet.</p>
            <p className="text-xs text-gray-600 mt-1 max-w-sm mx-auto">
              Map this project&apos;s TTPs to ATT&amp;CK (matrix tab &rarr; &ldquo;Map TTPs&rdquo;) to enable
              candidate attribution.
            </p>
          </div>
        ) : data.groups.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-sm text-gray-400">
              No ATT&amp;CK Groups share techniques with the {data.observed_total} observed technique
              {data.observed_total === 1 ? '' : 's'}.
            </p>
          </div>
        ) : (
          <>
            <p className="text-[11px] text-gray-500 mb-3">
              Ranked by overlap with <span className="text-gray-300">{data.observed_total}</span> observed technique
              {data.observed_total === 1 ? '' : 's'}. Coverage = shared &divide; observed.
            </p>
            <div className="space-y-2">
              {data.groups.map((group, idx) => {
                const isOpen = expanded[group.id];
                const pct = Math.round((group.coverage || 0) * 100);
                return (
                  <div
                    key={group.id}
                    className="rounded-lg overflow-hidden"
                    style={{ backgroundColor: '#161b28', border: `1px solid ${BORDER}` }}
                  >
                    <button
                      onClick={() => setExpanded((prev) => ({ ...prev, [group.id]: !prev[group.id] }))}
                      className="w-full text-left px-3 py-2.5 flex items-center gap-3 transition-colors hover:brightness-110"
                      aria-expanded={!!isOpen}
                      aria-label={`${isOpen ? 'Hide' : 'Show'} shared techniques for ${group.name}`}
                    >
                      <span className="text-xs font-bold text-gray-600 w-4 flex-shrink-0 text-right">{idx + 1}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-white truncate">{group.name}</span>
                          <span className="font-mono text-[10px] flex-shrink-0" style={{ color: ACCENT }}>
                            {group.id}
                          </span>
                        </div>
                        {/* Coverage bar */}
                        <div className="flex items-center gap-2 mt-1.5">
                          <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: BORDER }}>
                            <div
                              className="h-1.5 rounded-full"
                              style={{ width: `${pct}%`, backgroundColor: ACCENT }}
                            />
                          </div>
                          <span className="text-[10px] text-gray-400 flex-shrink-0 tabular-nums">{pct}%</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end flex-shrink-0">
                        <span className="text-sm font-bold" style={{ color: ACCENT }}>
                          {group.shared_count}
                        </span>
                        <span className="text-[9px] uppercase tracking-wider text-gray-600">shared</span>
                      </div>
                      <span className="material-symbols-outlined text-[18px] text-gray-500 flex-shrink-0">
                        {isOpen ? 'expand_less' : 'expand_more'}
                      </span>
                    </button>

                    {/* Shared technique list */}
                    {isOpen && (
                      <div className="px-3 pb-3 pt-1" style={{ borderTop: `1px solid ${BORDER}` }}>
                        {group.shared_techniques.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {group.shared_techniques.map((t) => (
                              <button
                                key={t.id}
                                onClick={() => onTechniqueClick?.(t.id)}
                                disabled={!onTechniqueClick}
                                className="flex items-center gap-1 text-[10px] px-2 py-1 rounded transition-colors hover:brightness-125 disabled:cursor-default"
                                style={{
                                  backgroundColor: 'rgba(173,198,255,0.12)',
                                  color: ACCENT,
                                  border: '1px solid rgba(173,198,255,0.25)',
                                }}
                                title={onTechniqueClick ? `Open ${t.id} — ${t.name} in the matrix` : `${t.id} — ${t.name}`}
                              >
                                <span className="font-mono">{t.id}</span>
                                <span className="text-gray-300 max-w-[160px] truncate">{t.name}</span>
                                {onTechniqueClick && (
                                  <span className="material-symbols-outlined text-[12px]">north_east</span>
                                )}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-gray-600 mt-2">No shared technique detail available.</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
