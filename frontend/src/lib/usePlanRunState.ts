'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { collectionPlansApi, type PlanExecutionStatus } from './api';

/**
 * One plan's run state, polled only while a run is in flight (`running`, which
 * includes queued and stopping runs), each tick awaited before the next.
 * `onRunEnded` fires once when an in-flight run stops, so the caller can
 * re-read what the run changed (source statuses, counts).
 */
export function usePlanRunState(planId: string | null, pollMs: number, onRunEnded?: () => void) {
  const [run, setRun] = useState<PlanExecutionStatus | null>(null);
  // The plan the state is for; a response for any other (a slow poll overtaken
  // by a new selection) is dropped.
  const forPlan = useRef<string | null>(null);
  const onRunEndedRef = useRef(onRunEnded);
  useEffect(() => { onRunEndedRef.current = onRunEnded; }, [onRunEnded]);

  const refresh = useCallback(async () => {
    const id = forPlan.current;
    if (!id) return;
    try {
      const res = await collectionPlansApi.executionStatus(id);
      if (forPlan.current === id) setRun(res.data);
    } catch {
      /* a failed poll is not evidence the run stopped: keep the last state */
    }
  }, []);

  useEffect(() => {
    forPlan.current = planId;
    setRun(null);
    if (planId) refresh();
  }, [planId, refresh]);

  const inFlight = run?.status === 'running';
  useEffect(() => {
    if (!inFlight) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      await refresh();
      if (!cancelled) timer = setTimeout(tick, pollMs);
    };
    timer = setTimeout(tick, pollMs);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [inFlight, refresh, pollMs]);

  const wasInFlight = useRef(false);
  useEffect(() => {
    if (wasInFlight.current && !inFlight && run) onRunEndedRef.current?.();
    wasInFlight.current = inFlight;
  }, [inFlight, run]);

  return { run, refresh };
}
