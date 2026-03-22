'use client';
import { useState, useCallback, useEffect, useRef } from 'react';

interface Props {
  /** All edges' first_seen/last_seen dates to compute the full range */
  edges: Array<{ first_seen?: string; last_seen?: string }>;
  /** Current temporal range filter: [start, end] as ISO strings, null = no filter */
  value: [string | null, string | null];
  /** Called when the analyst changes the range */
  onChange: (range: [string | null, string | null]) => void;
}

function toDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function formatDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function TemporalSlider({ edges, value, onChange }: Props) {
  // Compute the full date range from edges
  const { minDate, maxDate, hasTemporalData } = (() => {
    let min: Date | null = null;
    let max: Date | null = null;
    for (const e of edges) {
      const fs = toDate(e.first_seen);
      const ls = toDate(e.last_seen);
      if (fs) {
        if (!min || fs < min) min = fs;
        if (!max || fs > max) max = fs;
      }
      if (ls) {
        if (!min || ls < min) min = ls;
        if (!max || ls > max) max = ls;
      }
    }
    return { minDate: min, maxDate: max, hasTemporalData: min !== null && max !== null };
  })();

  const [isActive, setIsActive] = useState(value[0] !== null || value[1] !== null);
  const [startVal, setStartVal] = useState<string>(value[0] || (minDate ? formatDate(minDate) : ''));
  const [endVal, setEndVal] = useState<string>(value[1] || (maxDate ? formatDate(maxDate) : ''));
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Update local state when value prop changes
  useEffect(() => {
    if (value[0]) setStartVal(value[0].slice(0, 10));
    if (value[1]) setEndVal(value[1].slice(0, 10));
    setIsActive(value[0] !== null || value[1] !== null);
  }, [value]);

  const emitChange = useCallback((start: string, end: string, active: boolean) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (!active) {
        onChange([null, null]);
      } else {
        onChange([start || null, end || null]);
      }
    }, 300);
  }, [onChange]);

  function handleToggle() {
    const next = !isActive;
    setIsActive(next);
    if (next && minDate && maxDate) {
      const s = startVal || formatDate(minDate);
      const e = endVal || formatDate(maxDate);
      setStartVal(s);
      setEndVal(e);
      emitChange(s, e, true);
    } else {
      emitChange('', '', false);
    }
  }

  function handleStartChange(val: string) {
    setStartVal(val);
    emitChange(val, endVal, isActive);
  }

  function handleEndChange(val: string) {
    setEndVal(val);
    emitChange(startVal, val, isActive);
  }

  if (!hasTemporalData) return null;

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 bg-navy-800 border-t border-navy-600 text-xs">
      <button
        onClick={handleToggle}
        className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
          isActive ? 'bg-accent-blue text-white' : 'bg-navy-700 text-gray-400 hover:text-white'
        }`}
        title="Toggle temporal filter"
      >
        Temporal
      </button>
      {isActive && (
        <>
          <label className="text-gray-400">From</label>
          <input
            type="date"
            value={startVal}
            min={minDate ? formatDate(minDate) : undefined}
            max={endVal || (maxDate ? formatDate(maxDate) : undefined)}
            onChange={e => handleStartChange(e.target.value)}
            className="bg-navy-700 border border-navy-500 rounded px-2 py-0.5 text-xs text-gray-200 focus:outline-none focus:border-accent-blue"
          />
          <label className="text-gray-400">To</label>
          <input
            type="date"
            value={endVal}
            min={startVal || (minDate ? formatDate(minDate) : undefined)}
            max={maxDate ? formatDate(maxDate) : undefined}
            onChange={e => handleEndChange(e.target.value)}
            className="bg-navy-700 border border-navy-500 rounded px-2 py-0.5 text-xs text-gray-200 focus:outline-none focus:border-accent-blue"
          />
          <button
            onClick={() => {
              setIsActive(false);
              emitChange('', '', false);
            }}
            className="text-gray-500 hover:text-gray-300"
            title="Clear temporal filter"
          >
            Clear
          </button>
        </>
      )}
    </div>
  );
}
