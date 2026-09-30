import { describe, it, expect } from 'vitest';
import { describeMapResult } from '@/lib/attackMapping';

/**
 * /attack/map returns mapped/skipped counts plus `skip_reasons` (reason ->
 * count), `stale_removed` on a remap, and `reason`/`detail` when the whole
 * batch could not run. "0 mapped, 5 skipped" alone cannot say whether the
 * model rejected everything or the technique catalogue was never embedded;
 * the note must say which.
 */
describe('describeMapResult', () => {
  it('reports mappings and breaks the skips down by reason', () => {
    const d = describeMapResult(
      { mapped: 4, skipped: 3, skip_reasons: { rejected: 2, no_candidates: 1 } },
      { isAdmin: true },
    );
    expect(d.tone).toBe('ok');
    expect(d.text).toMatch(/AI mapped 4 TTPs/);
    expect(d.text).toMatch(/3 skipped/);
    expect(d.text).toMatch(/2 rejected by the model/);
    expect(d.text).toMatch(/1 with no nearby technique/);
    expect(d.needsEmbed).toBe(false);
  });

  it('says the catalogue is not embedded when that is why nothing mapped', () => {
    const d = describeMapResult(
      {
        mapped: 0, skipped: 5, skip_reasons: { technique_catalogue_not_embedded: 5 },
        reason: 'technique_catalogue_not_embedded', detail: 'No ATT&CK technique embeddings exist yet.',
      },
      { isAdmin: true },
    );
    expect(d.tone).toBe('warn');
    expect(d.needsEmbed).toBe(true);
    expect(d.text).toMatch(/No ATT&CK technique embeddings exist yet/);
    expect(d.text).toMatch(/Embed techniques/);
  });

  it('points an analyst at an administrator for embedding', () => {
    const d = describeMapResult(
      { mapped: 0, skipped: 2, skip_reasons: { technique_catalogue_not_embedded: 2 }, reason: 'technique_catalogue_not_embedded' },
      { isAdmin: false },
    );
    expect(d.text).toMatch(/administrator/);
  });

  it('does not blame embedding when the model rejected every candidate', () => {
    const d = describeMapResult({ mapped: 0, skipped: 3, skip_reasons: { rejected: 3 } }, { isAdmin: true });
    expect(d.needsEmbed).toBe(false);
    expect(d.text).toMatch(/3 rejected by the model/);
    expect(d.text).not.toMatch(/Embed techniques/);
  });

  it('distinguishes an unreadable model reply from a rejection', () => {
    const d = describeMapResult({ mapped: 0, skipped: 2, skip_reasons: { unparsed: 2 } }, { isAdmin: true });
    expect(d.text).toMatch(/2 with an unreadable model reply/);
    expect(d.text).not.toMatch(/rejected/);
  });

  it('reports stale mappings removed by a remap', () => {
    const d = describeMapResult({ mapped: 1, skipped: 0, skip_reasons: {}, stale_removed: 2 }, { isAdmin: true });
    expect(d.text).toMatch(/2 earlier AI mappings removed/);
  });

  it('says there was nothing to map when nothing was attempted', () => {
    const d = describeMapResult({ mapped: 0, skipped: 0, skip_reasons: {} }, { isAdmin: true });
    expect(d.tone).toBe('ok');
    expect(d.text).toMatch(/No unmapped TTPs/);
  });

  it('names an unknown reason rather than dropping it', () => {
    const d = describeMapResult({ mapped: 0, skipped: 1, skip_reasons: { quota_exhausted: 1 } }, { isAdmin: true });
    expect(d.text).toMatch(/1 quota exhausted/);
  });
});
