import { test, expect, type APIRequestContext } from '@playwright/test';
import { ADMIN_USER, cleanUp, createProject, detail, json, newAnalyst, signInAdmin, type Analyst } from './helpers';

/**
 * Per-project access through the real API (SECURITY.md, "Project access").
 *
 * The admin registers two analysts for this run. The admin creates a project,
 * makes analyst A its owner, and A makes analyst B a viewer. The specs assert
 * on the membership state they set, not on the state a new project starts in:
 * whether an admin-created project starts open or owned by its admin is a
 * policy that can change, and the checks below hold either way.
 *
 * Serial: each test builds on the membership the previous one left.
 */
test.describe.configure({ mode: 'serial' });

let admin: APIRequestContext;
let a: Analyst;
let b: Analyst;
let projectId: string;
let ownProjectOfA: string | undefined;

test.beforeAll(async () => {
  admin = await signInAdmin();
  a = await newAnalyst(admin, 'a');
  b = await newAnalyst(admin, 'b');
  projectId = await createProject(admin, 'access');
});

test.afterAll(async () => {
  await cleanUp(admin, [projectId, ownProjectOfA], [a?.ctx, b?.ctx, admin]);
});

async function members() {
  return json(await admin.get(`/api/projects/${projectId}/members`));
}

test('before an analyst is a member, access follows the project state', async () => {
  const state = await members();
  const res = await a.ctx.get(`/api/projects/${projectId}`);
  if (state.access === 'open') {
    // Open: no members, and every signed-in user may use it.
    expect(state.members).toEqual([]);
    expect(res.status()).toBe(200);
    expect((await res.json()).access).toBe('open');
  } else {
    // Restricted from the start (its creator is listed as owner): A is refused.
    expect(state.members.some((m: { role: string }) => m.role === 'owner')).toBe(true);
    expect(res.status()).toBe(403);
    expect(await detail(res)).toBe('No access to this project');
  }
});

test('an owner restricts the project: a non-member gets 403, never 404', async () => {
  const added = await json(
    await admin.put(`/api/projects/${projectId}/members/${a.username}`, { data: { role: 'owner' } }),
  );
  expect(added).toMatchObject({ username: a.username, role: 'owner' });

  const state = await members();
  expect(state.access).toBe('restricted');
  expect(state.members).toContainEqual(expect.objectContaining({ username: a.username, role: 'owner' }));

  const mine = await json(await a.ctx.get(`/api/projects/${projectId}`));
  expect(mine).toMatchObject({ id: projectId, access: 'restricted', my_role: 'owner' });

  // B is not a member: refused with the access message. A 404 would wrongly
  // claim the project does not exist, and would hide the access decision.
  const refused = await b.ctx.get(`/api/projects/${projectId}`);
  expect(refused.status()).toBe(403);
  expect(await detail(refused)).toBe('No access to this project');
  // Reaching the project's data through another route is refused the same way.
  const entities = await b.ctx.get('/api/entities', { params: { project_id: projectId } });
  expect(entities.status()).toBe(403);

  // 404 is kept for a project that does not exist.
  expect((await b.ctx.get(`/api/projects/e2e-no-such-project-${Date.now()}`)).status()).toBe(404);
});

