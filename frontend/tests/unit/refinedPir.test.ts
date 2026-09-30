import { describe, it, expect } from 'vitest';
import { extractRefinedPir } from '@/lib/refinedPir';

/**
 * The PIR refinement is free model prose; the refined requirement is whatever
 * follows a "Refined PIR"-style label, in whatever markdown the model chose.
 * The old regex took everything after the label up to the next straight quote
 * (usually the whole rest of the reply), and its "curly quote" class held only
 * a straight quote. These fixtures are the shapes models actually produce.
 */
const PIR = 'What command-and-control infrastructure has APT29 used against EU ministries since January 2024?';

describe('extractRefinedPir', () => {
  it('reads a bolded label with a quoted value', () => {
    const text = `1. ASSESS: too broad.\n\n**Refined PIR:** "${PIR}"\n\nThis version is time-bounded.`;
    expect(extractRefinedPir(text)).toBe(PIR);
  });

  it('reads a numbered label', () => {
    const text = `4. Techniques: ACH.\n5. Refined PIR: ${PIR}\n6. Notes: none.`;
    expect(extractRefinedPir(text)).toBe(PIR);
  });

  it('reads a numbered bold heading with the value on the next line', () => {
    const text = `### 5. **Proposed Refined PIR**\n\n> “${PIR}”\n\nWhy: it names an actor and a window.`;
    expect(extractRefinedPir(text)).toBe(PIR);
  });

  it('reads a table row', () => {
    const text = `| Element | Value |\n|---|---|\n| Original PIR | What is APT29 doing? |\n| Refined PIR | ${PIR} |`;
    expect(extractRefinedPir(text)).toBe(PIR);
  });

  it('reads a prose-prefixed label', () => {
    const text = `Taking all of this into account, my proposed refined PIR is: "${PIR}" It is narrower.`;
    expect(extractRefinedPir(text)).toBe(PIR);
  });

  it('strips curly quotes', () => {
    expect(extractRefinedPir(`Revised PIR: “${PIR}”`)).toBe(PIR);
  });

  it('does not take the rest of the reply after the value', () => {
    const text = `Refined version: ${PIR}\n\nSub-questions:\n- Which domains?\n- Which hosting providers?`;
    expect(extractRefinedPir(text)).toBe(PIR);
  });

  it('returns null for a reply that echoes the instruction but never gives a refined PIR', () => {
    const text = '5. PROPOSE a refined version of the PIR that is more actionable\n\nI need more context first.';
    expect(extractRefinedPir(text)).toBeNull();
  });

  it('returns null for pure prose with no label', () => {
    expect(extractRefinedPir('The requirement is broad and should be narrowed to one actor and a time window.')).toBeNull();
  });
});
