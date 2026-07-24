import { describe, it, expect } from 'vitest';
import {
  TYPE_COLOR_CLASS,
  TYPE_COLOR_HEX,
  TYPE_BADGE_CLASS,
  TYPE_ICON,
} from '@/lib/entityStyles';

/**
 * entityStyles is the single source of truth for entity coloring. These tests
 * lock in the known-type mappings and the fallback behaviour (unknown types
 * resolve to `undefined`, letting callers apply their own default).
 */
describe('entityStyles SSOT', () => {
  describe('TYPE_COLOR_CLASS (status dots / chips)', () => {
    it('maps core entity types to their Tailwind bg-* class', () => {
      expect(TYPE_COLOR_CLASS.Person).toBe('bg-orange-500');
      expect(TYPE_COLOR_CLASS.Organization).toBe('bg-blue-500');
      expect(TYPE_COLOR_CLASS.Location).toBe('bg-green-500');
    });

    it('maps cyber IOC types', () => {
      expect(TYPE_COLOR_CLASS.IPAddress).toBe('bg-cyan-500');
      expect(TYPE_COLOR_CLASS.ThreatActor).toBe('bg-red-500');
    });

    it('returns undefined for an unknown type (caller supplies fallback)', () => {
      expect(TYPE_COLOR_CLASS.NotAThing).toBeUndefined();
    });

    it('exposes only Tailwind bg-* utility classes', () => {
      for (const cls of Object.values(TYPE_COLOR_CLASS)) {
        expect(cls).toMatch(/^bg-[a-z]+-\d{3}$/);
      }
    });
  });

  describe('TYPE_COLOR_HEX (d3 node fill)', () => {
    it('maps types to valid 6-digit hex colors', () => {
      expect(TYPE_COLOR_HEX.Person).toBe('#f97316');
      expect(TYPE_COLOR_HEX.Organization).toBe('#3b82f6');
      for (const hex of Object.values(TYPE_COLOR_HEX)) {
        expect(hex).toMatch(/^#[0-9a-f]{6}$/i);
      }
    });

    it('returns undefined for an unknown type', () => {
      expect(TYPE_COLOR_HEX.Nonsense).toBeUndefined();
    });
  });

  describe('TYPE_BADGE_CLASS (cyber IOC badges)', () => {
    it('maps IOC types to a bg + text class pair', () => {
      expect(TYPE_BADGE_CLASS.IPAddress).toBe('bg-cyan-900/30 text-cyan-400');
      expect(TYPE_BADGE_CLASS.Vulnerability).toContain('text-rose-400');
    });

    it('returns undefined for an unknown type', () => {
      expect(TYPE_BADGE_CLASS.Mystery).toBeUndefined();
    });
  });

  describe('TYPE_ICON (compact glyphs)', () => {
    it('provides an emoji glyph for common types', () => {
      expect(TYPE_ICON.Person).toBe('👤');
      expect(TYPE_ICON.Location).toBe('📍');
    });

    it('returns undefined for a type without a glyph', () => {
      expect(TYPE_ICON.Unmapped).toBeUndefined();
    });
  });
});
