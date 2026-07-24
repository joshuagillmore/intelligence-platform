import { describe, it, expect } from 'vitest';
import { humanize } from '@/lib/format';

/**
 * humanize turns snake_case / kebab-case identifiers into Title Case labels for
 * display, while the raw identifier stays the key for API calls.
 */
describe('humanize', () => {
  it('title-cases a snake_case identifier', () => {
    expect(humanize('report_writing')).toBe('Report Writing');
  });

  it('title-cases a kebab-case identifier', () => {
    expect(humanize('web-scrape')).toBe('Web Scrape');
  });

  it('capitalizes a single lowercase word', () => {
    expect(humanize('extract')).toBe('Extract');
  });

  it('handles mixed separators', () => {
    expect(humanize('multi_word-mixed_case')).toBe('Multi Word Mixed Case');
  });

  it('returns an empty string for empty input', () => {
    expect(humanize('')).toBe('');
  });

  it('is null/undefined-safe (guards with `|| \'\'`)', () => {
    // Callers occasionally pass through possibly-undefined API fields.
    expect(humanize(undefined as unknown as string)).toBe('');
    expect(humanize(null as unknown as string)).toBe('');
  });
});
