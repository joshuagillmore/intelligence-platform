import { describe, it, expect } from 'vitest';
import { planTitle } from '@/lib/planTitle';

describe('planTitle', () => {
  it('leaves a clean requirement alone', () => {
    const t = 'Which vessels have been implicated in damage to Baltic Sea undersea cables since 2024?';
    expect(planTitle(t)).toBe(t);
  });

  it('recovers the requirement from a markdown-damaged title', () => {
    // Seen in the plan list, twice, indistinguishable from each other.
    const raw = '** > **Refined PIR:** *From 1 January 2024 to the present, identify all commercial vessels';
    expect(planTitle(raw)).toBe('From 1 January 2024 to the present, identify all commercial vessels');
  });

  it('strips a restated label the model prefixed', () => {
    const raw = '(Actionable, Specific, Measurable, Time-bounded)** > **Priority Intelligence Requirement (PIR):** Identify all incidents';
    expect(planTitle(raw)).toContain('Identify all incidents');
    expect(planTitle(raw)).not.toContain('**');
  });

  it('drops heading hashes and blockquote arrows', () => {
    expect(planTitle('### > Which vessels?')).toBe('Which vessels?');
  });

  it('removes emphasis without eating the words', () => {
    expect(planTitle('The _Yi Peng 3_ and **Newnew Polar Bear**')).toBe('The Yi Peng 3 and Newnew Polar Bear');
  });

  it('collapses a multi-line block to one line', () => {
    expect(planTitle('First line\n\nSecond line')).toBe('First line Second line');
  });

  it('falls back when there is nothing to show', () => {
    expect(planTitle('')).toBe('Untitled requirement');
    expect(planTitle(null)).toBe('Untitled requirement');
    expect(planTitle('   ')).toBe('Untitled requirement');
  });

  it('falls back rather than returning bare punctuation', () => {
    // A title of pure markup is not a title.
    expect(planTitle('** > **')).toBe('Untitled requirement');
  });

  it('accepts a caller-supplied fallback', () => {
    expect(planTitle('', 'Plan 7')).toBe('Plan 7');
  });

  it('does not strip legitimate punctuation inside the text', () => {
    const t = 'Vessels: Yi Peng 3, Newnew Polar Bear — what links them?';
    expect(planTitle(t)).toBe(t);
  });
});

describe('planTitle italic handling', () => {
  it('leaves identifiers with underscores intact', () => {
    // The backend's stripper protects snake_case for the same reason.
    expect(planTitle('Check the chunk_text column')).toBe('Check the chunk_text column');
  });

  it('leaves a mid-word underscore alone', () => {
    expect(planTitle('Growth of 20_30 percent')).toBe('Growth of 20_30 percent');
  });
});
