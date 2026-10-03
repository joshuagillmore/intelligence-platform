# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report privately through GitHub's
[private vulnerability reporting](https://github.com/joshuagillmore/intelligence-platform/security/advisories/new)
(the **Security** tab → **Report a vulnerability**). We aim to acknowledge a
report within a few days and will keep you updated as we work on a fix.

When reporting, please include:

- the affected component (backend `intel_platform`, frontend, or deploy config),
- a description of the issue and its impact,
- steps to reproduce (a proof-of-concept helps), and
- any suggested remediation.

## Scope

This is an intelligence-analyst workbench that **collects untrusted content from
the web** and renders it back to analysts. Reports touching the trust boundary
are especially valuable:

- **SSRF / egress** — outbound collection fetches are gated through
  `collection/url_guard.py` (`validate_url`) on every request and redirect hop.
- **Injection** — stored XSS from document- or LLM-derived text, Cypher/SQL
  injection, prompt injection that escalates privilege.
- **AuthN / AuthZ** — JWT handling, the admin-gated routes, per-project access
  (see "Project access" below), privilege escalation.
- **Secret handling** — provider API keys saved through the admin UI are
  Fernet-encrypted at rest **when `ENCRYPTION_KEY` is set**; without it they are
  stored in plaintext (a warning is logged at boot, and `REQUIRE_SECURE_AUTH=true`
  refuses to start). Report any leak path.

## Deploying safely

This project ships with **default development credentials** and a placeholder
`JWT_SECRET`. Before exposing any instance beyond `localhost`:

- set `REQUIRE_SECURE_AUTH=true` (see exactly what it checks below),
- set a real, high-entropy `JWT_SECRET` (at least 32 bytes),
- set `DEFAULT_ADMIN_PASSWORD` to a strong value, and an `ENCRYPTION_KEY`
  (a Fernet key; `Fernet.generate_key()`),
- set `API_KEY` to a long random value, or leave it blank to disable API-key
  auth (a non-blank key authenticates as admin),
- set `CORS_ORIGINS` to the origin(s) the UI is actually served from,
- provide real datastore passwords (never the `.env.example` placeholders;
  with Docker Compose, `NEO4J_PASSWORD` and `POSTGRES_PASSWORD`), and
- keep `.env` (and any real keys) out of version control — it is gitignored.

### What `REQUIRE_SECURE_AUTH=true` enforces

With `REQUIRE_SECURE_AUTH=true` the app refuses to start unless every one of
these holds (without the flag, the secret and admin-password problems are only
logged as warnings at boot):

- `JWT_SECRET` is set, is not the shipped placeholder, and is at least 32 bytes.
- `API_KEY` is either blank (which switches API-key auth off) or a non-default
  value of at least 16 bytes. Any non-blank key authenticates as admin.
- `ENCRYPTION_KEY` is set to a valid Fernet key.
- No admin account's **stored** password hash verifies against `admin`. This is
  checked against the database on every boot, not against the setting: an
  instance that once booted with `admin`/`admin` is caught too. If
  `DEFAULT_ADMIN_PASSWORD` is set (and is not `admin`), those accounts are given
  that password at boot; otherwise the app refuses to start. On an empty
  database it will not seed an `admin` user without a non-default
  `DEFAULT_ADMIN_PASSWORD`.
- `MCP_ENABLED` is not true: the MCP endpoint's tools write to the graph and
  spend LLM calls, so it is refused outright under secure auth.

A signed-in user changes their own password with `POST /api/auth/change-password`
(current password required; throttled like a login).

### Browser sessions

The UI does not hold its token. `POST /api/auth/login` sets the JWT in an
**httpOnly** cookie (`sentinel_session`, `SameSite=Lax`, `Path=/`, lifetime
`SESSION_COOKIE_MAX_AGE`, default 24 h) and returns only `{username, role}`, so
script running in the page — an XSS in rendered document or model text — cannot
read it. `POST /api/auth/logout` clears it; `GET /api/auth/me` says who it
belongs to.

Because the browser attaches a cookie on its own, a cookie-authenticated request
that changes state (anything but `GET`/`HEAD`/`OPTIONS`), and logout itself,
must also carry the header `X-Requested-With: sentinel`; without it the API
answers **403**. A cross-site form cannot set a header, and a cross-site script
that tries needs a CORS preflight that `CORS_ORIGINS` refuses, so another site
cannot act as a signed-in analyst. `SameSite=Lax` is the second layer.

- Set `SESSION_COOKIE_SECURE=true` on any deployment served over HTTPS, so the
  cookie is never sent over plain HTTP.
- Callers with a bearer JWT or the `API_KEY` in the `Authorization` header are
  unaffected and need no extra header; the API key is accepted only in that
  header, never from the cookie.

The local `docker compose` stack binds all services to `127.0.0.1` by design;
do not rebind app ports to `0.0.0.0` on an untrusted network.

### Project access

Each project has members, held in Postgres (`project_members`), with one of
three roles: **viewer** (read), **editor** (read and write project data) and
**owner** (also manage members and delete the project). An admin (`role` admin
on the session, which includes the `API_KEY`) is an implicit owner of every
project; they are listed only on projects they created or claimed.

- **Open projects.** A project with no members is usable by every signed-in
  user. Only projects created before membership existed are open (every new
  project is owned from birth, see below), so a single-analyst deployment
  works as before. Any signed-in user may add the first member of an open
  project, and that member must be an owner. Adding the first member restricts
  the project. On a shared deployment, an admin should **claim** every open
  project (`POST /api/projects/{id}/claim`, or the "Claim" control the projects
  page shows admins next to each open project): the admin becomes its owner
  and it is restricted. Until that happens anyone signed in can add themselves
  as its first owner.
- **Restricted projects.** Only members can use a restricted project, each up to
  their role. Anyone else gets **403** `No access to this project`. A member
  whose role is too low gets a 403 that names the role required. **404** means
  only that the project does not exist. So a 403 does confirm that a project id
  exists, but project ids are random UUIDs.
- **New projects.** Whoever creates a project becomes its owner, admins and
  the `API_KEY` caller (`api_key_user`) included, so every new project starts
  restricted. If the owner row cannot be written the project is not created
  (503).
- **Owners.** The members of a restricted project always include at least one
  owner. The API refuses (409) to remove or demote the last one.
- **What is checked.** Every project-scoped API operation declares
  `require_project_access`. A `project_id` is read from the path, the query
  string or the JSON/form body. So is the id of anything a project owns: an
  entity, document, report, note, snapshot, legacy collection, plan, source,
  catalog entry or PIR. Each id is resolved to its project, and the caller must
  hold the role on **every** project a request touches. Naming a project you can
  access does not reach another project's entity. The project list and the
  unscoped plan and collection lists are filtered on the server.
  `tests/test_project_access_coverage.py` walks the OpenAPI schema and fails on
  any project-scoped operation that does not declare the check.
- **Failing closed.** If membership cannot be read, the API returns 503 and does
  not let the request through.
- **Outside this model.** Admin routes (`/api/admin/*`, ATT&CK catalogue loads,
  user registration, personas) are admin-only, as before. The MCP endpoint (off
  by default, and refused under `REQUIRE_SECURE_AUTH`) does **not** apply
  per-project access: its tools act on whichever project they name. Keep MCP
  off on a shared deployment.

## Supported versions

This is an actively developed project; security fixes land on `main`. There are
no separately maintained release branches — track `main` for the latest fixes.
