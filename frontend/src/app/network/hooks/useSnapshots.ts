'use client';
import { useCallback, useRef, useState } from 'react';
import { snapshotsApi } from '@/lib/api';
import { createRequestSequencer } from '../graphFilters';
import type { Entity } from '../types';

/** A saved snapshot as `GET /snapshots` lists it. */
export interface SnapshotSummary {
  id: string;
  name: string;
  entity_count: number;
  created_at: string;
}

/**
 * Snapshots ("bins"): named sets of entity ids saved from the multi-selection.
 * Viewing one restricts the graph to its entities through the filter effect,
 * so it composes with the other filters and clearing it restores the graph.
 */
export function useSnapshots(activeProject: { id: string } | null, multiSelected: Entity[]) {
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [snapshotNameInput, setSnapshotNameInput] = useState('');
  const [snapshotFormOpen, setSnapshotFormOpen] = useState(false);
  const [activeSnapshotId, setActiveSnapshotId] = useState<string | null>(null);
  // The viewed snapshot's entity ids — an input to the filter effect like any
  // other filter, so it composes with them and clearing it restores the graph.
  const [activeSnapshotIds, setActiveSnapshotIds] = useState<Set<string> | null>(null);
  const snapshotSeqRef = useRef(createRequestSequencer());

  const loadSnapshots = useCallback(async () => {
    if (!activeProject) return;
    try {
      const res = await snapshotsApi.list(activeProject.id);
      setSnapshots(res.data.snapshots || []);
    } catch (e) {
      console.error('Failed to load snapshots', e);
    }
  }, [activeProject]);

  async function saveSnapshot() {
    if (!activeProject || !snapshotNameInput.trim() || multiSelected.length === 0) return;
    try {
      await snapshotsApi.create({
        project_id: activeProject.id,
        name: snapshotNameInput.trim(),
        entity_ids: multiSelected.map(e => e.id),
      });
      setSnapshotNameInput('');
      setSnapshotFormOpen(false);
      loadSnapshots();
    } catch {
      console.error('Failed to save snapshot');
    }
  }

  async function loadSnapshotView(snapshotId: string) {
    const token = snapshotSeqRef.current.next();
    try {
      const res = await snapshotsApi.get(snapshotId);
      // A slower load of a previously clicked snapshot must not win.
      if (!snapshotSeqRef.current.isCurrent(token)) return;
      setActiveSnapshotIds(new Set<string>(res.data.entity_ids || []));
      setActiveSnapshotId(snapshotId);
    } catch {
      console.error('Failed to load snapshot');
    }
  }

  function clearSnapshotView() {
    snapshotSeqRef.current.next(); // and a load still in flight must not re-apply it
    setActiveSnapshotId(null);
    setActiveSnapshotIds(null);
  }

  async function deleteSnapshot(snapshotId: string) {
    try {
      await snapshotsApi.delete(snapshotId);
      if (activeSnapshotId === snapshotId) clearSnapshotView();
      loadSnapshots();
    } catch {
      console.error('Failed to delete snapshot');
    }
  }

  return {
    snapshots,
    snapshotNameInput, setSnapshotNameInput,
    snapshotFormOpen, setSnapshotFormOpen,
    activeSnapshotId,
    activeSnapshotIds,
    loadSnapshots,
    saveSnapshot,
    loadSnapshotView,
    clearSnapshotView,
    deleteSnapshot,
  };
}
