import { test, expect, type APIRequestContext } from '@playwright/test';
import { cleanUp, createProject, json, signInAdmin } from './helpers';

/**
 * A collection run end to end through the collection worker.
 *
 * The stack has no model, so the plan generated from a requirement must say
 * why it came back thin (`generation_failures`) rather than look like a plan
 * with nothing to do. Executing it only queues the run in the API
 * (COLLECTION_WORKER_MODE=worker); the separate worker service claims it, and
 * a cancel ends it. The stack must run the `worker` service, as CI's does.
 *
 * The plan gets one web source so the run lasts long enough to be cancelled
 * while running: resolving it asks the model, and the in-stack Ollama has no
 * model, so the run retries for a few seconds before the source fails. (The
 * resolution also runs a web search, as any real run does.) If the run still
 * finishes first, the cancel has nothing to stop and the spec asserts the
 * terminal state instead; the annotation says which happened.
 */
test.describe.configure({ mode: 'serial' });

const TERMINAL_STATES = ['completed', 'failed', 'cancelled'];
const TERMINAL_JOBS = ['succeeded', 'failed', 'cancelled'];

let admin: APIRequestContext;
let projectId: string;
let planId: string;

test.beforeAll(async () => {
  admin = await signInAdmin();
  projectId = await createProject(admin, 'worker-run');
});

test.afterAll(async () => {
  await cleanUp(admin, [projectId], [admin]);
});

async function executionStatus() {
  return json(await admin.get(`/api/collection-plans/${planId}/execution-status`));
}

test('a plan generated from a requirement with no model says why it is thin', async () => {
  test.setTimeout(120_000);
  const pir = await json(
    await admin.post('/api/pirs', {
      data: { project_id: projectId, text: 'Which vessels called at Rotterdam under a changed flag in 2026?' },
    }),
  );
  const plan = await json(
    await admin.post('/api/collection-plans/from-pir', { data: { project_id: projectId, pir_id: pir.id }, timeout: 110_000 }),
  );
  planId = plan.id;
  test.info().annotations.push({
    type: 'generation',
    description: `llm_available=${plan.llm_available}; ${plan.generation_failures.join('; ')}`,
  });

  expect(plan).toMatchObject({ project_id: projectId, pir_id: pir.id, status: 'DRAFT' });
  // Nothing was generated, and the response says so in its own words.
  expect(plan.sources).toEqual([]);
  expect(plan.eeis_captured).toBe(0);
  expect(Array.isArray(plan.generation_failures)).toBe(true);
  expect(plan.generation_failures.length).toBeGreaterThan(0);
  for (const failure of plan.generation_failures) expect(typeof failure).toBe('string');
  expect(plan.generation_failures).toContain('no essential elements were extracted from the refinement');
  if (plan.llm_available) {
    // A provider was selected (the Ollama fallback) but could not answer.
    expect(plan.generation_failures.join('; ')).toMatch(/refinement failed \(\w+\)|source generation failed \(\w+\)/);
  } else {
    expect(plan.llm_requirements?.message).toBeTruthy();
  }
});

test('execute queues the run, the worker claims it, and cancel ends it', async () => {
  test.setTimeout(150_000);
  const source = await json(
    await admin.post(`/api/collection-plans/${planId}/sources`, {
      data: { name: 'e2e worker run', source_type: 'web_scrape', config: { url: 'https://example.com/' } },
    }),
  );
  expect(source.plan_id).toBe(planId);

  const started = await json(await admin.post(`/api/collection-plans/${planId}/execute`, { data: {} }), 202);
  // The API process does not run it: it is queued for a worker.
  expect(started).toMatchObject({ worker_mode: 'worker', execution_status: 'queued', sources_queued: 1 });
  expect(started.job_id).toBeTruthy();

  const first = await executionStatus();
  expect(first.job_id).toBe(started.job_id);

  // The worker claims it within a minute (it polls every 2 s).
  await expect
    .poll(async () => (await executionStatus()).job_status, { timeout: 60_000, intervals: [250, 500, 1000] })
    .not.toBe('queued');

  const cancel = await admin.post(`/api/collection-plans/${planId}/cancel`);
  test.info().annotations.push({
    type: 'cancel',
    description: cancel.status() === 202 ? 'cancelled the running job' : 'the run had finished; nothing to cancel',
  });
  if (cancel.status() === 202) {
    const body = await cancel.json();
    // Running: the job is marked cancelled at once and the run stops before
    // its next step, so the state reads `running` until it has stopped.
    expect(body).toMatchObject({ job_id: started.job_id, status: 'cancelled', previous_status: 'running', stopping: true });
    await expect.poll(async () => (await executionStatus()).status, { timeout: 60_000 }).toBe('cancelled');
    expect((await executionStatus()).job_status).toBe('cancelled');
    // A second cancel finds nothing in flight.
    expect((await admin.post(`/api/collection-plans/${planId}/cancel`)).status()).toBe(409);
  } else {
    // The run finished before the cancel arrived: there was nothing to stop.
    expect(cancel.status()).toBe(409);
    const done = await executionStatus();
    expect(TERMINAL_STATES).toContain(done.status);
    expect(TERMINAL_JOBS).toContain(done.job_status);
  }
});

test('a run cancelled as soon as it is queued ends cancelled', async () => {
  test.setTimeout(120_000);
  // The previous run is finished, so the plan can run again.
  const started = await json(await admin.post(`/api/collection-plans/${planId}/execute`, { data: {} }), 202);
  expect(started.execution_status).toBe('queued');

  const cancel = await admin.post(`/api/collection-plans/${planId}/cancel`);
  if (cancel.status() === 202) {
    const body = await cancel.json();
    test.info().annotations.push({ type: 'cancel', description: `cancelled a ${body.previous_status} job` });
    expect(body).toMatchObject({ job_id: started.job_id, status: 'cancelled' });
    // Queued: finished at once. Claimed in between: stops before its next step.
    expect(['queued', 'running']).toContain(body.previous_status);
    await expect.poll(async () => (await executionStatus()).status, { timeout: 60_000 }).toBe('cancelled');
    const done = await executionStatus();
    expect(done).toMatchObject({ job_id: started.job_id, job_status: 'cancelled' });
  } else {
    // A worker claimed and finished it between the two requests.
    expect(cancel.status()).toBe(409);
    expect(TERMINAL_JOBS).toContain((await executionStatus()).job_status);
  }
  // Nothing is left in flight: cancelling again has nothing to stop.
  expect((await admin.post(`/api/collection-plans/${planId}/cancel`)).status()).toBe(409);
});
