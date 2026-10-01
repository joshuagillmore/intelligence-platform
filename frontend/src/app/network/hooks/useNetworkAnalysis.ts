'use client';
import { useState } from 'react';
import { graphApi } from '@/lib/api';
import type { EgoNetworkData, InfluenceResult } from '../types';

/** On-demand network analysis: an entity's ego network and influence propagation. */
export function useNetworkAnalysis(activeProject: { id: string } | null) {
  const [egoNetwork, setEgoNetwork] = useState<EgoNetworkData | null>(null);
  const [egoLoading, setEgoLoading] = useState(false);
  const [egoHops, setEgoHops] = useState(2);
  const [influenceResult, setInfluenceResult] = useState<InfluenceResult | null>(null);
  const [influenceLoading, setInfluenceLoading] = useState(false);
  const [influenceSteps, setInfluenceSteps] = useState(3);
  const [influenceThreshold, setInfluenceThreshold] = useState(0.3);

  async function loadEgoNetwork(entityId: string) {
    if (!activeProject) return;
    setEgoLoading(true);
    try {
      const res = await graphApi.egoNetwork(entityId, activeProject.id, egoHops);
      setEgoNetwork(res.data);
    } catch (e) {
      console.error('Failed to load ego network', e);
    } finally {
      setEgoLoading(false);
    }
  }

  async function runInfluencePropagation(seedIds: string[]) {
    if (!activeProject || seedIds.length === 0) return;
    setInfluenceLoading(true);
    try {
      const res = await graphApi.influence(activeProject.id, seedIds, influenceSteps, influenceThreshold);
      setInfluenceResult(res.data);
    } catch (e) {
      console.error('Failed to run influence propagation', e);
    } finally {
      setInfluenceLoading(false);
    }
  }

  return {
    egoNetwork,
    egoLoading,
    egoHops, setEgoHops,
    loadEgoNetwork,
    influenceResult,
    influenceLoading,
    influenceSteps, setInfluenceSteps,
    influenceThreshold, setInfluenceThreshold,
    runInfluencePropagation,
  };
}
