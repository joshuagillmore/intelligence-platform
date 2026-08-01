import type { Project } from './api';

export type SortKey = 'name' | 'created' | 'modified' | 'priority';
export type SortDir = 'asc' | 'desc';

const PRIORITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

const hasContent = (p: Project) => p.entity_count > 0 || p.document_count > 0;

export interface OrderOptions {
  sortBy: SortKey;
  sortDir: SortDir;
  /** Whether the analyst picked the sort themselves. Until they do, the list
   *  leads with projects that have content; after, their choice wins outright. */
  sortChosen?: boolean;
  /** A project just created, kept visible wherever the ordering would put it.
   *  New projects are empty, and empty projects sort last, so without this the
   *  thing the analyst just made lands at the bottom of a long list. */
  pinnedId?: string | null;
}

/** Order the project list for the dashboard.
 *
 *  Leading with populated projects is a sensible default on a landing page full
 *  of placeholders, but it used to apply regardless of the sort key — so an
 *  explicit "modified, newest first" still put every populated project above
 *  the newest one, and the sort controls looked broken.
 */
export function orderProjects(projects: Project[], opts: OrderOptions): Project[] {
  const { sortBy, sortDir, sortChosen = false, pinnedId = null } = opts;

  const sorted = [...projects].sort((a, b) => {
    switch (sortBy) {
      case 'name':
        return a.name.localeCompare(b.name);
      case 'priority':
        return (PRIORITY_ORDER[a.priority] ?? 99) - (PRIORITY_ORDER[b.priority] ?? 99);
      case 'created':
        return (a.created_at || '').localeCompare(b.created_at || '');
      case 'modified':
        return (a.updated_at || a.created_at || '').localeCompare(b.updated_at || b.created_at || '');
      default:
        return 0;
    }
  });

  const ordered = sortDir === 'desc' ? sorted.reverse() : sorted;
  const ranked = sortChosen
    ? ordered
    : [...ordered.filter(hasContent), ...ordered.filter(p => !hasContent(p))];

  const pinned = pinnedId ? ranked.find(p => String(p.id) === pinnedId) : undefined;
  return pinned ? [pinned, ...ranked.filter(p => p !== pinned)] : ranked;
}
