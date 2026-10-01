'use client';
import { useState } from 'react';
import { entityMgmtApi } from '@/lib/api';
import type { Entity } from '../types';

interface EntityActionSources {
  activeProject: { id: string } | null;
  selectedEntity: Entity | null;
  setSelectedEntity: (entity: Entity) => void;
  multiSelected: Entity[];
  setMultiSelected: (entities: Entity[]) => void;
  setAiResult: (result: string) => void;
  setTypeDropdownOpen: (open: boolean) => void;
  /** Re-read what an edit changes. */
  reloadGraph: () => void;
  reloadEntities: () => void;
  reloadStatistics: () => void;
}

/** Edits to the graph from the view: retype the selected entity, merge the multi-selection. */
export function useEntityActions({
  activeProject, selectedEntity, setSelectedEntity, multiSelected, setMultiSelected, setAiResult, setTypeDropdownOpen,
  reloadGraph, reloadEntities, reloadStatistics,
}: EntityActionSources) {
  const [mergeModalOpen, setMergeModalOpen] = useState(false);
  const [mergePrimaryId, setMergePrimaryId] = useState<string>('');

  async function changeEntityType(newType: string) {
    if (!selectedEntity) return;
    try {
      await entityMgmtApi.updateType(selectedEntity.id, newType);
      setSelectedEntity({ ...selectedEntity, entity_type: newType });
      setTypeDropdownOpen(false);
      reloadGraph();
      reloadEntities();
    } catch {
      console.error('Failed to update entity type');
    }
  }

  async function mergeEntities() {
    if (!activeProject || multiSelected.length < 2 || !mergePrimaryId) return;
    try {
      const mergeIds = multiSelected.filter(e => e.id !== mergePrimaryId).map(e => e.id);
      await entityMgmtApi.merge(mergePrimaryId, mergeIds, activeProject.id);
      setMergeModalOpen(false);
      setMergePrimaryId('');
      setMultiSelected([]);
      reloadGraph();
      reloadEntities();
      reloadStatistics();
      setAiResult('Entities merged successfully.');
    } catch {
      setAiResult('Failed to merge entities.');
    }
  }

  return {
    mergeModalOpen, setMergeModalOpen,
    mergePrimaryId, setMergePrimaryId,
    changeEntityType,
    mergeEntities,
  };
}
