'use client';
import { useState } from 'react';
import type { EntityStats, GraphStats, SortKey } from '../types';

/** The Statistics tab's sortable centrality table, and each metric's maximum. */
export function useStatisticsTable(stats: GraphStats | null) {
  const [sortKey, setSortKey] = useState<SortKey>('pagerank');
  const [sortAsc, setSortAsc] = useState(false);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function getSortedStats(): EntityStats[] {
    if (!stats?.entity_statistics) return [];
    const arr = [...stats.entity_statistics];
    arr.sort((a, b) => {
      let va: string | number = a[sortKey];
      let vb: string | number = b[sortKey];
      if (typeof va === 'string' && typeof vb === 'string') {
        return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      va = Number(va); vb = Number(vb);
      return sortAsc ? va - vb : vb - va;
    });
    return arr;
  }

  function getMaxValues(): Record<string, number> {
    if (!stats?.entity_statistics || stats.entity_statistics.length === 0) {
      return { degree: 0, betweenness: 0, eigenvector: 0, pagerank: 0, closeness: 0 };
    }
    const es = stats.entity_statistics;
    return {
      degree: Math.max(...es.map(e => e.degree)),
      betweenness: Math.max(...es.map(e => e.betweenness)),
      eigenvector: Math.max(...es.map(e => e.eigenvector)),
      pagerank: Math.max(...es.map(e => e.pagerank)),
      closeness: Math.max(...es.map(e => e.closeness)),
    };
  }

  const sortArrow = (key: SortKey) => sortKey === key ? (sortAsc ? ' ▲' : ' ▼') : '';

  return { handleSort, sortedStats: getSortedStats(), maxVals: getMaxValues(), sortArrow };
}
