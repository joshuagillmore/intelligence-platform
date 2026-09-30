import { describe, it, expect } from 'vitest';
import { entityPropertyEntries } from '@/lib/api';

/**
 * Entity routes flatten node fields onto the entity; a few nest them under
 * `properties`. Panels that listed `entity.properties` showed nothing for the
 * flattened shape. This lists the displayable fields from either shape.
 */
describe('entityPropertyEntries', () => {
  it('lists fields from a flattened entity', () => {
    const entries = entityPropertyEntries({
      id: 'ip-1', name: '203.0.113.7', entity_type: 'IPAddress', project_id: 'p1',
      asn: 'AS64500', enriched: true,
    });
    expect(Object.fromEntries(entries)).toEqual({ asn: 'AS64500', enriched: true });
  });

  it('lists fields from the nested shape too', () => {
    const entries = entityPropertyEntries({
      id: 'loc-1', name: 'Rotterdam', entity_type: 'Location', properties: { country: 'NL' },
    });
    expect(Object.fromEntries(entries)).toEqual({ country: 'NL' });
  });

  it('leaves out identity fields and empty values', () => {
    const keys = entityPropertyEntries({
      id: 'x', name: 'x', entity_type: 'Person', project_id: 'p', properties: {}, note: '', seen: null,
    }).map(([k]) => k);
    expect(keys).toEqual([]);
  });

  it('returns nothing for a non-object', () => {
    expect(entityPropertyEntries(null)).toEqual([]);
  });
});
