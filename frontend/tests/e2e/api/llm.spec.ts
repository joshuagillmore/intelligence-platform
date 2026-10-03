import { test, expect } from '@playwright/test';
import { json, signInAdmin } from './helpers';

/**
 * The one flow here that needs a live model: generating an intelligence
 * product. Opt-in and tagged `@llm`; skipped unless `E2E_LLM=1`, because every
 * run spends billed calls (the Cohere trial key allows 20 a minute and 1,000 a
 * month). CI runs it only from the manually dispatched "Frontend E2E with a
 * live model" job, which gives the stack a provider key:
 *
 *   E2E_LLM=1 npx playwright test --grep @llm
 *
 * Needs the seeded demo project (backend/scripts/seed_demo.py).
 */
const DEMO_PROJECT = 'demo-sentinel';

test.describe('live model', { tag: '@llm' }, () => {
  test.skip(process.env.E2E_LLM !== '1', 'opt-in: set E2E_LLM=1 against a stack with a provider key');

  test('a product generated for the seeded project is non-empty markdown', async () => {
    test.setTimeout(240_000);
    const admin = await signInAdmin();
    try {
      const entities = (await json(
        await admin.get('/api/entities', { params: { project_id: DEMO_PROJECT, query: 'Nord Industrial', limit: 5 } }),
      )) as { id: string; name: string }[];
      expect(entities.length, 'seed the demo project first').toBeGreaterThan(0);

      const product = await json(
        await admin.post('/api/reports/generate', {
          data: {
            project_id: DEMO_PROJECT,
            entity_ids: entities.slice(0, 3).map((e) => e.id),
            requirement: 'What is Nord Industrial Group procuring, from where, and through whom?',
          },
          timeout: 220_000,
        }),
      );
      const content = String(product.content ?? '').trim();
      expect(content.length).toBeGreaterThan(200);
      // Markdown structure: a heading, a list item or bold text somewhere.
      expect(content).toMatch(/^#{1,4} \S|^\s*[-*] \S|^\s*\d+\. \S|\*\*\S/m);
      expect(product.model).toBeTruthy();
      expect(['grounded', 'ungrounded']).toContain(product.retrieval_mode);
    } finally {
      await admin.dispose();
    }
  });
});
