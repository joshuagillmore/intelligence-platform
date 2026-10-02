'use client';
import { useEffect, useRef, useState } from 'react';
import { documentsApi, entitiesApi, readEntityDocuments, watchlistApi, type EntityDocument } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';
import { createRequestSequencer } from '../graphFilters';
import { EVIDENCE_DOC_LIMIT, entityFromRecord, type Entity, type Relationship } from '../types';

/** A source document in the evidence chain, with its reliability grade. */
export type EvidenceDocument = EntityDocument & { reliability_rating: string };

/**
 * The selected entity and everything read for it: its relationships, the
 * documents that mention it (the evidence chain) and whether it is watched.
 *
 * Each selection takes a token; a response for an entity the analyst has since
 * moved away from is dropped, so nothing of the previous entity's shows under
 * the next one's header. `onSelect` runs as a selection starts, for the view
 * state that resets with it.
 */
export function useEntitySelection(activeProject: { id: string } | null, onSelect: () => void) {
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null);
  const [entityRelationships, setEntityRelationships] = useState<Relationship[]>([]);
  const [relationshipsError, setRelationshipsError] = useState<string | null>(null);
  // Each selection takes a token; responses for an entity the analyst has since
  // moved away from (details, evidence, watchlist status) are dropped.
  const selectSeqRef = useRef(createRequestSequencer());
  // The selected entity's id, readable from callbacks that outlive a render
  // (an enrichment run finishing after the analyst moved on).
  const selectedEntityIdRef = useRef<string | null>(null);
  useEffect(() => {
    selectedEntityIdRef.current = selectedEntity?.id ?? null;
  }, [selectedEntity]);
  const [isWatchlisted, setIsWatchlisted] = useState(false);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  // Evidence chain: source documents for selected entity
  const [evidenceDocs, setEvidenceDocs] = useState<EvidenceDocument[]>([]);
  const [evidenceTotal, setEvidenceTotal] = useState(0);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  // Relationship evidence (rel.evidence is persisted on the edge — just toggle visibility, no fetch)
  const [relEvidenceOpen, setRelEvidenceOpen] = useState<Record<number, boolean>>({});

  // Relationship evidence is persisted on the edge itself (rel.evidence) — just toggle the
  // collapsible open/closed. No document fetching / client-side co-occurrence search.
  function toggleRelEvidence(relIndex: number) {
    setRelEvidenceOpen(prev => ({ ...prev, [relIndex]: !prev[relIndex] }));
  }

  async function checkWatchlistStatus(entityId: string, isCurrent: () => boolean) {
    if (!activeProject) return;
    try {
      const res = await watchlistApi.list(activeProject.id);
      if (!isCurrent()) return;
      // GET /watchlist returns {watched_entities: [{id, name, ...}], count}.
      // Reading the body as an array made every entity look unwatched, so
      // "Remove from Watchlist" could never appear.
      const watched: Array<{ id: string }> = res.data?.watched_entities ?? [];
      setIsWatchlisted(watched.some(e => e.id === entityId));
    } catch {
      if (isCurrent()) setIsWatchlisted(false);
    }
  }

  async function selectEntity(entity: Entity) {
    const seq = selectSeqRef.current;
    const token = seq.next();
    const isCurrent = () => seq.isCurrent(token);
    setSelectedEntity(entity);
    onSelect();
    // Nothing of the previous entity's may show under this one's header.
    setEntityRelationships([]);
    setRelationshipsError(null);
    setIsWatchlisted(false);
    setEvidenceDocs([]);
    setEvidenceTotal(0);
    setEvidenceError(null);
    setRelEvidenceOpen({});
    checkWatchlistStatus(entity.id, isCurrent);
    try {
      const res = await entitiesApi.get(entity.id);
      if (!isCurrent()) return;
      setEntityRelationships(res.data.relationships || []);
      if (res.data.entity) {
        setSelectedEntity(entityFromRecord(res.data.entity));
      }
    } catch (e) {
      if (!isCurrent()) return;
      console.error('Failed to load entity details', e);
      setRelationshipsError(getErrorMessage(e));
    }
    // Load evidence chain: the documents that mention this entity, in one call
    // (its MENTIONS edges), plus the project's document list for the
    // reliability grades that payload does not carry. A failure shows as an
    // error, not as "no source documents".
    if (activeProject) {
      setEvidenceLoading(true);
      try {
        const [mentionsRes, docsRes] = await Promise.all([
          entitiesApi.documents(entity.id, EVIDENCE_DOC_LIMIT),
          documentsApi.list(activeProject.id).catch(() => null),
        ]);
        if (!isCurrent()) return;
        const page = readEntityDocuments(mentionsRes.data);
        const listed: Array<{ id: string; reliability_rating?: string }> = docsRes?.data?.documents || [];
        const ratings = new Map(listed.map(d => [d.id, d.reliability_rating || '']));
        setEvidenceDocs(page.documents.map(doc => ({ ...doc, reliability_rating: ratings.get(doc.id) || '' })));
        setEvidenceTotal(page.total);
      } catch (e) {
        if (isCurrent()) setEvidenceError(getErrorMessage(e));
      } finally {
        if (isCurrent()) setEvidenceLoading(false);
      }
    }
  }

  // After an enrichment run: re-read the entity that was enriched, and only
  // while it is still the one on screen. A run takes a while; re-selecting the
  // enriched entity after the analyst had moved on yanked them back to it.
  async function refreshEnrichedEntity(entityId: string) {
    if (selectedEntityIdRef.current !== entityId) return;
    try {
      const res = await entitiesApi.get(entityId);
      if (selectedEntityIdRef.current !== entityId) return;
      if (res.data.entity) setSelectedEntity(entityFromRecord(res.data.entity));
      setEntityRelationships(res.data.relationships || []);
      setRelationshipsError(null);
    } catch (e) {
      console.error('Failed to refresh enriched entity', e);
    }
  }

  async function toggleWatchlist() {
    if (!activeProject || !selectedEntity) return;
    setWatchlistLoading(true);
    try {
      if (isWatchlisted) {
        await watchlistApi.remove(activeProject.id, selectedEntity.id);
        setIsWatchlisted(false);
      } else {
        await watchlistApi.add(activeProject.id, selectedEntity.id);
        setIsWatchlisted(true);
      }
    } catch {
      console.error('Failed to toggle watchlist');
    } finally {
      setWatchlistLoading(false);
    }
  }

  /** Drop the selection's loads still in flight (an edge was selected instead). */
  function abandonSelection() {
    selectSeqRef.current.next();
  }

  return {
    selectedEntity, setSelectedEntity,
    entityRelationships,
    relationshipsError,
    isWatchlisted,
    watchlistLoading,
    evidenceDocs,
    evidenceTotal,
    evidenceError,
    evidenceLoading,
    relEvidenceOpen,
    toggleRelEvidence,
    selectEntity,
    refreshEnrichedEntity,
    toggleWatchlist,
    abandonSelection,
  };
}
