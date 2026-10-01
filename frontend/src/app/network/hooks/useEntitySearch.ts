'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { entitiesApi, totalFrom } from '@/lib/api';
import { createRequestSequencer, useDebouncedValue } from '../graphFilters';
import { ENTITY_PANEL_LIMIT, SEARCH_DEBOUNCE_MS, type Entity } from '../types';

/**
 * The browse panel's entity list: a (debounced) search and a type filter, and
 * the true total so the panel can say when it is showing a page.
 */
export function useEntitySearch(activeProject: { id: string } | null) {
  const [entities, setEntities] = useState<Entity[]>([]);
  // How many match in full, so the panel can say when it is showing a page.
  const [entityTotal, setEntityTotal] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedSearchQuery = useDebouncedValue(searchQuery, SEARCH_DEBOUNCE_MS);
  // Only the latest entity search may write the list; a slow response to an
  // earlier keystroke is dropped.
  const entitySeqRef = useRef(createRequestSequencer());
  const [typeFilter, setTypeFilter] = useState('All');

  const loadEntities = useCallback(async () => {
    if (!activeProject) return;
    const token = entitySeqRef.current.next();
    try {
      const res = await entitiesApi.search(
        activeProject.id,
        debouncedSearchQuery || undefined,
        typeFilter === 'All' ? undefined : typeFilter,
        ENTITY_PANEL_LIMIT,
      );
      if (!entitySeqRef.current.isCurrent(token)) return;
      setEntities(res.data);
      // The panel groups what it received under type headings, and those counts
      // read as totals. On a 5,486-entity project it was grouping the first 50
      // and captioning them "Organization (6)" beside a graph holding 156.
      setEntityTotal(totalFrom(res));
    } catch (e) {
      if (!entitySeqRef.current.isCurrent(token)) return;
      console.error('Failed to load entities', e);
    }
  }, [activeProject, debouncedSearchQuery, typeFilter]);

  // The entity list alone follows the (debounced) search and type filter.
  useEffect(() => {
    loadEntities();
  }, [loadEntities]);

  return { entities, entityTotal, searchQuery, setSearchQuery, setTypeFilter, loadEntities };
}
