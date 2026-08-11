import { describe, it, expect } from 'vitest';
import { totalFrom } from '@/lib/api';

describe('totalFrom', () => {
  it('reads the true total from the header', () => {
    // The list view showed 50 rows of 398 with nothing to say so.
    expect(totalFrom({ headers: { 'x-total-count': '398' }, data: new Array(50) })).toBe(398);
  });

  it('accepts the canonical header casing too', () => {
    expect(totalFrom({ headers: { 'X-Total-Count': '12' }, data: [] })).toBe(12);
  });

  it('falls back to the page length when the header is missing', () => {
    // Under-report rather than invent: a caller that cannot read the header
    // should not claim a total it does not know.
    expect(totalFrom({ headers: {}, data: [1, 2, 3] })).toBe(3);
  });

  it('falls back when the header is not a number', () => {
    expect(totalFrom({ headers: { 'x-total-count': 'many' }, data: [1, 2] })).toBe(2);
  });

  it('ignores a negative total', () => {
    expect(totalFrom({ headers: { 'x-total-count': '-5' }, data: [1] })).toBe(1);
  });

  it('handles a zero total without falling back', () => {
    expect(totalFrom({ headers: { 'x-total-count': '0' }, data: [] })).toBe(0);
  });

  it('survives a response with no headers at all', () => {
    expect(totalFrom({ data: [1] })).toBe(1);
    expect(totalFrom({})).toBe(0);
  });

  it('does not report truncation when the page is the whole set', () => {
    const res = { headers: { 'x-total-count': '29' }, data: new Array(29) };
    expect(totalFrom(res) > res.data.length).toBe(false);
  });
});
