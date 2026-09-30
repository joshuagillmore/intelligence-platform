/**
 * Key-entity ranking from `GET /graph/centrality`.
 *
 * The endpoint returns `{id, name, entity_type, degree}` rows, where `degree`
 * is a link count. There is no `centrality` field; reading one scored every
 * entity 0. `score` here is the degree scaled by the largest degree in the
 * list, so the best-connected entity scores 1 and the rest are relative to it.
 */
export interface KeyEntity {
  id?: string;
  name: string;
  entity_type: string;
  /** Number of links, as returned by the API. */
  degree: number;
  /** degree / max degree in the list, 0..1. */
  score: number;
}

export function rankByDegree(rows: unknown, limit = 10): KeyEntity[] {
  if (!Array.isArray(rows)) return [];
  const parsed = rows
    .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object')
    .map((r) => ({
      id: typeof r.id === 'string' ? r.id : undefined,
      name: typeof r.name === 'string' ? r.name : '',
      entity_type: typeof r.entity_type === 'string' ? r.entity_type : '',
      degree: typeof r.degree === 'number' && Number.isFinite(r.degree) ? r.degree : 0,
    }))
    .sort((a, b) => b.degree - a.degree)
    .slice(0, limit);
  const max = parsed.reduce((m, r) => Math.max(m, r.degree), 0);
  return parsed.map((r) => ({ ...r, score: max > 0 ? r.degree / max : 0 }));
}
