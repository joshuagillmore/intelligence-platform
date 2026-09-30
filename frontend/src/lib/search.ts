/**
 * Reading a `GET /search` (keyword search) body.
 *
 * Keyword search matches entity names only (not document text) and returns a
 * capped page. `count` is the rows on this page, `total` the true number of
 * matches, `truncated` whether the page holds fewer than all of them. Rows
 * arrive either grouped (`entities`, `documents`, `reports`) or as one flat
 * `results` list; both are read into the grouped shape the page renders.
 */
export interface SearchEntry {
  id: string;
  name: string;
  entity_type: string;
  reliability?: string;
  report_type?: string;
  preview?: string;
}

export interface SearchResults {
  entities: SearchEntry[];
  documents: SearchEntry[];
  reports: SearchEntry[];
  /** Rows on this page. */
  count: number;
  /** Every match; never less than `count`. */
  total: number;
  truncated: boolean;
}

function rows(value: unknown): SearchEntry[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (r): r is SearchEntry => !!r && typeof r === 'object' && typeof (r as SearchEntry).id === 'string',
  );
}

export function readSearch(data: unknown): SearchResults {
  const body = (data && typeof data === 'object' && !Array.isArray(data) ? data : null) as
    | Record<string, unknown>
    | null;
  const grouped = !!body && (Array.isArray(body.entities) || Array.isArray(body.documents) || Array.isArray(body.reports));
  if (!body || (!grouped && !Array.isArray(body.results))) {
    throw new Error('Unexpected search response shape.');
  }

  let entities: SearchEntry[];
  let documents: SearchEntry[];
  let reports: SearchEntry[];
  if (grouped) {
    entities = rows(body.entities);
    documents = rows(body.documents);
    reports = rows(body.reports);
  } else {
    const all = rows(body.results);
    documents = all.filter((r) => r.entity_type === 'Document');
    reports = all.filter((r) => r.entity_type === 'Report');
    entities = all.filter((r) => r.entity_type !== 'Document' && r.entity_type !== 'Report');
  }

  const shown = entities.length + documents.length + reports.length;
  const count = typeof body.count === 'number' && Number.isFinite(body.count) ? Math.max(body.count, shown) : shown;
  const total = typeof body.total === 'number' && Number.isFinite(body.total) ? Math.max(body.total, count) : count;
  const truncated = body.truncated === true || total > count;
  return { entities, documents, reports, count, total, truncated };
}
