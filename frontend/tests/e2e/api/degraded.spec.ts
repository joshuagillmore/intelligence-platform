import { test, expect, type APIRequestContext } from '@playwright/test';
import { anonymous, cleanUp, createProject, json, newAnalyst, signInAdmin, type Analyst } from './helpers';

/**
 * Degraded outcomes are counted, not only logged (backend/CLAUDE.md,
 * "Degraded outcomes"). `/health` carries `degraded: {subsystem: total}` for
 * the API process; `GET /api/admin/degraded` is the admin breakdown with the
 * time counting started. A plan generated from a requirement with no model is
 * a degraded collection outcome, so the spec causes one and looks for it.
 *
 * The admin breakdown's shape is asserted loosely: `since` plus objects of
 * counts, whether the counts sit at the top level (one process) or under
 * `total` (every process combined).
 *
 * Serial: the second test reads the count the first one causes.
 */
test.describe.configure({ mode: 'serial' });

let admin: APIRequestContext;
let analyst: Analyst;
let anon: APIRequestContext;
let projectId: string;

test.beforeAll(async () => {
  admin = await signInAdmin();
  analyst = await newAnalyst(admin, 'degraded');
  anon = await anonymous();
  projectId = await createProject(admin, 'degraded');
});

test.afterAll(async () => {
  await cleanUp(admin, [projectId], [analyst?.ctx, anon, admin]);
});

async function healthDegraded(): Promise<Record<string, number>> {
  const health = await json(await anon.get('/health'));
  expect(['ok', 'degraded']).toContain(health.status);
  expect(typeof health.degraded).toBe('object');
  expect(health.degraded).not.toBeNull();
  for (const [subsystem, count] of Object.entries(health.degraded)) {
    expect(Number.isInteger(count), `${subsystem}: ${count}`).toBe(true);
    expect(count as number).toBeGreaterThanOrEqual(0);
  }
  return health.degraded;
}

test('/health counts degraded outcomes per subsystem, as integers', async () => {
  test.setTimeout(120_000);
  const before = (await healthDegraded()).collection ?? 0;

  // No model in this stack: generating a plan from a requirement degrades.
  const pir = await json(await admin.post('/api/pirs', { data: { project_id: projectId, text: 'Who supplies the port?' } }));
  const plan = await json(
    await admin.post('/api/collection-plans/from-pir', { data: { project_id: projectId, pir_id: pir.id }, timeout: 110_000 }),
  );
  expect(plan.generation_failures.length).toBeGreaterThan(0);

  const after = (await healthDegraded()).collection ?? 0;
  expect(after - before).toBeGreaterThanOrEqual(plan.generation_failures.length);
});

test('/api/admin/degraded gives an admin the breakdown and refuses everyone else', async () => {
  const res = await admin.get('/api/admin/degraded');
  const body = await json(res);
  expect(typeof body).toBe('object');
  expect(typeof body.since).toBe('string');
  expect(Number.isNaN(Date.parse(body.since))).toBe(false);

  // One process's counts at the top level, or every process's under `total`.
  const counts = (typeof body.total === 'object' && body.total !== null ? body.total : body) as Record<string, unknown>;
  for (const [subsystem, reasons] of Object.entries(counts)) {
    if (subsystem === 'since' || subsystem === 'processes') continue;
    expect(typeof reasons, subsystem).toBe('object');
    for (const count of Object.values(reasons as Record<string, unknown>)) {
      expect(Number.isInteger(count), `${subsystem}: ${count}`).toBe(true);
    }
  }
  // The generation failure counted on /health is broken down by reason here.
  expect(Object.keys((counts.collection ?? {}) as object).length).toBeGreaterThan(0);

  expect((await analyst.ctx.get('/api/admin/degraded')).status()).toBe(403);
  expect((await anon.get('/api/admin/degraded')).status()).toBe(401);
});