test('a viewer can read but not write, whether the project id is in a form or a JSON body', async () => {
  const added = await json(
    await a.ctx.put(`/api/projects/${projectId}/members/${b.username}`, { data: { role: 'viewer' } }),
  );
  expect(added).toMatchObject({ username: b.username, role: 'viewer' });

  const read = await json(await b.ctx.get(`/api/projects/${projectId}`));
  expect(read.my_role).toBe('viewer');

  // Document ingest takes project_id as a multipart form field, not from the path.
  const form = {
    project_id: projectId,
    content: 'Access check. Nothing here should be stored for a viewer.',
    source_name: 'e2e-viewer-write.txt',
    extraction_mode: 'nlp',
  };
  const formWrite = await b.ctx.post('/api/ingest', { multipart: form });
  expect(formWrite.status()).toBe(403);
  expect(await detail(formWrite)).toBe('This needs the editor role on this project; yours is viewer');

  const jsonWrite = await b.ctx.post('/api/pirs', { data: { project_id: projectId, text: 'A viewer may not add this' } });
  expect(jsonWrite.status()).toBe(403);

  // A viewer cannot manage members either.
  const promote = await b.ctx.put(`/api/projects/${projectId}/members/${b.username}`, { data: { role: 'owner' } });
  expect(promote.status()).toBe(403);

  // The same form from the owner is accepted, so the 403 above was the role
  // check and not a malformed request.
  const ownerWrite = await json(await a.ctx.post('/api/ingest', { multipart: { ...form, content: 'Owner write.' } }));
  expect(ownerWrite.document_id).toBeTruthy();
});

test('the last owner can be neither removed nor demoted (409)', async () => {
  // Leave A as the only owner. If the admin was listed as an owner when it
  // created the project, it is removed here; an admin needs no membership.
  for (const m of (await members()).members as { username: string; role: string }[]) {
    if (m.role === 'owner' && m.username !== a.username) {
      await json(await admin.delete(`/api/projects/${projectId}/members/${m.username}`));
    }
  }
  const owners = (await members()).members.filter((m: { role: string }) => m.role === 'owner');
  expect(owners).toEqual([expect.objectContaining({ username: a.username })]);

  expect((await a.ctx.delete(`/api/projects/${projectId}/members/${a.username}`)).status()).toBe(409);
  expect(
    (await a.ctx.put(`/api/projects/${projectId}/members/${a.username}`, { data: { role: 'viewer' } })).status(),
  ).toBe(409);
  // The rule is the project's, not the caller's: an admin is refused too.
  expect((await admin.delete(`/api/projects/${projectId}/members/${a.username}`)).status()).toBe(409);

  expect((await members()).members).toContainEqual(expect.objectContaining({ username: a.username, role: 'owner' }));
});

test('an admin is never refused, member or not', async () => {
  const state = await members();
  expect(state.access).toBe('restricted');
  expect(state.members.map((m: { username: string }) => m.username)).not.toContain(ADMIN_USER);

  const read = await json(await admin.get(`/api/projects/${projectId}`));
  expect(read.my_role).toBe('owner');
  // A write the admin is not a member for goes through as well.
  const pir = await json(await admin.post('/api/pirs', { data: { project_id: projectId, text: 'Admin-added requirement' } }));
  expect(pir.project_id).toBe(projectId);
});

test('the project list shows each caller only what they may read', async () => {
  // A project A creates is A's alone: an analyst's new project starts restricted.
  ownProjectOfA = await createProject(a.ctx, 'a-only');

  const listOf = async (ctx: APIRequestContext) =>
    (await json(await ctx.get('/api/projects'))) as { id: string; access: string; my_role: string | null }[];
  const [listA, listB, listAdmin] = await Promise.all([listOf(a.ctx), listOf(b.ctx), listOf(admin)]);

  expect(listA.map((p) => p.id)).toEqual(expect.arrayContaining([projectId, ownProjectOfA]));
  expect(listA.find((p) => p.id === ownProjectOfA)).toMatchObject({ access: 'restricted', my_role: 'owner' });

  expect(listB.find((p) => p.id === projectId)).toMatchObject({ my_role: 'viewer' });
  expect(listB.map((p) => p.id)).not.toContain(ownProjectOfA);
  // Everything B is shown is open or names B's role on it.
  for (const p of listB) {
    expect(p.access === 'open' || p.my_role !== null, `B was listed ${p.id}`).toBe(true);
  }

  expect(listAdmin.map((p) => p.id)).toEqual(expect.arrayContaining([projectId, ownProjectOfA]));
  // And the list matches the per-project check.
  expect((await b.ctx.get(`/api/projects/${ownProjectOfA}`)).status()).toBe(403);
});
