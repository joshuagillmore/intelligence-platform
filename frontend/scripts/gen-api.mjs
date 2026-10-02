/**
 * Generate `src/lib/api.generated.ts` from the backend's OpenAPI document.
 *
 * `backend/openapi.json` is written by `backend/scripts/export_openapi.py`
 * (deterministic key order), so the same backend always produces the same
 * types. `npm run gen:api` runs this file; `tests/unit/apiGenerated.test.ts`
 * imports `generateApiTypes` and fails when the committed file differs from a
 * fresh generation, which is how a backend change that the frontend has not
 * caught up with fails the frontend job.
 *
 * Both paths go through this one function so the CLI's own banner or
 * formatting can never make a fresh file differ from the committed one.
 */
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const here = path.dirname(fileURLToPath(import.meta.url));

/** Where the backend writes its schema, relative to this repo. */
export const SPEC_PATH = path.resolve(here, '../../backend/openapi.json');
/** The committed output. */
export const OUTPUT_PATH = path.resolve(here, '../src/lib/api.generated.ts');

const BANNER = `/**
 * GENERATED FILE: do not edit by hand.
 *
 * Produced by \`npm run gen:api\` (frontend/scripts/gen-api.mjs) from
 * backend/openapi.json, which backend/scripts/export_openapi.py writes.
 * tests/unit/apiGenerated.test.ts fails when this file is stale.
 */
`;

/** The TypeScript source for the schema at `specPath`, LF line endings. */
export async function generateApiTypes(specPath = SPEC_PATH) {
  const spec = JSON.parse(await readFile(specPath, 'utf8'));
  // A pydantic field with a default is optional on the way in, so request
  // bodies must not demand it. Responses carry every non-nullable field; optional
  // ones may be absent (the backend sends only the keys a handler set); apiTypes'
  // `Present` restores that for them.
  const ast = await openapiTS(spec, { alphabetize: true, defaultNonNullable: false });
  return `${BANNER}\n${astToString(ast)}`.replace(/\r\n/g, '\n');
}

const invokedDirectly = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  const source = await generateApiTypes();
  await writeFile(OUTPUT_PATH, source, 'utf8');
  console.log(`wrote ${path.relative(process.cwd(), OUTPUT_PATH)} from ${path.relative(process.cwd(), SPEC_PATH)}`);
}
