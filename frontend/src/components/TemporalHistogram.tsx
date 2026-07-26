'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Distribution of *when things happened* across the graph, with a drag-to-select
 * range that filters the network view.
 *
 * Deliberately built on entity `event_datetime` — the date extraction resolved
 * from the source text — and never on ingestion time. A histogram of ingestion
 * time is a picture of when the crawler ran, which is what the control this
 * replaces was showing.
 *
 * Two things the data forces:
 *
 * - Most extracted dates are month- or year-precision. Bucketing those by day
 *   stacks every one of them on the 1st, so the bucket size is chosen from the
 *   span and the bars are labelled with the precision actually available.
 * - Most entities carry no date at all. Hiding them on any selection would
 *   empty the graph, so undated entities stay visible and are dimmed instead —
 *   the toggle makes that explicit rather than leaving the analyst to infer it.
 */

export interface HistogramBin {
  key: string;
  count: number;
  by_type?: Record<string, number>;
}

export interface HistogramData {
  bucket: 'day' | 'month' | 'year';
  bins: HistogramBin[];
  dated: number;
  undated: number;
  earliest: string | null;
  latest: string | null;
}

interface Props {
  data: HistogramData | null;
  loading?: boolean;
  /** Selected range as [startKey, endKey] over bin keys; null = no filter. */
  value: [string | null, string | null];
  onChange: (range: [string | null, string | null]) => void;
  /** Whether undated entities are hidden while a range is selected. */
  hideUndated: boolean;
  onHideUndatedChange: (hide: boolean) => void;
  onBucketChange?: (bucket: 'day' | 'month' | 'year') => void;
}

const BUCKET_LABEL: Record<string, string> = {
  day: 'by day',
  month: 'by month',
  year: 'by year',
};

/** Human label for a bin key: "2026-03" -> "Mar 2026". */
function binLabel(key: string, bucket: string): string {
  if (bucket === 'year') return key;
  const [y, m, d] = key.split('-');
  const month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m) - 1] ?? m;
  return bucket === 'month' ? `${month} ${y}` : `${d} ${month} ${y}`;
}

export default function TemporalHistogram({
  data, loading, value, onChange, hideUndated, onHideUndatedChange, onBucketChange,
}: Props) {
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragTo, setDragTo] = useState<number | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  // Memoised: a fresh `[]` each render would re-fire every memo below it.
  const bins = useMemo(() => data?.bins ?? [], [data]);
  const maxCount = useMemo(
    () => bins.reduce((m, b) => Math.max(m, b.count), 0),
    [bins],
  );

  // Selected range expressed as bin indices, for rendering.
  const [selStart, selEnd] = useMemo(() => {
    if (dragFrom !== null && dragTo !== null) {
      return [Math.min(dragFrom, dragTo), Math.max(dragFrom, dragTo)];
    }
    const [a, b] = value;
    if (!a || !b) return [-1, -1];
    const i = bins.findIndex(x => x.key === a);
    const j = bins.findIndex(x => x.key === b);
    return [i, j];
  }, [dragFrom, dragTo, value, bins]);

  const commit = useCallback((from: number, to: number) => {
    const lo = Math.min(from, to);
    const hi = Math.max(from, to);
    if (lo < 0 || hi >= bins.length) return;
    onChange([bins[lo].key, bins[hi].key]);
  }, [bins, onChange]);

  // Pointer release anywhere ends the drag — releasing outside the track
  // otherwise leaves it stuck in a selecting state.
  useEffect(() => {
    if (dragFrom === null) return;
    const end = () => {
      if (dragFrom !== null && dragTo !== null) commit(dragFrom, dragTo);
      setDragFrom(null);
      setDragTo(null);
    };
    window.addEventListener('pointerup', end);
    return () => window.removeEventListener('pointerup', end);
  }, [dragFrom, dragTo, commit]);

  const hasSelection = value[0] !== null && value[1] !== null;
  const total = (data?.dated ?? 0) + (data?.undated ?? 0);

  if (loading) {
    return (
      <div className="px-3 py-2 text-xs text-gray-500 border-t border-navy-700">
        Loading event dates…
      </div>
    );
  }

  if (!data || data.dated === 0) {
    return (
      <div className="px-3 py-2 text-xs text-gray-500 border-t border-navy-700">
        No dated events in this project — nothing to plot over time.
        {total > 0 && (
          <span className="ml-1 text-gray-600">
            ({total} entities, none carrying a date from their source)
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="border-t border-navy-700 bg-navy-800/60 px-3 py-2 select-none">
      <div className="flex items-center gap-3 mb-1.5 text-xs">
        <span className="font-medium text-gray-300">Events over time</span>

        <span className="text-gray-500">
          {data.dated} dated
          {data.undated > 0 && <span className="text-gray-600"> · {data.undated} undated</span>}
        </span>

        {onBucketChange && (
          <div className="flex items-center gap-1">
            {(['day', 'month', 'year'] as const).map(b => (
              <button
                key={b}
                onClick={() => onBucketChange(b)}
                className={`px-1.5 py-0.5 rounded text-[11px] transition-colors ${
                  data.bucket === b
                    ? 'bg-accent-blue text-white'
                    : 'bg-navy-700 text-gray-400 hover:text-white'
                }`}
                title={`Bucket ${BUCKET_LABEL[b]}`}
              >
                {b}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1" />

        {hasSelection && (
          <>
            <label className="flex items-center gap-1 text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={hideUndated}
                onChange={e => onHideUndatedChange(e.target.checked)}
                className="accent-accent-blue"
              />
              Hide undated
            </label>
            <span className="text-accent-blue font-medium">
              {binLabel(value[0]!, data.bucket)} – {binLabel(value[1]!, data.bucket)}
            </span>
            <button
              onClick={() => onChange([null, null])}
              className="text-gray-500 hover:text-gray-300"
              title="Clear the time filter"
            >
              Clear
            </button>
          </>
        )}
      </div>

      <div
        ref={trackRef}
        className="flex items-end gap-px h-14 cursor-crosshair"
        role="group"
        aria-label="Filter the graph by when events happened"
      >
        {bins.map((bin, i) => {
          const inRange = selStart >= 0 && i >= selStart && i <= selEnd;
          const height = maxCount > 0 ? Math.max(2, (bin.count / maxCount) * 100) : 2;
          return (
            <button
              key={bin.key}
              type="button"
              onPointerDown={() => { setDragFrom(i); setDragTo(i); }}
              onPointerEnter={() => { if (dragFrom !== null) setDragTo(i); }}
              onFocus={() => { /* keyboard users select via Enter below */ }}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  commit(i, i);
                }
              }}
              className={`flex-1 min-w-[2px] rounded-t transition-colors focus:outline-none focus:ring-1 focus:ring-accent-blue ${
                inRange || selStart < 0
                  ? 'bg-accent-blue hover:bg-accent-blue/80'
                  : 'bg-navy-600 hover:bg-navy-500'
              }`}
              style={{ height: `${height}%` }}
              title={`${binLabel(bin.key, data.bucket)} — ${bin.count} event${bin.count === 1 ? '' : 's'}`}
              aria-label={`${binLabel(bin.key, data.bucket)}, ${bin.count} events`}
            />
          );
        })}
      </div>

      {bins.length > 1 && (
        <div className="flex justify-between mt-1 text-[10px] text-gray-600">
          <span>{binLabel(bins[0].key, data.bucket)}</span>
          <span>{binLabel(bins[bins.length - 1].key, data.bucket)}</span>
        </div>
      )}
    </div>
  );
}
