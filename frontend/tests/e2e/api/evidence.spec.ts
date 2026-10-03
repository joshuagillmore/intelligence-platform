import { test, expect, type APIRequestContext } from '@playwright/test';
import { cleanUp, createProject, json, signInAdmin } from './helpers';

/**
 * Evidence: a document ingested into a project becomes the evidence for the
 * entities extracted from it. `GET /api/entities/{id}/documents` (the evidence
 * chain the network view shows) must return that document with a passage that
 * quotes the entity. NLP extraction only, so no model is needed.
 */
let admin: APIRequestContext;
let projectId: string;

const DOCUMENT = [
  'Maria Gonzalez, the chief executive of Northwind Shipping Company, met port officials in Rotterdam on 3 March 2026.',
  'Northwind Shipping Company later confirmed that Maria Gonzalez had signed a charter for two tankers.',
].join(' ');

test.beforeAll(async () => {
  admin = await signInAdmin();
  projectId = await createProject(admin, 'evidence');
});

test.afterAll(async () => {
  await cleanUp(admin, [projectId], [admin]);
});

async function findEntity(query: string, name: RegExp) {
  const found = (await json(await admin.get('/api/entities', { params: { project_id: projectId, query } }))) as {
    id: string;
    name: string;
    entity_type: string;
  }[];
  const entity = found.find((e) => name.test(e.name));
  expect(entity, `no entity named ${name} among ${JSON.stringify(found.map((e) => e.name))}`).toBeTruthy();
  return entity!;
}

test('an ingested document is the evidence for the entities it names, with a quoted passage', async () => {
  test.setTimeout(90_000);
  const ingested = await json(
    await admin.post('/api/ingest', {
      multipart: { project_id: projectId, content: DOCUMENT, source_name: 'e2e-evidence.txt', extraction_mode: 'nlp' },
      timeout: 80_000,
    }),
  );
  expect(ingested.document_id).toBeTruthy();
  expect(ingested.document_name).toBe('e2e-evidence.txt');
  expect(ingested.entities_created).toBeGreaterThan(0);

  for (const [query, name, quoted] of [
    ['Northwind', /^Northwind Shipping Company$/, 'Northwind Shipping Company'],
    ['Gonzalez', /^Maria Gonzalez$/, 'Maria Gonzalez'],
  ] as const) {
    const entity = await findEntity(query, name);
    const chain = await json(await admin.get(`/api/entities/${entity.id}/documents`));
    expect(chain.total).toBeGreaterThanOrEqual(1);
    const doc = chain.documents.find((d: { name: string }) => d.name === 'e2e-evidence.txt');
    expect(doc, `${quoted}: the ingested document is not in its evidence chain`).toBeTruthy();
    expect(doc.mention_count).toBeGreaterThanOrEqual(1);
    expect(doc.passages.length).toBeGreaterThanOrEqual(1);
    for (const passage of doc.passages as { text: string; offset: number }[]) {
      expect(passage.text).toContain(quoted);
      expect(passage.offset).toBeGreaterThanOrEqual(0);
      expect(DOCUMENT.slice(passage.offset, passage.offset + quoted.length)).toBe(quoted);
    }
  }
});
