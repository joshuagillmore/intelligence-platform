'use client';
import { useEffect, useState } from 'react';
import type { HistogramData } from '@/components/TemporalHistogram';
import { timelineApi } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';

export type HistogramBucket = 'day' | 'month' | 'year';

/** The event-date distribution behind the chronology brush, per bucket size. */
export function useHistogram(activeProject: { id: string } | null) {
  const [histogramBucket, setHistogramBucket] = useState<HistogramBucket>('month');
  const [histogram, setHistogram] = useState<HistogramData | null>(null);
  const [histogramLoading, setHistogramLoading] = useState(false);
  const [histogramError, setHistogramError] = useState<string | null>(null);

  // Event-date distribution for the chronology brush. Re-fetched when the
  // bucket changes; the selection is cleared because bin keys differ between
  // buckets ("2026-03" is not a valid key once bucketing by year).
  useEffect(() => {
    if (!activeProject) {
      setHistogram(null);
      return;
    }
    let cancelled = false;
    setHistogramLoading(true);
    setHistogramError(null);
    timelineApi.histogram(activeProject.id, histogramBucket)
      .then(res => { if (!cancelled) setHistogram(res.data as HistogramData); })
      .catch((err: unknown) => {
        if (cancelled) return;
        setHistogram(null);
        setHistogramError(getErrorMessage(err));
      })
      .finally(() => { if (!cancelled) setHistogramLoading(false); });
    return () => { cancelled = true; };
  }, [activeProject, histogramBucket]);

  return { histogramBucket, setHistogramBucket, histogram, histogramLoading, histogramError };
}
