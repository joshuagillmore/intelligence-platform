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
- **AuthN / AuthZ** — JWT handling, the admin-gated routes, privilege escalation.
- **Secret handling** — API keys are Fernet-encrypted at rest; report any leak path.

## Deploying safely

This project ships with **default development credentials** and a placeholder
`JWT_SECRET`. Before exposing any instance beyond `localhost`:

- set strong, non-default admin credentials,
- set a real, high-entropy `JWT_SECRET`,
- provide real datastore passwords (never the `.env.example` placeholders), and
- keep `.env` (and any real keys) out of version control — it is gitignored.

The local `docker compose` stack binds all services to `127.0.0.1` by design;
do not rebind app ports to `0.0.0.0` on an untrusted network.

## Supported versions

This is an actively developed project; security fixes land on `main`. There are
no separately maintained release branches — track `main` for the latest fixes.
