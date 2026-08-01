import { describe, it, expect } from 'vitest';
import { orderProjects } from '@/lib/projectOrder';
import type { Project } from '@/lib/api';

function project(over: Partial<Project> & { id: string }): Project {
  return {
    name: over.id,
    description: '',
    classification_level: 'UNCLASSIFIED',
    priority: 'medium',
    status: 'active',
    entity_count: 0,
    relationship_count: 0,
    document_count: 0,
    ...over,
  } as Project;
}

const populatedOld = project({ id: 'old-populated', entity_count: 40, updated_at: '2026-01-01T00:00:00Z' });
const populatedMid = project({ id: 'mid-populated', document_count: 3, updated_at: '2026-04-01T00:00:00Z' });
const emptyNew = project({ id: 'new-empty', updated_at: '2026-07-31T00:00:00Z' });

const ids = (ps: Project[]) => ps.map(p => p.id);

describe('orderProjects', () => {
  it('leads with populated projects by default', () => {
    const got = orderProjects([emptyNew, populatedOld], { sortBy: 'modified', sortDir: 'desc' });
    expect(ids(got)).toEqual(['old-populated', 'new-empty']);
  });

  it('honours an explicit sort instead of burying the newest project', () => {
    // The defect: "populated first" applied regardless of the sort key, so
    // choosing "modified, newest first" still put every populated project above
    // the one just worked on, and the sort controls looked broken.
    const got = orderProjects([populatedOld, populatedMid, emptyNew], {
      sortBy: 'modified',
      sortDir: 'desc',
      sortChosen: true,
    });
    expect(ids(got)).toEqual(['new-empty', 'mid-populated', 'old-populated']);
  });

  it('still sorts within the populated group by default', () => {
    const got = orderProjects([populatedOld, populatedMid, emptyNew], {
      sortBy: 'modified',
      sortDir: 'desc',
    });
    expect(ids(got)).toEqual(['mid-populated', 'old-populated', 'new-empty']);
  });

  it('pins a just-created project above everything', () => {
    // New projects are empty, so without the pin the analyst cannot find what
    // they just made in a list of a hundred populated ones.
    const got = orderProjects([populatedOld, populatedMid, emptyNew], {
      sortBy: 'modified',
      sortDir: 'desc',
      pinnedId: 'new-empty',
    });
    expect(ids(got)[0]).toBe('new-empty');
  });

  it('keeps the pin from duplicating the project', () => {
    const got = orderProjects([populatedOld, emptyNew], {
      sortBy: 'name',
      sortDir: 'asc',
      pinnedId: 'new-empty',
    });
    expect(got).toHaveLength(2);
    expect(ids(got)).toEqual(['new-empty', 'old-populated']);
  });

  it('ignores a pin for a project that is not in the list', () => {
    const got = orderProjects([populatedOld], { sortBy: 'name', sortDir: 'asc', pinnedId: 'gone' });
    expect(ids(got)).toEqual(['old-populated']);
  });

  it('does not mutate the input array', () => {
    const input = [emptyNew, populatedOld];
    orderProjects(input, { sortBy: 'name', sortDir: 'desc' });
    expect(ids(input)).toEqual(['new-empty', 'old-populated']);
  });

  it('sorts by priority with unknown values last', () => {
    const critical = project({ id: 'crit', priority: 'critical', entity_count: 1 });
    const unknown = project({ id: 'unknown', priority: 'whatever', entity_count: 1 });
    const low = project({ id: 'low', priority: 'low', entity_count: 1 });
    const got = orderProjects([unknown, low, critical], { sortBy: 'priority', sortDir: 'asc' });
    expect(ids(got)).toEqual(['crit', 'low', 'unknown']);
  });
});
