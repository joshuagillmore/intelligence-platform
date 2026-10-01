// @vitest-environment node
import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';
import { generateApiTypes, OUTPUT_PATH, SPEC_PATH } from '../../scripts/gen-api.mjs';

/**
 * `src/lib/api.generated.ts` is the frontend's copy of the backend contract.
 * When a backend change lands without the frontend regenerating it, the
 * committed types describe an API that no longer exists, and every check
 * `api.ts` makes against them is checking the wrong thing. This fails the
 * frontend job instead.
 */
describe('api.generated.ts', () => {
  it('matches a fresh generation from backend/openapi.json', async () => {
    let fresh: string;
    try {
      fresh = await generateApiTypes(SPEC_PATH);
    } catch (error) {
      throw new Error(
        `Could not generate from ${SPEC_PATH} (${String(error)}). ` +
          'Export it with `cd backend && uv run python scripts/export_openapi.py`.',
      );
    }
    const committed = (await readFile(OUTPUT_PATH, 'utf8')).replace(/\r\n/g, '\n');
    if (committed === fresh) return;

    // Name the first differing line rather than dumping two 8,000-line files.
    const a = committed.split('\n');
    const b = fresh.split('\n');
    const line = a.findIndex((text, i) => text !== b[i]);
    const at = line === -1 ? Math.min(a.length, b.length) : line;
    expect.fail(
      `src/lib/api.generated.ts is stale: run \`npm run gen:api\` and commit the result.\n` +
        `First difference at line ${at + 1}:\n  committed: ${a[at] ?? '<end of file>'}\n  fresh:     ${b[at] ?? '<end of file>'}`,
    );
  });
});
