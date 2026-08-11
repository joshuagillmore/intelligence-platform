import { describe, it, expect } from 'vitest';

type Ev = { entity_type: string; event_type: string };

/** Mirrors the filter in src/app/timeline/page.tsx. */
const isDated = (e: Ev) => e.event_type === 'event';
const visible = (events: Ev[], types: Set<string>, datedOnly: boolean) =>
  events.filter(e => types.has(e.entity_type)).filter(e => !datedOnly || isDated(e));

const ALL = new Set(['Event', 'Organization', 'Location']);

// Shaped like the live project: 5 dated events among 495 entities whose
// timestamp is simply when collection added them.
const sample: Ev[] = [
  { entity_type: 'Event', event_type: 'event' },
  { entity_type: 'Event', event_type: 'event' },
  { entity_type: 'Organization', event_type: 'entity_created' },
  { entity_type: 'Location', event_type: 'entity_created' },
  { entity_type: 'Organization', event_type: 'entity_created' },
];

describe('timeline dated-events filter', () => {
  it('shows everything by default', () => {
    expect(visible(sample, ALL, false)).toHaveLength(5);
  });

  it('narrows to entries whose date came from the source', () => {
    // The point: a chronology of what happened, not of when collection ran.
    expect(visible(sample, ALL, true)).toHaveLength(2);
  });

  it('uses the same signal as the row label', () => {
    // The row prints 'Occurred' for event_type === 'event' and 'Added to
    // graph' otherwise; filtering on anything else would let the two disagree.
    const dated = visible(sample, ALL, true);
    expect(dated.every(e => e.event_type === 'event')).toBe(true);
  });

  it('composes with the type filter rather than overriding it', () => {
    const onlyOrgs = new Set(['Organization']);
    expect(visible(sample, onlyOrgs, false)).toHaveLength(2);
    expect(visible(sample, onlyOrgs, true)).toHaveLength(0);
  });

  it('is empty, not everything, when nothing carries a date', () => {
    const undated = sample.filter(e => e.event_type !== 'event');
    expect(visible(undated, ALL, true)).toHaveLength(0);
  });
});
