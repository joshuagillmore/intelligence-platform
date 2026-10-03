/**
 * GENERATED FILE: do not edit by hand.
 *
 * Produced by `npm run gen:api` (frontend/scripts/gen-api.mjs) from
 * backend/openapi.json, which backend/scripts/export_openapi.py writes.
 * tests/unit/apiGenerated.test.ts fails when this file is stale.
 */

export interface paths {
    "/api/admin/api-keys": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Api Keys
         * @description List all stored API keys with masked values.
         */
        get: operations["list_api_keys_api_admin_api_keys_get"];
        put?: never;
        /**
         * Add Api Key
         * @description Add a new API key for a provider.
         */
        post: operations["add_api_key_api_admin_api_keys_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/api-keys/{key_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Api Key
         * @description Delete an API key by ID.
         */
        delete: operations["delete_api_key_api_admin_api_keys__key_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/api-keys/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Activate Api Key
         * @description Set a specific key as the active key for its provider.
         *
         *     Deactivation follows the stored key's own provider. Deactivating by the
         *     request's provider and activating the id unchecked left two active keys for
         *     one provider whenever the two disagreed, and every key lookup for it then
         *     raised.
         */
        put: operations["activate_api_key_api_admin_api_keys_activate_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Config
         * @description Return non-sensitive configuration info.
         */
        get: operations["get_config_api_admin_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/degraded": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Degraded
         * @description Degraded outcomes over the last 24 hours, from every process.
         *
         *     ``{since, processes: {api: {...}, worker: {...}}, total: {...},
         *     history_available}``, each count map ``{<subsystem>: {<reason>: count}}``:
         *     the rows the API and the collection worker flushed to ``degraded_events``,
         *     plus this process's counts not flushed yet. ``/health`` stays per process.
         */
        get: operations["get_degraded_api_admin_degraded_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/enrichment": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Enrichment Config */
        get: operations["get_enrichment_config_api_admin_enrichment_get"];
        /** Update Enrichment Config */
        put: operations["update_enrichment_config_api_admin_enrichment_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/llm/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Available Models
         * @description List models available from all configured providers.
         */
        get: operations["list_available_models_api_admin_llm_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/llm/select": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Select Llm
         * @description Switch the active LLM provider and model; persisted, so it survives a restart.
         *
         *     Saved before it takes effect: a choice that would silently revert on the
         *     next restart is refused (503) instead.
         */
        put: operations["select_llm_api_admin_llm_select_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/proxy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Proxy Config */
        get: operations["get_proxy_config_api_admin_proxy_get"];
        /** Update Proxy Config */
        put: operations["update_proxy_config_api_admin_proxy_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/admin/vpn/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Vpn Status
         * @description Report gluetun VPN status + public IP. Never 500s on an unreachable VPN.
         */
        get: operations["get_vpn_status_api_admin_vpn_status_get"];
        /**
         * Set Vpn Status
         * @description Stop (kill-switch) or start the gluetun VPN tunnel.
         */
        put: operations["set_vpn_status_api_admin_vpn_status_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/analysis/gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Analyze Gaps
         * @description Intelligence gaps: measured graph-coverage holes, then a narrated read.
         */
        post: operations["analyze_gaps_api_analysis_gaps_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/analysis/hypotheses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Hypotheses
         * @description Analysis of Competing Hypotheses over retrieved graph + document evidence.
         */
        post: operations["generate_hypotheses_api_analysis_hypotheses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/analysis/source-evaluation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Evaluate Sources
         * @description Grade the project's sources on the NATO Admiralty scale.
         *
         *     Grounded in measured provenance: entity yield per document, corroboration
         *     against the project's other documents, content volume, origin URL, and any
         *     rating already on file.
         */
        post: operations["evaluate_sources_api_analysis_source_evaluation_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/assess/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Assessment
         * @description Use LLM to generate an assessment for an entity based on graph context.
         */
        post: operations["generate_assessment_api_assess_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/assess/multi": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Assess Multiple Entities
         * @description Assess multiple entities at once — gathers context for all and returns combined assessment data.
         */
        post: operations["assess_multiple_entities_api_assess_multi_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/attribution": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Attribution
         * @description Candidate threat-actor groups ranked by observed-technique overlap.
         *
         *     Suggestive overlap, not confirmed attribution.
         */
        get: operations["get_attribution_api_attack_attribution_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/embed": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Embed
         * @description (Admin) Embed the ATT&CK technique catalog into pgvector for RAG mapping.
         *
         *     Idempotent (upsert). Degrades to ``{"embedded": 0}`` if no embedding provider
         *     is reachable rather than 500-ing.
         */
        post: operations["embed_api_attack_embed_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/ingest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ingest
         * @description (Admin) Fetch + parse + load the pinned ATT&CK bundle. Idempotent.
         */
        post: operations["ingest_api_attack_ingest_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/ingest-vuln-chain": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ingest Vuln Chain
         * @description (Admin) Fetch CWE + CAPEC, load ``(:Cwe)-[:ENABLES]->(:AttackTechnique)``.
         *
         *     Idempotent. Requires ATT&CK to be ingested first (edges are only created for
         *     techniques that already exist). Returns ``{"cwes": int, "edges": int}``.
         */
        post: operations["ingest_vuln_chain_api_attack_ingest_vuln_chain_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/map": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Map Ttps
         * @description RAG-map this project's unmapped TTPs to ATT&CK techniques.
         *
         *     Returns mapped/skipped counts with a reason per skip (see
         *     :func:`services.attack.mapping.map_project_ttps`). An unreachable LLM is a
         *     503, not a batch of skips. ``remap`` re-examines LLM-mapped TTPs and removes
         *     edges the model no longer confirms.
         */
        post: operations["map_ttps_api_attack_map_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/matrix": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Matrix
         * @description Full tactic → technique model with per-technique observed coverage.
         */
        get: operations["get_matrix_api_attack_matrix_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/navigator-layer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Navigator Layer
         * @description Download a Navigator layer v4.5 JSON scored by observed coverage.
         */
        get: operations["get_navigator_layer_api_attack_navigator_layer_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Report
         * @description Assemble the ATT&CK-structured intelligence product for a project.
         *
         *     Structured sections (observed-by-tactic, candidate attribution, key
         *     mitigations, CVE-enabled techniques) + a deterministic markdown report and a
         *     short LLM narrative (``null`` if no LLM is reachable).
         */
        get: operations["get_report_api_attack_report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resolve
         * @description Link this project's TTP/ThreatActor entities to canonical ATT&CK nodes.
         */
        post: operations["resolve_api_attack_resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/resolve-cve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resolve Cve
         * @description Chain this project's CVE ``Vulnerability`` entities to ATT&CK techniques.
         *
         *     MERGEs ``HAS_WEAKNESS`` to the CWE reference nodes and materializes
         *     ``(:Vulnerability)-[:ENABLES {via:"cwe-capec"}]->(:AttackTechnique)`` for every
         *     technique those CWEs enable. Returns
         *     ``{"vulnerabilities": int, "techniques_linked": int}``.
         */
        post: operations["resolve_cve_api_attack_resolve_cve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Status
         * @description Whether ATT&CK is ingested, at what version, with node counts.
         */
        get: operations["get_status_api_attack_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/technique/{tid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Technique
         * @description Technique detail: tactics, platforms, detection, mitigations, groups, and
         *     this project's entities mapped to it.
         */
        get: operations["get_technique_api_attack_technique__tid__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attack/technique/{tid}/d3fend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get D3Fend
         * @description D3FEND defensive countermeasures for a technique (lazy, keyless, cached).
         *
         *     ``tid`` must be ``T####`` or ``T####.###`` (422 otherwise): it goes into the
         *     outbound D3FEND URL. A 404 from D3FEND is a cached "none"; an outage or an
         *     unreadable reply returns ``{"countermeasures": [], "degraded": true}``
         *     uncached — never a 500.
         */
        get: operations["get_d3fend_api_attack_technique__tid__d3fend_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/change-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Change Password
         * @description Change the signed-in user's password.
         *
         *     There was no way to change a password at all, so a seeded admin/admin could
         *     only be fixed by editing the database. The current password is required and
         *     throttled like a login, because this endpoint is otherwise a password oracle.
         */
        post: operations["change_password_api_auth_change_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description Sign in: sets the session cookie (contract 8). The token is not in the body.
         */
        post: operations["login_api_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Logout
         * @description Clear the session cookie.
         *
         *     Needs no live session (an expired one must still be clearable) but does
         *     need the session header: a cross-site form must not sign the analyst out.
         */
        post: operations["logout_api_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Me
         * @description The signed-in user, from the cookie or a bearer token.
         */
        get: operations["me_api_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Register
         * @description Create a new user. Requires admin authentication.
         */
        post: operations["register_api_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-dashboard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Collection Dashboard
         * @description Dashboard summary: plan counts, recent acquisitions, source health.
         */
        get: operations["collection_dashboard_api_collection_dashboard_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Plans */
        get: operations["list_plans_api_collection_plans_get"];
        put?: never;
        /** Create Plan */
        post: operations["create_plan_api_collection_plans_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Plan */
        get: operations["get_plan_api_collection_plans__plan_id__get"];
        /** Update Plan */
        put: operations["update_plan_api_collection_plans__plan_id__put"];
        post?: never;
        /** Delete Plan */
        delete: operations["delete_plan_api_collection_plans__plan_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/acquisitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Acquisitions */
        get: operations["list_acquisitions_api_collection_plans__plan_id__acquisitions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Activate Plan */
        post: operations["activate_plan_api_collection_plans__plan_id__activate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Activity
         * @description A page of a plan's activity log, oldest first.
         *
         *     Without `since`, the most recent `limit` events. With `since` (an ISO-8601
         *     timestamp, normally the last event the caller holds), up to `limit` events
         *     after it — so a poller pages forward instead of reloading the trail. The UI
         *     polls every 3 s and every poll used to load the whole trail; a malformed
         *     `since` was silently ignored, which also meant "load all of it", and is now
         *     a 400.
         */
        get: operations["get_activity_api_collection_plans__plan_id__activity_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Plan */
        post: operations["archive_plan_api_collection_plans__plan_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Plan Run
         * @description Cancel the plan's live run (queued, running, or stalled).
         *
         *     A running job is marked ``cancelled`` and stops before its next source
         *     (``plan_should_stop`` reads it); ``stopping`` says so, and the run state
         *     stays ``running`` until it has. A queued or stalled job has nothing left to
         *     stop and is finished at once. 409 when no run is live.
         */
        post: operations["cancel_plan_run_api_collection_plans__plan_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Catalog */
        get: operations["list_catalog_api_collection_plans__plan_id__catalog_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Complete Plan */
        post: operations["complete_plan_api_collection_plans__plan_id__complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/execute": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Execute Plan Endpoint
         * @description Approve and execute a collection plan: 202 with the ``job_id`` of the run.
         *
         *     Inserts a ``collection_jobs`` row. In ``inline`` worker mode the API process
         *     runs it at once as a background task; in ``worker`` mode it is ``queued``
         *     for ``python -m intel_platform.worker``. The run resolves sources, acquires
         *     them through the registered connectors, extracts entities into the graph,
         *     then re-tasks against the requirement's open elements. File upload sources
         *     are skipped (they need a manual upload). With nothing to run the plan is
         *     still activated, and ``job_id`` is null.
         */
        post: operations["execute_plan_endpoint_api_collection_plans__plan_id__execute_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/execution-status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Execution Status
         * @description Poll the execution progress of a collection plan's latest run.
         *
         *     ``status`` is the job table's answer (``current_run_state``), the same one
         *     the execute guard enforces; the activity trail supplies the message and the
         *     per-run counts. ``job_status``, ``seconds_since_heartbeat`` and ``error``
         *     come from the job row so a caller can see why a run reads as it does.
         */
        get: operations["get_execution_status_api_collection_plans__plan_id__execution_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/pause": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pause Plan */
        post: operations["pause_plan_api_collection_plans__plan_id__pause_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Sources */
        get: operations["list_sources_api_collection_plans__plan_id__sources_get"];
        put?: never;
        /** Add Source */
        post: operations["add_source_api_collection_plans__plan_id__sources_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/sources/{source_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Source */
        put: operations["update_source_api_collection_plans__plan_id__sources__source_id__put"];
        post?: never;
        /** Delete Source */
        delete: operations["delete_source_api_collection_plans__plan_id__sources__source_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/sources/{source_id}/acquisitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Source Acquisitions */
        get: operations["list_source_acquisitions_api_collection_plans__plan_id__sources__source_id__acquisitions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/{plan_id}/sources/{source_id}/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload File To Source
         * @description Upload a file through a collection plan source → parse → profile → ingest → route to graph.
         */
        post: operations["upload_file_to_source_api_collection_plans__plan_id__sources__source_id__upload_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collection-plans/from-pir": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Plan From Pir
         * @description Submit a PIR → LLM refines it, generates a collection plan with sources.
         *
         *     Flow: PIR → LLM refinement → LLM plan generation → create Plan + Sources → DRAFT
         *     Returns the plan ready for user approval.
         *
         *     The PIR itself is persisted first (or resolved from `pir_id`), so the plan is
         *     always anchored to a requirement the project hub can list and track.
         */
        post: operations["create_plan_from_pir_api_collection_plans_from_pir_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Collections */
        get: operations["list_collections_api_collections_get"];
        put?: never;
        /**
         * Create Collection
         * @description Legacy: create a collection. New code should use POST /collection-plans/from-pir.
         */
        post: operations["create_collection_api_collections_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Collection */
        get: operations["get_collection_api_collections__task_id__get"];
        /** Update Collection */
        put: operations["update_collection_api_collections__task_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections/{task_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Collection */
        post: operations["cancel_collection_api_collections__task_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections/{task_id}/execute": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Execute Collection
         * @description Execute an approved collection plan: search -> crawl -> ingest -> extract.
         */
        post: operations["execute_collection_api_collections__task_id__execute_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections/{task_id}/progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Collection Progress
         * @description Get detailed collection execution progress.
         */
        get: operations["get_collection_progress_api_collections__task_id__progress_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections/{task_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Collection Status */
        get: operations["get_collection_status_api_collections__task_id__status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections/count/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Collection Count For Project */
        get: operations["get_collection_count_for_project_api_collections_count__project_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/collections/parse-plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Parse Plan */
        post: operations["parse_plan_api_collections_parse_plan_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/communities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Communities */
        get: operations["get_communities_api_communities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/connector-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Connector Types
         * @description List available connector types and their capabilities.
         */
        get: operations["list_connector_types_api_connector_types_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-catalog/{catalog_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Catalog Entry */
        get: operations["get_catalog_entry_api_data_catalog__catalog_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/data-catalog/{catalog_id}/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Catalog Preview */
        get: operations["get_catalog_preview_api_data_catalog__catalog_id__preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Documents
         * @description List a project's documents with metadata, and how many exist in all.
         */
        get: operations["list_documents_api_documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/documents/{doc_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Document
         * @description Get full document with content and extracted entities.
         */
        get: operations["get_document_api_documents__doc_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/documents/{doc_id}/evidence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Evidence For Entity
         * @description Get text passages from a document that mention a specific entity.
         *
         *     At most MAX_EVIDENCE_PASSAGES are returned; `total` counts every mention.
         *     A blank name is refused: it matched at every index, so one request against
         *     a 10 MB document built about ten million passages.
         */
        get: operations["get_evidence_for_entity_api_documents__doc_id__evidence_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/enrichment/entities/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Enrichment
         * @description Return the cached enrichment view without hitting any provider.
         *
         *     ``cached`` holds only providers that have a cached payload for this
         *     observable — ``{}`` when nothing is cached. A provider with no entry (or an
         *     unreadable one) is absent rather than ``null``, so a client cannot mistake
         *     a miss for a cached result.
         */
        get: operations["get_enrichment_api_enrichment_entities__entity_id__get"];
        put?: never;
        /**
         * Investigate
         * @description Run every eligible provider for the entity and merge the results.
         */
        post: operations["investigate_api_enrichment_entities__entity_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/enrichment/entities/{entity_id}/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh
         * @description Force a fresh lookup for one provider, bypassing the cache.
         */
        post: operations["refresh_api_enrichment_entities__entity_id__refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/enrichment/providers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Providers
         * @description List registered providers, their supported types, and key status.
         */
        get: operations["list_providers_api_enrichment_providers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/entities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search Entities
         * @description Entities matching the filters, capped at `limit`.
         *
         *     `X-Total-Count` reports how many match in full, so a caller can tell a
         *     complete list from a truncated one. Nothing said so before, and every
         *     consumer takes the default 50: the geo map plotted 50 of 398 locations and
         *     the network sidebar grouped 50 of 5,486 entities under type headings that
         *     read as totals. A header keeps the body a bare list, which every existing
         *     caller already parses as one.
         */
        get: operations["search_entities_api_entities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/entities/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Entity */
        get: operations["get_entity_api_entities__entity_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/entities/{entity_id}/assess": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Assessment */
        post: operations["create_assessment_api_entities__entity_id__assess_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/entities/{entity_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Entity Documents
         * @description The documents that mention an entity, with evidence passages: its evidence chain.
         *
         *     One call, from the entity's MENTIONS edges, in its own project; the
         *     network page used to request evidence document by document. Most-
         *     mentioning documents first. Each carries up to PASSAGES_PER_DOCUMENT
         *     passages around the entity's name — matched exactly first, then ignoring
         *     case, since reporting does not keep an extractor's capitalisation.
         *     `count` is this page, `total` every document that mentions the entity.
         */
        get: operations["get_entity_documents_api_entities__entity_id__documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/entities/{entity_id}/type": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Entity Type
         * @description Update an entity's type (e.g., fix a misclassification).
         */
        put: operations["update_entity_type_api_entities__entity_id__type_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/entities/merge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Merge Entities
         * @description Merge entities into the primary, moving every edge as it was.
         *
         *     Each edge keeps its direction, type and properties (evidence, provenance,
         *     polarity), and the documents that mention a merged entity move to the
         *     primary. An entity is deleted only once every one of its edges has been
         *     recreated on the primary; otherwise it is kept, and the response says so —
         *     deleting it anyway is how edges used to disappear behind a success message.
         */
        post: operations["merge_entities_api_entities_merge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/entity-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Entity Type Hierarchy
         * @description Get the entity type hierarchy.
         */
        get: operations["get_entity_type_hierarchy_api_entity_types_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/export/entities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Entities Csv
         * @description Export all entities as CSV.
         */
        get: operations["export_entities_csv_api_export_entities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/export/graph": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Graph Json
         * @description Export the full graph as JSON (nodes + edges).
         */
        get: operations["export_graph_json_api_export_graph_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/export/mindmap": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Mindmap
         * @description Export the topic mind map in various formats.
         *
         *     format: json | markdown | mermaid
         */
        get: operations["export_mindmap_api_export_mindmap_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/export/report/{report_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Report
         * @description Export a specific report.
         */
        get: operations["export_report_api_export_report__report_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/export/stix": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Stix
         * @description Export the knowledge graph as a STIX 2.1 bundle.
         */
        get: operations["export_stix_api_export_stix_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/geo/entity-timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Entity Timeline
         * @description Get temporal data for an entity — event dates, relationship dates, document ingestion dates.
         *
         *     Returns bucketed counts for the traffic frequency chart and raw events for the temporal window.
         */
        get: operations["get_entity_timeline_api_geo_entity_timeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/geo/locations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Geo Locations
         * @description Get all geolocatable entities (places + IP/WHOIS geo) with relationships and edges.
         */
        get: operations["get_geo_locations_api_geo_locations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/geo/nearby/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Nearby
         * @description Nearby OSM features (airfields / military / ports / infrastructure /
         *     government / neighbourhoods) around a geolocated entity — local GEOINT
         *     context via Overpass. Best-effort: returns [] if the entity has no
         *     coordinates or Overpass is unreachable.
         */
        get: operations["get_nearby_api_geo_nearby__entity_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/geo/within": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Within
         * @description Entities whose coordinates fall inside a bounding box — the "what's in
         *     this area" (AOI) query. Reuses the same coordinate resolver as the map.
         *
         *     Flat bbox: does not handle antimeridian crossing (a view straddling 180°
         *     longitude would miss the far side) — fine for typical AOIs.
         */
        get: operations["get_within_api_geo_within_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/graph": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Full Graph */
        get: operations["get_full_graph_api_graph_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/graph/centrality": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Centrality */
        get: operations["get_centrality_api_graph_centrality_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/graph/ego-network/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ego Network */
        get: operations["get_ego_network_api_graph_ego_network__entity_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/graph/influence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Influence Propagation */
        post: operations["post_influence_propagation_api_graph_influence_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/graph/statistics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Statistics */
        get: operations["get_statistics_api_graph_statistics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/graph/structural-holes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Structural Holes */
        get: operations["get_structural_holes_api_graph_structural_holes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ingest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ingest Document */
        post: operations["ingest_document_api_ingest_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ingest/batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ingest Batch */
        post: operations["ingest_batch_api_ingest_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/llm/query": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Llm Query */
        post: operations["llm_query_api_llm_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/llm/skills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Skills */
        get: operations["list_skills_api_llm_skills_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/notebook": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Notes */
        get: operations["list_notes_api_notebook_get"];
        put?: never;
        /** Create Note */
        post: operations["create_note_api_notebook_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/notebook/{note_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Note */
        get: operations["get_note_api_notebook__note_id__get"];
        put?: never;
        post?: never;
        /** Delete Note */
        delete: operations["delete_note_api_notebook__note_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/paths/{entity_id_1}/{entity_id_2}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Find Shortest Path */
        get: operations["find_shortest_path_api_paths__entity_id_1___entity_id_2__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/personas": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Personas */
        get: operations["list_personas_api_personas_get"];
        put?: never;
        /**
         * Create Persona
         * @description Create a persona, or update a custom one. Built-ins cannot be overwritten.
         */
        post: operations["create_persona_api_personas_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/personas/{persona_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Persona */
        delete: operations["delete_persona_api_personas__persona_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/personas/{persona_id}/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Activate Persona */
        post: operations["activate_persona_api_personas__persona_id__activate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/personas/active": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Active Persona */
        get: operations["get_active_persona_api_personas_active_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pirs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Pirs
         * @description List a project's requirements, newest first, each with the plans it drove.
         */
        get: operations["list_pirs_api_pirs_get"];
        put?: never;
        /** Create Pir */
        post: operations["create_pir_api_pirs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pirs/{pir_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Pir */
        get: operations["get_pir_api_pirs__pir_id__get"];
        /** Update Pir */
        put: operations["update_pir_api_pirs__pir_id__put"];
        post?: never;
        /**
         * Delete Pir
         * @description Delete a PIR. Plans raised against it survive, unlinked — the collected
         *     intelligence outlives the question that prompted it.
         */
        delete: operations["delete_pir_api_pirs__pir_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pirs/{pir_id}/assess": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Assess Pir
         * @description Judge whether what has been collected answers the PIR.
         *
         *     Either the requirement is satisfied or collection stopped at its source
         *     limit — and in that case the analyst needs to know *which* elements are
         *     still unanswered, rather than being handed a pile of documents and left to
         *     infer it. Each EEI is judged against the project's own graph, never against
         *     the model's background knowledge.
         */
        post: operations["assess_pir_api_pirs__pir_id__assess_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pirs/{pir_id}/requirements": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Pir Requirements
         * @description Per-element collection state: what is answered, what was tried, what is missing.
         *
         *     The assessor's reasoning was previously computed and discarded into a
         *     response payload nothing consumed. These rows are what the collection loop
         *     acts on, so exposing them is what lets an analyst see *why* a requirement is
         *     unfinished rather than only that it is.
         */
        get: operations["get_pir_requirements_api_pirs__pir_id__requirements_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Projects
         * @description The projects the caller may read, newest first, each with their role on it.
         *
         *     Filtered here, not in the client: an admin sees every project; anyone else
         *     sees the open ones (no members) and those they are a member of.
         */
        get: operations["list_projects_api_projects_get"];
        put?: never;
        /**
         * Create Project
         * @description Create a project. Its creator becomes its owner, which makes it restricted.
         *
         *     An admin is an implicit owner of every project and is never listed as a
         *     member, so a project an admin creates starts open.
         */
        post: operations["create_project_api_projects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["get_project_api_projects__project_id__get"];
        /** Update Project */
        put: operations["update_project_api_projects__project_id__put"];
        post?: never;
        /** Delete Project */
        delete: operations["delete_project_api_projects__project_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Project Activity
         * @description Get recent activity for a project.
         */
        get: operations["get_project_activity_api_projects__project_id__activity_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Project Members
         * @description The project's members (owners first), whether it is open, and the caller's role.
         */
        get: operations["list_project_members_api_projects__project_id__members_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/members/{username}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Put Project Member
         * @description Add a member or change their role (owners only; anyone on an open project).
         *
         *     409 when the project has no members and the role is not owner (the first
         *     member closes the project, so it must be someone who can manage it), or when
         *     the change would leave the project without an owner.
         */
        put: operations["put_project_member_api_projects__project_id__members__username__put"];
        post?: never;
        /**
         * Remove Project Member
         * @description Remove a member (owners only). 409 for the project's last owner.
         */
        delete: operations["remove_project_member_api_projects__project_id__members__username__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/batch-delete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Batch Delete Projects */
        post: operations["batch_delete_projects_api_projects_batch_delete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/query": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Graph Rag Query */
        post: operations["graph_rag_query_api_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Reports */
        get: operations["list_reports_api_reports_get"];
        put?: never;
        /** Save Report */
        post: operations["save_report_api_reports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reports/{report_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Report
         * @description A saved report. Only a Report node, and only in `project_id` when given.
         *
         *     It used to return whatever node carried the id — an entity, a Document,
         *     another project's report. Scoped as DELETE is; `project_id` stays optional
         *     so existing clients keep working, and a client that passes it can no longer
         *     be handed another project's report.
         */
        get: operations["get_report_api_reports__report_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Report
         * @description Delete a saved report. Only a Report node, and only in `project_id` when given.
         *
         *     `project_id` is optional so existing clients keep working; pass it and a
         *     report from another project is refused rather than deleted.
         */
        delete: operations["delete_report_api_reports__report_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reports/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Report
         * @description Generate an intelligence product grounded in real Graph-RAG retrieval.
         *
         *     Resolves the analyst-selected entities by exact ID (not a fuzzy text
         *     search — the analyst already chose them), retrieves their subgraph and
         *     source document evidence via the existing GraphRAGPipeline, optionally
         *     enriches with semantically similar passages via vector search, and
         *     generates the report through the requested skill. Falls back to an
         *     ungrounded prompt — with the limitation stated explicitly — only when
         *     retrieval finds no graph or document evidence at all.
         */
        post: operations["generate_report_api_reports_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Global Search
         * @description Search entity names across all entity types, documents, and reports.
         *
         *     Every search term must appear in the name. `count` is the rows on this
         *     page and `total` the true number of matches (the same filter, not capped
         *     by the page size); `total` used to be the page length, so a search capped
         *     at 50 always reported 50.
         */
        get: operations["global_search_api_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/search/semantic": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Semantic Search
         * @description Semantic similarity search across document chunks using vector embeddings.
         */
        post: operations["semantic_search_api_search_semantic_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/snapshots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Snapshots
         * @description List all snapshots for a project.
         */
        get: operations["list_snapshots_api_snapshots_get"];
        put?: never;
        /**
         * Create Snapshot
         * @description Save a subgraph snapshot (bin) for later analysis.
         */
        post: operations["create_snapshot_api_snapshots_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/snapshots/{snapshot_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Snapshot
         * @description Get a snapshot with full entity and relationship data.
         */
        get: operations["get_snapshot_api_snapshots__snapshot_id__get"];
        put?: never;
        post?: never;
        /** Delete Snapshot */
        delete: operations["delete_snapshot_api_snapshots__snapshot_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/subgraph/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Subgraph */
        get: operations["get_subgraph_api_subgraph__entity_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Timeline
         * @description Get a timeline of entities and events, newest first by real event date when known.
         *
         *     Entities with a populated ``event_datetime`` (extraction resolved a real-world
         *     date from the source text) are timestamped and labeled by that; everything
         *     else falls back to ``created_at`` (ingestion time) — the same fallback
         *     pattern geo.py's entity-timeline endpoint uses.
         *
         *     Returns one page (`count`) of the whole project (`total`), `truncated` when
         *     more exist past this page, and `types_present` across the whole project so a
         *     type filter can offer every type rather than a fixed list or the page's.
         */
        get: operations["get_timeline_api_timeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/timeline/histogram": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Timeline Histogram
         * @description Bucket a project's dated entities for the network-graph brush filter.
         *
         *     Only entities carrying a real `event_datetime` are counted — ingestion time
         *     is not a fact about the subject, and including it would draw a histogram of
         *     when the crawler ran. `undated` is returned alongside so the caller can say
         *     "42 of 380 entities are dated" rather than implying the rest are absent from
         *     the period.
         */
        get: operations["get_timeline_histogram_api_timeline_histogram_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/topics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Topic Tree
         * @description Build hierarchical topic tree, with the analyst's edits applied.
         *
         *     method: tfidf (keyword-based), semantic (embedding-based), or hybrid
         *     granularity: broad (3-5 clusters), medium (10-15), detailed (30+)
         *
         *     Only the algorithmic tree is cached. The edits are read and applied on
         *     every request, so a rename is visible on the next load without the cache
         *     having to be cleared — which, being per process, could not be done for
         *     every worker anyway. `edits_overlay` says whether they could be read.
         */
        get: operations["get_topic_tree_api_topics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/topics/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Topic Context */
        get: operations["get_topic_context_api_topics__entity_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/topics/{entity_id}/summarize": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Summarize Topic
         * @description Stream an LLM-generated intelligence summary for a topic node.
         */
        post: operations["summarize_topic_api_topics__entity_id__summarize_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/topics/{node_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Topic Node
         * @description Rename or update a topic node.
         */
        put: operations["update_topic_node_api_topics__node_id__put"];
        post?: never;
        /**
         * Delete Topic Node
         * @description Mark a topic node as deleted (hidden from view).
         */
        delete: operations["delete_topic_node_api_topics__node_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/topics/{node_id}/children": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Add Topic Child
         * @description Add a user-created child node to a topic.
         */
        post: operations["add_topic_child_api_topics__node_id__children_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/watchlist": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Watchlist */
        get: operations["get_watchlist_api_watchlist_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/watchlist/add": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add To Watchlist */
        post: operations["add_to_watchlist_api_watchlist_add_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/watchlist/remove": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Remove From Watchlist */
        post: operations["remove_from_watchlist_api_watchlist_remove_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health Check */
        get: operations["health_check_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AcquisitionLogItem */
        AcquisitionLogItem: {
            /** Completed At */
            completed_at?: string | null;
            /** Document Id */
            document_id: string;
            /** Duration Ms */
            duration_ms: number;
            /** Entities Created */
            entities_created: number;
            /** Error Message */
            error_message: string;
            /** Id */
            id: string;
            /** Plan Id */
            plan_id: string;
            /** Record Count */
            record_count: number;
            /** Relationships Created */
            relationships_created: number;
            /** Result */
            result: string;
            /** Source Id */
            source_id: string;
            /** Source Type */
            source_type: string;
            /** Started At */
            started_at?: string | null;
        };
        /** AddSourceRequest */
        AddSourceRequest: {
            /** Config */
            config?: {
                [key: string]: unknown;
            };
            /**
             * Enabled
             * @default true
             */
            enabled?: boolean;
            /** Name */
            name: string;
            /**
             * Schedule Cron
             * @default
             */
            schedule_cron?: string;
            /** Source Type */
            source_type: string;
        };
        /** AdminConfigResponse */
        AdminConfigResponse: {
            /** Chunk Overlap */
            chunk_overlap: number;
            /** Chunk Size */
            chunk_size: number;
            /** Extraction Mode */
            extraction_mode: string;
            /** Llm Model */
            llm_model: string;
            /** Llm Provider */
            llm_provider: string;
            /** Neo4J Uri */
            neo4j_uri: string;
            proxy: components["schemas"]["ProxyModeItem"];
        };
        /** ApiKeyActivatedResponse */
        ApiKeyActivatedResponse: {
            /** Active Key Id */
            active_key_id: string;
            /** Status */
            status: string;
        };
        /** ApiKeyActivateRequest */
        ApiKeyActivateRequest: {
            /** Key Id */
            key_id: string;
            /** Provider */
            provider: string;
        };
        /** ApiKeyCreatedResponse */
        ApiKeyCreatedResponse: {
            /** Id */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Key Preview */
            key_preview: string;
            /** Label */
            label: string;
            /** Provider */
            provider: string;
            /** Status */
            status: string;
        };
        /** ApiKeyCreateRequest */
        ApiKeyCreateRequest: {
            /** Api Key */
            api_key: string;
            /** Label */
            label: string;
            /** Provider */
            provider: string;
        };
        /** ApiKeyItem */
        ApiKeyItem: {
            /** Created At */
            created_at?: string | null;
            /** Id */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Key Preview */
            key_preview: string;
            /** Label */
            label: string;
            /** Provider */
            provider: string;
        };
        /** ApiKeyListResponse */
        ApiKeyListResponse: {
            /** Keys */
            keys: components["schemas"]["ApiKeyItem"][];
        };
        /** AssessmentCreatedResponse */
        AssessmentCreatedResponse: {
            /** Assessment Id */
            assessment_id: string;
            /** Entity Id */
            entity_id: string;
            /** Entity Name */
            entity_name: string;
            /** Judgment */
            judgment: string;
            /** Probability */
            probability: number;
            /** Probability Label */
            probability_label: string;
        };
        /**
         * AssessmentErrorItem
         * @description An assessment that could not be made (its entity is gone).
         */
        AssessmentErrorItem: {
            /** Error */
            error: string;
        };
        /**
         * AssessPirRequest
         * @description Optional inputs for a satisfaction assessment.
         */
        AssessPirRequest: {
            /** Source Limit */
            source_limit?: number | null;
        };
        /** AttackCountsItem */
        AttackCountsItem: {
            /** Groups */
            groups: number;
            /** Mitigations */
            mitigations: number;
            /** Software */
            software: number;
            /** Tactics */
            tactics: number;
            /** Techniques */
            techniques: number;
        };
        /** AttackEmbedResponse */
        AttackEmbedResponse: {
            /** Detail */
            detail?: string | null;
            /** Embedded */
            embedded: number;
            /** Reason */
            reason?: string | null;
        };
        /** AttackIngestResponse */
        AttackIngestResponse: {
            counts: components["schemas"]["AttackCountsItem"];
            /** Ingested */
            ingested: boolean;
            /** Version */
            version: string;
        };
        /** AttackMappedEntityItem */
        AttackMappedEntityItem: {
            /** Confidence */
            confidence?: number | null;
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id: string;
            /** Method */
            method: string;
            /** Name */
            name?: string | null;
        };
        /** AttackMapResponse */
        AttackMapResponse: {
            /** Detail */
            detail?: string | null;
            /** Mapped */
            mapped: number;
            /** Reason */
            reason?: string | null;
            /** Skip Reasons */
            skip_reasons: {
                [key: string]: number;
            };
            /** Skipped */
            skipped: number;
            /** Stale Removed */
            stale_removed?: number | null;
        };
        /** AttackMatrixResponse */
        AttackMatrixResponse: {
            /** Ingested */
            ingested: boolean;
            /** Tactics */
            tactics: components["schemas"]["AttackTacticItem"][];
            /** Version */
            version?: string | null;
        };
        /** AttackRefItem */
        AttackRefItem: {
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
        };
        /** AttackReportResponse */
        AttackReportResponse: {
            /** Attribution */
            attribution: components["schemas"]["AttributionSummaryItem"][];
            /** Cve Enabled */
            cve_enabled: components["schemas"]["CveEnabledTechniqueItem"][];
            /** Key Mitigations */
            key_mitigations: components["schemas"]["KeyMitigationItem"][];
            /** Markdown */
            markdown: string;
            /** Narrative */
            narrative?: string | null;
            /** Observed By Tactic */
            observed_by_tactic: components["schemas"]["ObservedTacticItem"][];
            /** Project Id */
            project_id: string;
        };
        /** AttackResolveResponse */
        AttackResolveResponse: {
            /** Mapped */
            mapped: number;
        };
        /** AttackStatusResponse */
        AttackStatusResponse: {
            counts: components["schemas"]["AttackCountsItem"];
            /** Ingested */
            ingested: boolean;
            /** Version */
            version?: string | null;
            vuln_chain: components["schemas"]["VulnChainStatusItem"];
        };
        /** AttackSubtechniqueItem */
        AttackSubtechniqueItem: {
            /** Id */
            id: string;
            /** Methods */
            methods: string[];
            /** Name */
            name?: string | null;
            /** Observed Count */
            observed_count: number;
        };
        /** AttackTacticItem */
        AttackTacticItem: {
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Shortname */
            shortname?: string | null;
            /** Techniques */
            techniques: components["schemas"]["AttackTechniqueCellItem"][];
        };
        /** AttackTacticRefItem */
        AttackTacticRefItem: {
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Shortname */
            shortname?: string | null;
        };
        /** AttackTechniqueCellItem */
        AttackTechniqueCellItem: {
            /** Id */
            id: string;
            /** Is Subtechnique */
            is_subtechnique: boolean;
            /** Methods */
            methods: string[];
            /** Name */
            name?: string | null;
            /** Observed Count */
            observed_count: number;
            /** Subtechniques */
            subtechniques: components["schemas"]["AttackSubtechniqueItem"][];
        };
        /** AttackTechniqueResponse */
        AttackTechniqueResponse: {
            /** Description */
            description: string;
            /** Detection */
            detection: string;
            /** Enabling Cves */
            enabling_cves: components["schemas"]["AttackRefItem"][];
            /** Groups */
            groups: components["schemas"]["AttackRefItem"][];
            /** Id */
            id: string;
            /** Is Subtechnique */
            is_subtechnique: boolean;
            /** Mitigations */
            mitigations: components["schemas"]["AttackRefItem"][];
            /** Name */
            name: string;
            /** Parent Id */
            parent_id?: string | null;
            /** Platforms */
            platforms: string[];
            /** Related Entities */
            related_entities: components["schemas"]["AttackMappedEntityItem"][];
            /** Tactics */
            tactics: components["schemas"]["AttackTacticRefItem"][];
        };
        /** AttributionGroupItem */
        AttributionGroupItem: {
            /** Coverage */
            coverage: number;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Shared Count */
            shared_count: number;
            /** Shared Techniques */
            shared_techniques: components["schemas"]["AttackRefItem"][];
        };
        /**
         * AttributionResponse
         * @description Groups ranked by technique overlap: suggestive, never confirmed attribution.
         */
        AttributionResponse: {
            /** Groups */
            groups: components["schemas"]["AttributionGroupItem"][];
            /** Observed Total */
            observed_total: number;
        };
        /** AttributionSummaryItem */
        AttributionSummaryItem: {
            /** Coverage */
            coverage: number;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Shared Count */
            shared_count: number;
        };
        /** BatchDeleteRequest */
        BatchDeleteRequest: {
            /** Project Ids */
            project_ids: string[];
        };
        /** BatchIngestResponse */
        BatchIngestResponse: {
            /** Documents Processed */
            documents_processed: number;
            /** Results */
            results: components["schemas"]["IngestResponse"][];
            /** Total Entities Created */
            total_entities_created: number;
            /** Total Relationships Created */
            total_relationships_created: number;
        };
        /** Body_ingest_batch_api_ingest_batch_post */
        Body_ingest_batch_api_ingest_batch_post: {
            /** Extraction Mode */
            extraction_mode?: string | null;
            /** Files */
            files: string[];
            /** Project Id */
            project_id: string;
            /**
             * Reliability Rating
             * @default C3
             */
            reliability_rating?: string;
        };
        /** Body_ingest_document_api_ingest_post */
        Body_ingest_document_api_ingest_post: {
            /** Content */
            content?: string | null;
            /** Extraction Mode */
            extraction_mode?: string | null;
            /** File */
            file?: string | null;
            /** Project Id */
            project_id: string;
            /**
             * Reliability Rating
             * @default C3
             */
            reliability_rating?: string;
            /** Source Name */
            source_name?: string | null;
        };
        /** Body_upload_file_to_source_api_collection_plans__plan_id__sources__source_id__upload_post */
        Body_upload_file_to_source_api_collection_plans__plan_id__sources__source_id__upload_post: {
            /**
             * Extraction Mode
             * @default nlp
             */
            extraction_mode?: string;
            /** File */
            file: string;
            /**
             * Reliability Rating
             * @default C3
             */
            reliability_rating?: string;
        };
        /** BoundingBoxItem */
        BoundingBoxItem: {
            /** Max Lat */
            max_lat: number;
            /** Max Lng */
            max_lng: number;
            /** Min Lat */
            min_lat: number;
            /** Min Lng */
            min_lng: number;
        };
        /** CachedEnrichmentResponse */
        CachedEnrichmentResponse: {
            /** Cached */
            cached: {
                [key: string]: {
                    [key: string]: unknown;
                };
            };
            /** Entity Id */
            entity_id: string;
            /** Observable */
            observable: string;
        };
        /** CatalogPreviewResponse */
        CatalogPreviewResponse: {
            /** Offset */
            offset: number;
            /** Rows */
            rows: {
                [key: string]: unknown;
            }[];
            /** Schema */
            schema: {
                [key: string]: unknown;
            };
            /** Total */
            total: number;
        };
        /** CentralityItem */
        CentralityItem: {
            /** Degree */
            degree: number;
            /** Entity Type */
            entity_type: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** ChangePasswordRequest */
        ChangePasswordRequest: {
            /** Current Password */
            current_password: string;
            /** New Password */
            new_password: string;
        };
        /** CollectionActivityItem */
        CollectionActivityItem: {
            /** Created At */
            created_at: string;
            /** Event */
            event: string;
            /** Id */
            id: string;
            /** Message */
            message: string;
            /** Plan Id */
            plan_id: string;
            /** Source Id */
            source_id?: string | null;
        };
        /** CollectionCountResponse */
        CollectionCountResponse: {
            /** Count */
            count: number;
            /** Project Id */
            project_id: string;
        };
        /** CollectionDashboardResponse */
        CollectionDashboardResponse: {
            /** Plan Counts */
            plan_counts: {
                [key: string]: number;
            };
            /** Project Id */
            project_id: string;
            /** Recent Acquisitions */
            recent_acquisitions: components["schemas"]["AcquisitionLogItem"][];
            source_health: components["schemas"]["SourceHealthItem"];
            /** Total Plans */
            total_plans: number;
            /** Total Records Acquired */
            total_records_acquired: number;
        };
        /** CollectionPlanResponse */
        CollectionPlanResponse: {
            /** Assigned To */
            assigned_to: string;
            /** Created At */
            created_at?: string | null;
            /** Created By */
            created_by: string;
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Next Run At */
            next_run_at?: string | null;
            /** Pir */
            pir: string;
            /** Pir Id */
            pir_id?: string | null;
            /** Project Id */
            project_id: string;
            /** Refined Pir */
            refined_pir: string;
            /** Requirement */
            requirement: string;
            /** Routing Rules */
            routing_rules: {
                [key: string]: unknown;
            };
            /** Schedule Cron */
            schedule_cron: string;
            /** Source Count */
            source_count: number;
            /** Sources */
            sources: components["schemas"]["CollectionSourceResponse"][];
            /** Status */
            status: string;
            /** Updated At */
            updated_at?: string | null;
        };
        /** CollectionSourceResponse */
        CollectionSourceResponse: {
            /** Acquisition Count */
            acquisition_count: number;
            /** Collection Status */
            collection_status: string;
            /** Config */
            config: {
                [key: string]: unknown;
            };
            /** Created At */
            created_at?: string | null;
            /** Enabled */
            enabled: boolean;
            /** Id */
            id: string;
            /** Last Error */
            last_error: string;
            /** Last Failure At */
            last_failure_at?: string | null;
            /** Last Success At */
            last_success_at?: string | null;
            /** Name */
            name: string;
            /** Next Run At */
            next_run_at?: string | null;
            /** Plan Id */
            plan_id: string;
            /** Schedule Cron */
            schedule_cron: string;
            /** Source Type */
            source_type: string;
            /** Total Records Acquired */
            total_records_acquired: number;
        };
        /** CommunityItem */
        CommunityItem: {
            /** Community Id */
            community_id: number;
            /** Members */
            members: components["schemas"]["GraphMemberItem"][];
            /** Size */
            size: number;
        };
        /** ConnectorTypeItem */
        ConnectorTypeItem: {
            /** Description */
            description: string;
            /** Source Type */
            source_type: string;
        };
        /** CoverageItem */
        CoverageItem: {
            /** Documents */
            documents: number;
            /** Entities */
            entities: number;
            /** Entity Type Counts */
            entity_type_counts: {
                [key: string]: number;
            };
            /** Isolated */
            isolated: number;
            /** Isolated Names */
            isolated_names: string[];
            /** Locations */
            locations: number;
            /** Relationship Type Counts */
            relationship_type_counts: {
                [key: string]: number;
            };
            /** Relationships */
            relationships: number;
            /** Single Link */
            single_link: number;
            /** Single Link Names */
            single_link_names: string[];
            /** Ungeocoded Locations */
            ungeocoded_locations: number;
            /** Ungeocoded Names */
            ungeocoded_names: string[];
            /** Unrated Document Names */
            unrated_document_names: string[];
            /** Unrated Documents */
            unrated_documents: number;
            /** Unsourced */
            unsourced: number;
            /** Unsourced Names */
            unsourced_names: string[];
        };
        /**
         * CreateAssessmentRequest
         * @description An analyst's own assessment. The judgment and probability are theirs.
         */
        CreateAssessmentRequest: {
            /**
             * Analyst
             * @default system
             */
            analyst?: string;
            /** Entity Id */
            entity_id: string;
            /** Judgment */
            judgment: string;
            /**
             * Methodology
             * @default
             */
            methodology?: string;
            /** Probability */
            probability: number;
            /** Project Id */
            project_id: string;
        };
        /** CreateCollectionRequest */
        CreateCollectionRequest: {
            /**
             * Pir
             * @default
             */
            pir?: string;
            /**
             * Plan
             * @default []
             */
            plan?: {
                [key: string]: unknown;
            }[];
            /** Project Id */
            project_id: string;
            /**
             * Refined Pir
             * @default
             */
            refined_pir?: string;
            /**
             * Refinement
             * @default
             */
            refinement?: string;
        };
        /**
         * CreatePirRequest
         * @description Create a Priority Intelligence Requirement for a project.
         */
        CreatePirRequest: {
            /**
             * Created By
             * @default analyst
             */
            created_by?: string;
            /** Eeis */
            eeis?: string[];
            /**
             * Priority
             * @default medium
             */
            priority?: string;
            /** Project Id */
            project_id: string;
            /**
             * Refined Text
             * @default
             */
            refined_text?: string;
            /**
             * Status
             * @default OPEN
             */
            status?: string;
            /** Text */
            text: string;
            /**
             * Title
             * @default
             */
            title?: string;
        };
        /** CreatePlanRequest */
        CreatePlanRequest: {
            /**
             * Assigned To
             * @default
             */
            assigned_to?: string;
            /**
             * Created By
             * @default analyst
             */
            created_by?: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /** Name */
            name: string;
            /**
             * Pir
             * @default
             */
            pir?: string;
            /** Pir Id */
            pir_id?: string | null;
            /** Project Id */
            project_id: string;
            /**
             * Refined Pir
             * @default
             */
            refined_pir?: string;
            /**
             * Requirement
             * @default
             */
            requirement?: string;
            /** Routing Rules */
            routing_rules?: {
                [key: string]: unknown;
            };
            /**
             * Schedule Cron
             * @default
             */
            schedule_cron?: string;
            /**
             * Status
             * @default DRAFT
             */
            status?: string;
        };
        /** CreateProjectRequest */
        CreateProjectRequest: {
            /**
             * Classification Level
             * @default UNCLASSIFIED
             */
            classification_level?: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /** Name */
            name: string;
            /**
             * Priority
             * @default medium
             */
            priority?: string;
        };
        /** CreateSnapshotRequest */
        CreateSnapshotRequest: {
            /**
             * Description
             * @default
             */
            description?: string;
            /** Entity Ids */
            entity_ids: string[];
            /** Name */
            name: string;
            /** Project Id */
            project_id: string;
        };
        /** CveEnabledTechniqueItem */
        CveEnabledTechniqueItem: {
            /** Cves */
            cves: components["schemas"]["AttackRefItem"][];
            /** Technique Id */
            technique_id?: string | null;
            /** Technique Name */
            technique_name?: string | null;
        };
        /** CveResolutionResponse */
        CveResolutionResponse: {
            /** Techniques Linked */
            techniques_linked: number;
            /** Vulnerabilities */
            vulnerabilities: number;
        };
        /** D3fendCountermeasureItem */
        D3fendCountermeasureItem: {
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Name */
            name?: string | null;
        };
        /** D3fendResponse */
        D3fendResponse: {
            /** Countermeasures */
            countermeasures: components["schemas"]["D3fendCountermeasureItem"][];
            /** Degraded */
            degraded?: boolean | null;
        };
        /** DataCatalogItem */
        DataCatalogItem: {
            /** Column Count */
            column_count: number;
            /** File Format */
            file_format: string;
            /** File Size Bytes */
            file_size_bytes: number;
            /** Id */
            id: string;
            /** Ingested At */
            ingested_at?: string | null;
            /** Name */
            name: string;
            /** Original Filename */
            original_filename: string;
            /** Plan Id */
            plan_id: string;
            /** Preview Rows */
            preview_rows: {
                [key: string]: unknown;
            }[];
            /** Profiling */
            profiling: {
                [key: string]: unknown;
            };
            /** Row Count */
            row_count: number;
            /** Schema Info */
            schema_info: {
                [key: string]: unknown;
            };
            /** Source Id */
            source_id: string;
        };
        /** DateCountItem */
        DateCountItem: {
            /** Count */
            count: number;
            /** Date */
            date: string;
        };
        /** DateRangeItem */
        DateRangeItem: {
            /** End */
            end: string;
            /** Start */
            start: string;
        };
        /**
         * DegradedCounts
         * @description ``{<subsystem>: {<reason>: count}}``. Only subsystems that degraded at
         *     least once appear, so ``{}`` means nothing degraded.
         */
        DegradedCounts: {
            [key: string]: {
                [key: string]: number;
            };
        };
        /**
         * DegradedProcesses
         * @description The counts of each process that flushes them (services/telemetry.py).
         */
        DegradedProcesses: {
            api: components["schemas"]["DegradedCounts"];
            worker: components["schemas"]["DegradedCounts"];
        };
        /**
         * DegradedResponse
         * @description Degraded outcomes over the last 24 hours, per process and combined.
         */
        DegradedResponse: {
            /** History Available */
            history_available: boolean;
            processes: components["schemas"]["DegradedProcesses"];
            /** Since */
            since: string;
            total: components["schemas"]["DegradedCounts"];
        };
        /**
         * DeletedResponse
         * @description A row removed by id.
         */
        DeletedResponse: {
            /** Deleted */
            deleted: boolean;
            /** Id */
            id: string;
        };
        /** DocumentDetailResponse */
        DocumentDetailResponse: {
            /** Content */
            content: string;
            /** Entities */
            entities: components["schemas"]["DocumentEntityItem"][];
            /** Entity Count */
            entity_count: number;
            /** Highlights */
            highlights: components["schemas"]["DocumentHighlightItem"][];
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
            /** Reliability Rating */
            reliability_rating?: string | null;
            /** Summary Json */
            summary_json?: string | null;
        };
        /** DocumentEntityItem */
        DocumentEntityItem: {
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
            /** Relationship */
            relationship: string;
        };
        /** DocumentEvidenceResponse */
        DocumentEvidenceResponse: {
            /** Count */
            count: number;
            /** Document Id */
            document_id: string;
            /** Document Name */
            document_name?: string | null;
            /** Entity Name */
            entity_name: string;
            /** Passages */
            passages: components["schemas"]["EvidencePassageItem"][];
            /** Total */
            total: number;
            /** Truncated */
            truncated: boolean;
        };
        /** DocumentExcerptItem */
        DocumentExcerptItem: {
            /** Content */
            content: string;
            /** Name */
            name: string;
        };
        /** DocumentHighlightItem */
        DocumentHighlightItem: {
            /** End */
            end: number;
            /** Entity Id */
            entity_id?: string | null;
            /** Entity Name */
            entity_name: string;
            /** Entity Type */
            entity_type?: string | null;
            /** Start */
            start: number;
        };
        /** DocumentListResponse */
        DocumentListResponse: {
            /** Count */
            count: number;
            /** Documents */
            documents: components["schemas"]["DocumentSummaryItem"][];
            /** Project Exists */
            project_exists: boolean;
            /** Total */
            total: number;
            /** Truncated */
            truncated: boolean;
        };
        /** DocumentSummaryItem */
        DocumentSummaryItem: {
            /** Content Length */
            content_length: number;
            /** Created At */
            created_at: string;
            /** Entity Count */
            entity_count: number;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Reliability Rating */
            reliability_rating: string;
            /** Summary Json */
            summary_json: string;
        };
        /** EeiAssessmentItem */
        EeiAssessmentItem: {
            /** Eei */
            eei: string;
            /** Index */
            index: number;
            /** Justification */
            justification: string;
            /** Verdict */
            verdict: string;
        };
        /** EgoEdgeItem */
        EgoEdgeItem: {
            /** Confidence */
            confidence?: number | null;
            /** Rel Type */
            rel_type: string;
            /** Source Id */
            source_id: string;
            /** Target Id */
            target_id: string;
            /** Weight */
            weight?: number | null;
        };
        /** EgoNetworkResponse */
        EgoNetworkResponse: {
            /** Center */
            center: string;
            /** Edge Count */
            edge_count?: number | null;
            /** Edges */
            edges: components["schemas"]["EgoEdgeItem"][];
            /** Hops */
            hops: number;
            /** Node Count */
            node_count?: number | null;
            /** Nodes */
            nodes: components["schemas"]["EgoNodeItem"][];
        };
        /** EgoNodeItem */
        EgoNodeItem: {
            /** Entity Type */
            entity_type: string;
            /** Hop Distance */
            hop_distance: number;
            /** Id */
            id: string;
            /** Local Betweenness */
            local_betweenness: number;
            /** Local Pagerank */
            local_pagerank: number;
            /** Name */
            name: string;
        };
        /**
         * EmptyResponse
         * @description ``{}``: what a lookup with nothing to return sends.
         */
        EmptyResponse: Record<string, never>;
        /** EnrichmentConfigRequest */
        EnrichmentConfigRequest: {
            /** Auto Enabled */
            auto_enabled: boolean;
        };
        /** EnrichmentConfigResponse */
        EnrichmentConfigResponse: {
            /** Auto Enabled */
            auto_enabled: boolean;
        };
        /** EnrichmentProviderItem */
        EnrichmentProviderItem: {
            /** Auto */
            auto: boolean;
            /** Has Key */
            has_key: boolean;
            /** Name */
            name: string;
            /** Requires Key */
            requires_key: boolean;
            /** Supported Types */
            supported_types: string[];
        };
        /** EnrichmentProviderListResponse */
        EnrichmentProviderListResponse: {
            /** Providers */
            providers: components["schemas"]["EnrichmentProviderItem"][];
        };
        /** EnrichmentRunResponse */
        EnrichmentRunResponse: {
            /** Entity Id */
            entity_id?: string | null;
            /** Observable */
            observable?: string | null;
            /** Providers */
            providers: {
                [key: string]: components["schemas"]["ProviderOutcomeItem"];
            };
        };
        /** EntityContextItem */
        EntityContextItem: {
            entity: components["schemas"]["EntityProperties"];
            /** Relationship Count */
            relationship_count: number;
            /** Relationships */
            relationships: components["schemas"]["RelationshipItem"][];
        };
        /** EntityCsvExportResponse */
        EntityCsvExportResponse: {
            /** Count */
            count: number;
            /** Csv */
            csv: string;
        };
        /** EntityDetailResponse */
        EntityDetailResponse: {
            entity: components["schemas"]["EntityProperties"];
            /** Relationships */
            relationships: components["schemas"]["RelationshipItem"][];
        };
        /** EntityDocumentsResponse */
        EntityDocumentsResponse: {
            /** Count */
            count: number;
            /** Documents */
            documents: components["schemas"]["MentioningDocument"][];
            /** Total */
            total: number;
        };
        /** EntityMergeResponse */
        EntityMergeResponse: {
            /** Complete */
            complete: boolean;
            /** Dropped Edges */
            dropped_edges: number;
            /** Entities Merged */
            entities_merged: number;
            /** Entities Not Found */
            entities_not_found: string[];
            /** Entities Not Merged */
            entities_not_merged: string[];
            /** Primary Id */
            primary_id: string;
            /** Primary Name */
            primary_name?: string | null;
            /** Relationships Transferred */
            relationships_transferred: number;
        };
        /**
         * EntityProperties
         * @description An entity node's stored properties, flattened (``dict(node)``).
         *
         *     Open-ended (``extra="allow"``): nodes are schemaless, and each entity type,
         *     extraction pass, enrichment provider and analyst edit adds its own
         *     properties (``latitude``, ``asn``, ``event_datetime``, ``content`` ...).
         *     The keys every entity carries are declared; the rest pass through as stored.
         */
        EntityProperties: {
            /** Entity Category */
            entity_category?: string | null;
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Project Id */
            project_id?: string | null;
            /** Relationship Count */
            relationship_count?: number | null;
        } & {
            [key: string]: unknown;
        };
        /** EntityTimelineEventItem */
        EntityTimelineEventItem: {
            /** Date */
            date: string;
            /** Label */
            label: string;
            /** Type */
            type: string;
        };
        /** EntityTimelineResponse */
        EntityTimelineResponse: {
            /** Buckets */
            buckets: components["schemas"]["DateCountItem"][];
            date_range?: components["schemas"]["DateRangeItem"] | null;
            /** Entity Id */
            entity_id?: string | null;
            /** Entity Name */
            entity_name?: string | null;
            /** Events */
            events: components["schemas"]["EntityTimelineEventItem"][];
            /** Total Events */
            total_events?: number | null;
        };
        /** EntityTypeChangedResponse */
        EntityTypeChangedResponse: {
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** New Type */
            new_type: string;
            /** Old Type */
            old_type?: string | null;
        };
        /** EntityTypeHierarchyResponse */
        EntityTypeHierarchyResponse: {
            /** Categories */
            categories: string[];
            /** Hierarchy */
            hierarchy: {
                [key: string]: string[];
            };
        };
        /**
         * ErrorMessageResponse
         * @description A 200 that carries only an error message, e.g. ``{"error": "Entity not found"}``.
         */
        ErrorMessageResponse: {
            /** Error */
            error: string;
        };
        /**
         * EvidenceEdgeItem
         * @description A relationship a product was drawn from, with its provenance.
         */
        EvidenceEdgeItem: {
            /** Admiralty Rating */
            admiralty_rating: string;
            /** Confidence */
            confidence?: number | null;
            /** Corroboration Agreement */
            corroboration_agreement: string;
            /** Corroboration Count */
            corroboration_count: number;
            /** Evidence */
            evidence: string;
            /** Method */
            method: string;
            /** Rel Type */
            rel_type: string;
            /** Source Doc Id */
            source_doc_id: string;
            /** Source Name */
            source_name?: string | null;
            /** Target Name */
            target_name?: string | null;
        };
        /** EvidencePassage */
        EvidencePassage: {
            /** Offset */
            offset: number;
            /** Text */
            text: string;
        };
        /** EvidencePassageItem */
        EvidencePassageItem: {
            /** Entity Name */
            entity_name: string;
            /** Position */
            position: number;
            /** Text */
            text: string;
        };
        /** ExecuteRequest */
        ExecuteRequest: {
            /**
             * Max Results Per Source
             * @default 10
             */
            max_results_per_source?: number;
            /** Source Limit */
            source_limit?: number | null;
        };
        /** FileUploadResponse */
        FileUploadResponse: {
            /** Catalog Id */
            catalog_id: string;
            /** Column Count */
            column_count: number;
            /** File Format */
            file_format: string;
            /** Filename */
            filename: string;
            /** Plan Id */
            plan_id: string;
            /** Preview Rows */
            preview_rows: {
                [key: string]: unknown;
            }[];
            /** Profiling */
            profiling: {
                [key: string]: unknown;
            };
            /** Record Count */
            record_count: number;
            routing_results: components["schemas"]["UploadRoutingItem"];
            /** Schema Info */
            schema_info: {
                [key: string]: unknown;
            };
            /** Source Id */
            source_id: string;
        };
        /** GapAnalysisRequest */
        GapAnalysisRequest: {
            /** Entity Ids */
            entity_ids?: string[];
            /**
             * Focus
             * @default
             */
            focus?: string;
            /**
             * Max Hops
             * @default 2
             */
            max_hops?: number;
            /** Project Id */
            project_id: string;
            /**
             * Token Budget
             * @default 8000
             */
            token_budget?: number;
        };
        /** GapAnalysisResponse */
        GapAnalysisResponse: {
            /** Analysis */
            analysis: string;
            /** Context Edges */
            context_edges: number;
            /** Context Nodes */
            context_nodes: number;
            coverage: components["schemas"]["CoverageItem"];
            /** Focus Entities */
            focus_entities: string[];
            /** Model */
            model: string;
            /** Retrieval Mode */
            retrieval_mode: string;
            /** Skill Applied */
            skill_applied: string;
            /** Structural Gaps */
            structural_gaps: components["schemas"]["StructuralGapItem"][];
            /** Tokens Used */
            tokens_used: number;
        };
        /**
         * GenerateAssessmentRequest
         * @description Ask the model to produce an assessment from the entity's graph context.
         *
         *     Separate from `CreateAssessmentRequest`, which this endpoint used to reuse:
         *     that model requires `judgment` and `probability`, which are precisely what
         *     this endpoint exists to produce, so every caller had to invent the answer in
         *     order to ask the question. The handler already treated both as optional —
         *     `req.judgment if req.judgment else 'None provided'`, and `req.probability`
         *     only as a fallback when the model emits nothing parseable — so the two had
         *     simply drifted apart.
         */
        GenerateAssessmentRequest: {
            /**
             * Analyst
             * @default llm
             */
            analyst?: string;
            /** Entity Id */
            entity_id: string;
            /**
             * Judgment
             * @default
             */
            judgment?: string;
            /**
             * Methodology
             * @default
             */
            methodology?: string;
            /**
             * Probability
             * @default 0.5
             */
            probability?: number;
            /** Project Id */
            project_id: string;
        };
        /** GeneratedAssessmentResponse */
        GeneratedAssessmentResponse: {
            /** Assessment */
            assessment: string;
            /** Assessment Id */
            assessment_id?: string | null;
            /** Entity Id */
            entity_id?: string | null;
            /** Entity Name */
            entity_name?: string | null;
            /** Error */
            error?: string | null;
            /** Judgment */
            judgment?: string | null;
            /** Model */
            model: string;
            /** Probability */
            probability?: number | null;
            /** Probability Label */
            probability_label?: string | null;
            /** Probability Parsed */
            probability_parsed: boolean;
            /** Tokens Used */
            tokens_used: number;
        };
        /** GeneratedReportResponse */
        GeneratedReportResponse: {
            /** Content */
            content: string;
            /** Context Edges */
            context_edges: number;
            /** Context Nodes */
            context_nodes: number;
            /** Evidence */
            evidence: components["schemas"]["EvidenceEdgeItem"][];
            /** Model */
            model: string;
            /** Probability */
            probability?: number | null;
            /** Probability Parsed */
            probability_parsed?: boolean | null;
            /** Retrieval Mode */
            retrieval_mode: string;
            /** Skill Applied */
            skill_applied: string;
            /** Tokens Used */
            tokens_used: number;
        };
        /** GenerateReportRequest */
        GenerateReportRequest: {
            /**
             * Entity Ids
             * @default []
             */
            entity_ids?: string[];
            /**
             * Include Evidence
             * @default true
             */
            include_evidence?: boolean;
            /**
             * Max Hops
             * @default 2
             */
            max_hops?: number;
            /** Pir Id */
            pir_id?: string | null;
            /**
             * Probability Assessments
             * @default false
             */
            probability_assessments?: boolean;
            /** Project Id */
            project_id: string;
            /**
             * Report Type
             * @default general
             */
            report_type?: string;
            /**
             * Requirement
             * @default
             */
            requirement?: string;
            /**
             * Skill Name
             * @default report_writing
             */
            skill_name?: string;
            /**
             * Token Budget
             * @default 8000
             */
            token_budget?: number;
            /**
             * Use Vector
             * @default true
             */
            use_vector?: boolean;
        };
        /**
         * GeoEdgeItem
         * @description Two places joined through the entities they share.
         */
        GeoEdgeItem: {
            /** Shared Entities */
            shared_entities: (string | null)[];
            /** Source Coords */
            source_coords?: number[] | null;
            /** Source Id */
            source_id: string;
            /** Source Name */
            source_name: string;
            /** Target Coords */
            target_coords?: number[] | null;
            /** Target Id */
            target_id: string;
            /** Target Name */
            target_name: string;
            /** Weight */
            weight: number;
        };
        /** GeoLocationItem */
        GeoLocationItem: {
            /** Connection Count */
            connection_count?: number | null;
            /** Entity Type */
            entity_type: string;
            /** Geo Confidence */
            geo_confidence: string;
            /** Geo Source */
            geo_source: string;
            /** Geocoded */
            geocoded: boolean;
            /** Id */
            id: string;
            /** Latitude */
            latitude?: number | null;
            /** Location Type */
            location_type: string;
            /** Longitude */
            longitude?: number | null;
            /** Mgrs */
            mgrs: string;
            /** Name */
            name: string;
            /** Properties */
            properties: {
                [key: string]: unknown;
            };
            /** Relationships */
            relationships?: components["schemas"]["GeoRelationshipItem"][] | null;
        };
        /** GeoLocationsResponse */
        GeoLocationsResponse: {
            /** Edge Count */
            edge_count: number;
            /** Edges */
            edges: components["schemas"]["GeoEdgeItem"][];
            /** Geocoded */
            geocoded: number;
            /** Locations */
            locations: components["schemas"]["GeoLocationItem"][];
            /** Total */
            total: number;
        };
        /** GeoPointItem */
        GeoPointItem: {
            /** Lat */
            lat: number;
            /** Lng */
            lng: number;
        };
        /** GeoRelationshipItem */
        GeoRelationshipItem: {
            /** Confidence */
            confidence?: number | null;
            /** Direction */
            direction: string;
            /** Rel Type */
            rel_type?: string | null;
            /** Target Id */
            target_id?: string | null;
            /** Target Name */
            target_name?: string | null;
        };
        /** GeoWithinResponse */
        GeoWithinResponse: {
            bbox: components["schemas"]["BoundingBoxItem"];
            /** Count */
            count: number;
            /** Entities */
            entities: components["schemas"]["GeoLocationItem"][];
        };
        /**
         * GraphEdgeProperties
         * @description One edge with its stored properties spread flat beside its endpoints.
         *
         *     Open-ended (``extra="allow"``): every stored edge property (confidence,
         *     evidence, method, polarity, first_seen ...) is passed through as stored.
         */
        GraphEdgeProperties: {
            /** Rel Type */
            rel_type: string;
            /** Source Id */
            source_id?: string | null;
            /** Target Id */
            target_id?: string | null;
        } & {
            [key: string]: unknown;
        };
        /**
         * GraphExportResponse
         * @description The project graph as stored: node and edge property maps.
         */
        GraphExportResponse: {
            /** Edge Count */
            edge_count: number;
            /** Edges */
            edges: components["schemas"]["GraphEdgeProperties"][];
            /** Node Count */
            node_count: number;
            /** Nodes */
            nodes: components["schemas"]["GraphNodeProperties"][];
            /** Truncated */
            truncated: boolean;
        };
        /** GraphMemberItem */
        GraphMemberItem: {
            /** Entity Type */
            entity_type: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /**
         * GraphNodeProperties
         * @description Any graph node's stored properties (``properties(n)``) on a traversal.
         *
         *     Open-ended (``extra="allow"``) for the same reason as ``EntityProperties``,
         *     and looser still: a walk may end on a shared catalog node (an ATT&CK
         *     technique, a CWE), which is keyed and named differently.
         */
        GraphNodeProperties: {
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** GraphRagQueryResponse */
        GraphRagQueryResponse: {
            /** Answer */
            answer: string;
            /** Context */
            context: string;
            /** Context Edges */
            context_edges: number;
            /** Context Nodes */
            context_nodes: number;
            /** Llm Error */
            llm_error?: string | null;
            /** Model */
            model: string;
            /** Query */
            query: string;
            /** Retrieval Mode */
            retrieval_mode: string;
            /** Tokens Used */
            tokens_used: number;
            /** Vector Results */
            vector_results?: number | null;
        };
        /** GraphStatisticsResponse */
        GraphStatisticsResponse: {
            /** Components */
            components: number;
            /** Density */
            density: number;
            /** Edges */
            edges: number;
            /** Entities */
            entities: components["schemas"]["NodeStatisticsItem"][];
            /** Nodes */
            nodes: number;
            /** Project Exists */
            project_exists: boolean;
            /** Truncated */
            truncated: boolean;
        };
        /** GraphViewEdgeItem */
        GraphViewEdgeItem: {
            /** Confidence */
            confidence: number;
            /** Evidence */
            evidence: string;
            /** First Seen */
            first_seen?: string | null;
            /** Last Seen */
            last_seen?: string | null;
            /** Method */
            method: string;
            /** Polarity */
            polarity: string;
            /** Rel Type */
            rel_type: string;
            /** Source Doc Id */
            source_doc_id: string;
            /** Source Id */
            source_id: string;
            /** Target Id */
            target_id: string;
        };
        /** GraphViewNodeItem */
        GraphViewNodeItem: {
            /** Community Id */
            community_id: number;
            /** Date Precision */
            date_precision: string;
            /** Date Text */
            date_text: string;
            /** Degree */
            degree: number;
            /** Entity Category */
            entity_category: string;
            /** Entity Type */
            entity_type: string;
            /** Event Datetime */
            event_datetime: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Pagerank */
            pagerank: number;
        };
        /** GraphViewResponse */
        GraphViewResponse: {
            /** Edge Count */
            edge_count: number;
            /** Edges */
            edges: components["schemas"]["GraphViewEdgeItem"][];
            /** Node Count */
            node_count: number;
            /** Nodes */
            nodes: components["schemas"]["GraphViewNodeItem"][];
            /** Project Exists */
            project_exists: boolean;
            /** Total Nodes */
            total_nodes: number;
            /** Truncated */
            truncated: boolean;
        };
        /**
         * HealthStatus
         * @description HealthResponse plus the degraded-outcome totals (contract 1).
         */
        HealthStatus: {
            /** Degraded */
            degraded?: {
                [key: string]: number;
            };
            /**
             * Embeddings
             * @default ok
             */
            embeddings?: string;
            /** Neo4J Connected */
            neo4j_connected: boolean;
            /**
             * Ollama Connected
             * @default false
             */
            ollama_connected?: boolean;
            /** Status */
            status: string;
            /**
             * Version
             * @default 0.1.0
             */
            version?: string;
        };
        /** HistogramBinItem */
        HistogramBinItem: {
            /** By Type */
            by_type: {
                [key: string]: number;
            };
            /** Count */
            count: number;
            /** Key */
            key: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HypothesesRequest */
        HypothesesRequest: {
            /**
             * Analyst
             * @default llm
             */
            analyst?: string;
            /** Entity Ids */
            entity_ids?: string[];
            /**
             * Max Hops
             * @default 2
             */
            max_hops?: number;
            /** Project Id */
            project_id: string;
            /** Question */
            question: string;
            /**
             * Save Assessment
             * @default false
             */
            save_assessment?: boolean;
            /**
             * Token Budget
             * @default 8000
             */
            token_budget?: number;
            /**
             * Use Vector
             * @default true
             */
            use_vector?: boolean;
        };
        /** HypothesesResponse */
        HypothesesResponse: {
            /** Analysis */
            analysis: string;
            /** Assessment Id */
            assessment_id?: string | null;
            /** Context Edges */
            context_edges: number;
            /** Context Nodes */
            context_nodes: number;
            /** Focus Entities */
            focus_entities: string[];
            /** Hypotheses */
            hypotheses: components["schemas"]["HypothesisItem"][];
            /** Model */
            model: string;
            /** Probability */
            probability?: number | null;
            /** Probability Label */
            probability_label?: string | null;
            /** Question */
            question: string;
            /** Retrieval Mode */
            retrieval_mode: string;
            /** Skill Applied */
            skill_applied: string;
            /** Tokens Used */
            tokens_used: number;
            /** Vector Hits */
            vector_hits: number;
        };
        /** HypothesisItem */
        HypothesisItem: {
            /** Id */
            id: string;
            /** Probability */
            probability: number;
            /** Probability Label */
            probability_label: string;
            /** Statement */
            statement: string;
        };
        /**
         * InfluenceRequest
         * @description Typed so a malformed body is a 422 rather than a failure inside the walk.
         */
        InfluenceRequest: {
            /** Project Id */
            project_id: string;
            /** Seed Ids */
            seed_ids: string[];
            /**
             * Steps
             * @default 3
             */
            steps?: number;
            /**
             * Threshold
             * @default 0.3
             */
            threshold?: number;
        };
        /** InfluenceResponse */
        InfluenceResponse: {
            /** Reach Ratio */
            reach_ratio: number;
            /** Seeds */
            seeds: string[];
            /** Steps */
            steps: components["schemas"]["InfluenceStepItem"][];
            /** Total Activated */
            total_activated: number;
            /** Total Nodes */
            total_nodes?: number | null;
        };
        /** InfluenceStepItem */
        InfluenceStepItem: {
            /** Cumulative Count */
            cumulative_count: number;
            /** Newly Activated */
            newly_activated: components["schemas"]["GraphMemberItem"][];
            /** Step */
            step: number;
        };
        /**
         * IngestResponse
         * @description One stored document and the graph build over it. Open-ended like ``GraphBuildStats``.
         */
        IngestResponse: {
            /** Chunks */
            chunks: number;
            /** Content Truncated */
            content_truncated: boolean;
            /**
             * Dates Absorbed
             * @default 0
             */
            dates_absorbed?: number;
            /**
             * Dates Orphaned
             * @default 0
             */
            dates_orphaned?: number;
            /** Document Id */
            document_id: string;
            /** Document Name */
            document_name: string;
            /**
             * Dropped Attributes
             * @default 0
             */
            dropped_attributes?: number;
            /** Embeddings Stored */
            embeddings_stored: number;
            /**
             * Entities Created
             * @default 0
             */
            entities_created?: number;
            /**
             * Entities Filtered
             * @default 0
             */
            entities_filtered?: number;
            /**
             * Entities Merged
             * @default 0
             */
            entities_merged?: number;
            /** Indexed For Search */
            indexed_for_search: boolean;
            /**
             * Mentions Recorded
             * @default 0
             */
            mentions_recorded?: number;
            /**
             * Relationships Created
             * @default 0
             */
            relationships_created?: number;
            /**
             * Relationships Dropped
             * @default 0
             */
            relationships_dropped?: number;
            /**
             * Relationships Dropped By Reason
             * @default {}
             */
            relationships_dropped_by_reason?: {
                [key: string]: number;
            };
            /**
             * Relationships Dropped By Type
             * @default {}
             */
            relationships_dropped_by_type?: {
                [key: string]: number;
            };
            /**
             * Relationships Retired
             * @default 0
             */
            relationships_retired?: number;
        } & {
            [key: string]: unknown;
        };
        /** KeyMitigationItem */
        KeyMitigationItem: {
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
            /** Technique Count */
            technique_count: number;
        };
        /** LegacyCollectionProgressResponse */
        LegacyCollectionProgressResponse: {
            /** Collection Id */
            collection_id: string;
            /** Documents Acquired */
            documents_acquired: number;
            /** Documents In Graph */
            documents_in_graph: number;
            /** Progress */
            progress: number;
            /** Status */
            status: string;
        };
        /**
         * LegacyCollectionResponse
         * @description A legacy collection: the Collection node's stored properties, with its
         *     plan decoded from ``plan_json``.
         *
         *     Open-ended (``extra="allow"``): the node's properties are passed through as
         *     stored, and the runner adds its own (``progress``, ``updated_at``).
         */
        LegacyCollectionResponse: {
            /** Created At */
            created_at?: string | null;
            /** Documents Acquired */
            documents_acquired?: number | null;
            /** Id */
            id: string;
            /** Pir */
            pir?: string | null;
            /** Plan */
            plan: {
                [key: string]: unknown;
            }[];
            /** Progress */
            progress?: number | null;
            /** Project Id */
            project_id?: string | null;
            /** Refined Pir */
            refined_pir?: string | null;
            /** Refinement */
            refinement?: string | null;
            /** Status */
            status?: string | null;
            /** Updated At */
            updated_at?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** LegacyCollectionStartedResponse */
        LegacyCollectionStartedResponse: {
            /** Collection Id */
            collection_id: string;
            /** Status */
            status: string;
        };
        /** LegacyCollectionStatusResponse */
        LegacyCollectionStatusResponse: {
            /** Documents Acquired */
            documents_acquired: number;
            /** Progress */
            progress: number;
            /** Status */
            status?: string | null;
        };
        /** LLMConfigRequest */
        LLMConfigRequest: {
            /**
             * Model
             * @default
             */
            model?: string;
            /** Provider */
            provider: string;
        };
        /** LlmModelItem */
        LlmModelItem: {
            /** Configured */
            configured: boolean;
            /** Model */
            model: string;
            /** Params */
            params?: string | null;
            /** Provider */
            provider: string;
            /** Quantization */
            quantization?: string | null;
            /** Size Gb */
            size_gb: number;
        };
        /** LlmModelListResponse */
        LlmModelListResponse: {
            /** Active Model */
            active_model: string;
            /** Active Provider */
            active_provider: string;
            /** Models */
            models: components["schemas"]["LlmModelItem"][];
        };
        /** LLMQueryRequest */
        LLMQueryRequest: {
            /**
             * Max Tokens
             * @default 4096
             */
            max_tokens?: number;
            /** Messages */
            messages: {
                [key: string]: unknown;
            }[];
            /** Provider */
            provider?: string | null;
            /** Skill Name */
            skill_name?: string | null;
            /**
             * Stream
             * @default false
             */
            stream?: boolean;
            /**
             * System
             * @default
             */
            system?: string;
            /** System Prompt */
            system_prompt?: string | null;
            /**
             * Temperature
             * @default 0.3
             */
            temperature?: number;
        };
        /** LlmQueryResponse */
        LlmQueryResponse: {
            /** Content */
            content: string;
            /** Model */
            model: string;
            /** Probability */
            probability?: number | null;
            /** Skill Applied */
            skill_applied?: string | null;
            /** Tokens Used */
            tokens_used: number;
        };
        /** LlmRequirementsItem */
        LlmRequirementsItem: {
            /** Configuration */
            configuration: string;
            /** Message */
            message: string;
            /** Minimum Capability */
            minimum_capability: string;
            /** Supported Providers */
            supported_providers: string[];
        };
        /** LlmSelectionResponse */
        LlmSelectionResponse: {
            /** Active Model */
            active_model: string;
            /** Active Provider */
            active_provider: string;
            /** Status */
            status: string;
        };
        /** LoginRequest */
        LoginRequest: {
            /** Password */
            password: string;
            /** Username */
            username: string;
        };
        /** MentioningDocument */
        MentioningDocument: {
            /** Id */
            id: string;
            /** Mention Count */
            mention_count: number;
            /** Name */
            name: string;
            /** Passages */
            passages: components["schemas"]["EvidencePassage"][];
            /** Source Doc Id */
            source_doc_id: string;
            /** Url */
            url: string;
        };
        /** MergeEntitiesRequest */
        MergeEntitiesRequest: {
            /** Merge Ids */
            merge_ids: string[];
            /** Primary Id */
            primary_id: string;
            /** Project Id */
            project_id: string;
        };
        /** MindmapTextExportResponse */
        MindmapTextExportResponse: {
            /** Content */
            content: string;
            /** Format */
            format: string;
        };
        /** MultiAssessmentRequest */
        MultiAssessmentRequest: {
            /**
             * Analyst
             * @default system
             */
            analyst?: string;
            /** Entity Ids */
            entity_ids: string[];
            /**
             * Judgment
             * @default
             */
            judgment?: string;
            /**
             * Methodology
             * @default
             */
            methodology?: string;
            /**
             * Probability
             * @default 0.5
             */
            probability?: number;
            /** Project Id */
            project_id: string;
        };
        /** MultiAssessmentResponse */
        MultiAssessmentResponse: {
            /** Assessments */
            assessments: (components["schemas"]["AssessmentCreatedResponse"] | components["schemas"]["AssessmentErrorItem"])[];
            /** Entities */
            entities: components["schemas"]["EntityContextItem"][];
            /** Entity Count */
            entity_count: number;
        };
        /** NavigatorGradientItem */
        NavigatorGradientItem: {
            /** Colors */
            colors: string[];
            /** Maxvalue */
            maxValue: number;
            /** Minvalue */
            minValue: number;
        };
        /**
         * NavigatorLayerResponse
         * @description A MITRE ATT&CK Navigator layer (v4.5), served as a download.
         */
        NavigatorLayerResponse: {
            /** Description */
            description: string;
            /** Domain */
            domain: string;
            gradient: components["schemas"]["NavigatorGradientItem"];
            /** Hidedisabled */
            hideDisabled: boolean;
            /** Legenditems */
            legendItems: unknown[];
            /** Name */
            name: string;
            /** Showtacticrowbackground */
            showTacticRowBackground: boolean;
            /** Techniques */
            techniques: components["schemas"]["NavigatorTechniqueItem"][];
            /** Versions */
            versions: {
                [key: string]: string;
            };
        };
        /** NavigatorTechniqueItem */
        NavigatorTechniqueItem: {
            /** Color */
            color: string;
            /** Comment */
            comment: string;
            /** Enabled */
            enabled: boolean;
            /** Score */
            score: number;
            /** Tactic */
            tactic?: string | null;
            /** Techniqueid */
            techniqueID: string;
        };
        /** NearbyFeatureItem */
        NearbyFeatureItem: {
            /** Category */
            category: string;
            /** Lat */
            lat: number;
            /** Lon */
            lon: number;
            /** Name */
            name: string;
            /** Tags */
            tags: {
                [key: string]: unknown;
            };
        };
        /** NearbyFeaturesResponse */
        NearbyFeaturesResponse: {
            center?: components["schemas"]["GeoPointItem"] | null;
            /** Count */
            count: number;
            /** Error */
            error?: string | null;
            /** Features */
            features: components["schemas"]["NearbyFeatureItem"][];
            /** Radius */
            radius?: number | null;
        };
        /** NodeStatisticsItem */
        NodeStatisticsItem: {
            /** Betweenness */
            betweenness: number;
            /** Closeness */
            closeness: number;
            /** Degree */
            degree: number;
            /** Eigenvector */
            eigenvector: number;
            /** Entity Type */
            entity_type: string;
            /** Id */
            id: string;
            /** In Degree */
            in_degree: number;
            /** Name */
            name: string;
            /** Out Degree */
            out_degree: number;
            /** Pagerank */
            pagerank: number;
        };
        /** NoteCreatedResponse */
        NoteCreatedResponse: {
            /** Linked Entities */
            linked_entities: number;
            /** Note Id */
            note_id: string;
            /** Note Type */
            note_type: string;
            /** Title */
            title: string;
            /** Unlinked Entity Ids */
            unlinked_entity_ids: string[];
        };
        /** NoteRequest */
        NoteRequest: {
            /** Content */
            content: string;
            /**
             * Entity Ids
             * @default []
             */
            entity_ids?: string[];
            /**
             * Note Type
             * @default observation
             * @enum {string}
             */
            note_type?: "observation" | "hypothesis" | "question" | "conclusion";
            /** Project Id */
            project_id: string;
            /** Title */
            title: string;
        };
        /**
         * NoteResponse
         * @description A notebook entry: a Report node with ``report_type`` "notebook_entry".
         *
         *     Open-ended (``extra="allow"``) as every ``EntityProperties`` is; the fields
         *     the notebook reads are declared.
         */
        NoteResponse: {
            /** Content */
            content?: string | null;
            /** Created At */
            created_at?: string | null;
            /** Entity Category */
            entity_category?: string | null;
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Note Type */
            note_type?: string | null;
            /** Project Id */
            project_id?: string | null;
            /** Relationship Count */
            relationship_count?: number | null;
            /** Report Type */
            report_type?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** ObservedTacticItem */
        ObservedTacticItem: {
            /** Tactic Id */
            tactic_id: string;
            /** Tactic Name */
            tactic_name?: string | null;
            /** Techniques */
            techniques: components["schemas"]["ObservedTechniqueItem"][];
        };
        /** ObservedTechniqueItem */
        ObservedTechniqueItem: {
            /** Id */
            id: string;
            /** Methods */
            methods: string[];
            /** Name */
            name?: string | null;
            /** Observed Count */
            observed_count: number;
        };
        /** ParsedPlanItem */
        ParsedPlanItem: {
            /** Approved */
            approved: boolean;
            /** Description */
            description: string;
            /** Id */
            id: number;
            /** Source Type */
            source_type: string;
            /** Status */
            status: string;
        };
        /** ParsedPlanResponse */
        ParsedPlanResponse: {
            /** Count */
            count: number;
            /** Items */
            items: components["schemas"]["ParsedPlanItem"][];
        };
        /** PasswordChangedResponse */
        PasswordChangedResponse: {
            /** Status */
            status: string;
            /** Username */
            username: string;
        };
        /** PersonaActivatedResponse */
        PersonaActivatedResponse: {
            /** Active Persona */
            active_persona: string;
        };
        /** PersonaListResponse */
        PersonaListResponse: {
            /** Active Persona */
            active_persona: string;
            /** Personas */
            personas: components["schemas"]["PersonaResponse"][];
        };
        /** PersonaRequest */
        PersonaRequest: {
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Skills */
            skills: string[];
            /**
             * Temperature
             * @default 0.3
             */
            temperature?: number;
        };
        /** PersonaResponse */
        PersonaResponse: {
            /** Active */
            active: boolean;
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Skills */
            skills: string[];
            /** Temperature */
            temperature: number;
        };
        /** PirAssessmentResponse */
        PirAssessmentResponse: {
            /** Assessed Status */
            assessed_status?: string | null;
            /** Assessments */
            assessments: components["schemas"]["EeiAssessmentItem"][];
            /** Eeis Satisfied */
            eeis_satisfied: number;
            /** Eeis Total */
            eeis_total: number;
            /** Entities Considered */
            entities_considered: number;
            /** Entities Total */
            entities_total: number;
            evidence: components["schemas"]["PirEvidenceItem"];
            /** Model */
            model: string;
            /** Narrative */
            narrative: string;
            /** Pir Id */
            pir_id: string;
            /** Recommendation */
            recommendation: string;
            /** Source Limit */
            source_limit?: number | null;
            /** Sources Configured */
            sources_configured: number;
            /** Sources Used */
            sources_used: number;
            /** Sources Used All Plans */
            sources_used_all_plans: number;
            /** Status */
            status: string;
            /** Stopped On Source Limit */
            stopped_on_source_limit: boolean;
            /** Unmet Criteria */
            unmet_criteria: components["schemas"]["UnmetCriterionItem"][];
        };
        /**
         * PirEvidenceItem
         * @description What the verdicts were judged from.
         */
        PirEvidenceItem: {
            /** Budget Starved Elements */
            budget_starved_elements: number[];
            /** Dated Entities */
            dated_entities: number;
            /** Elements With Passages */
            elements_with_passages: number[];
            /** Elements Without Passages */
            elements_without_passages: number[];
            /** Embedding Dim Mismatch */
            embedding_dim_mismatch: boolean;
            /** Embedding Failed */
            embedding_failed: boolean;
            /** Embedding Fallback */
            embedding_fallback: boolean;
            /** Passages Retrieved */
            passages_retrieved: number;
            /** Retrieval Degraded */
            retrieval_degraded: boolean;
            /** Retrieval Failed For */
            retrieval_failed_for: number[];
            /** Retrieval Unavailable */
            retrieval_unavailable: boolean;
            /** Substrate */
            substrate: string;
        };
        /**
         * PirPlanLink
         * @description A collection plan raised against a PIR — the next link in the cycle.
         */
        PirPlanLink: {
            /**
             * Created At
             * @default
             */
            created_at?: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Records Acquired
             * @default 0
             */
            records_acquired?: number;
            /**
             * Source Count
             * @default 0
             */
            source_count?: number;
            /** Status */
            status: string;
        };
        /** PirRequirementsResponse */
        PirRequirementsResponse: {
            /** Counts */
            counts: {
                [key: string]: number;
            };
            /** Elements */
            elements: components["schemas"]["RequirementElementItem"][];
            /** Pir Id */
            pir_id: string;
            /** Project Id */
            project_id: string;
            /** Total */
            total: number;
        };
        /** PirResponse */
        PirResponse: {
            /**
             * Created At
             * @default
             */
            created_at?: string;
            /**
             * Created By
             * @default
             */
            created_by?: string;
            /**
             * Eeis
             * @default []
             */
            eeis?: string[];
            /** Id */
            id: string;
            /**
             * Plan Count
             * @default 0
             */
            plan_count?: number;
            /**
             * Plans
             * @default []
             */
            plans?: components["schemas"]["PirPlanLink"][];
            /**
             * Priority
             * @default medium
             */
            priority?: string;
            /** Project Id */
            project_id: string;
            /**
             * Refined Text
             * @default
             */
            refined_text?: string;
            /**
             * Status
             * @default OPEN
             */
            status?: string;
            /**
             * Text
             * @default
             */
            text?: string;
            /**
             * Title
             * @default
             */
            title?: string;
            /**
             * Updated At
             * @default
             */
            updated_at?: string;
        };
        /** PlanCancelResponse */
        PlanCancelResponse: {
            /** Job Id */
            job_id: string;
            /** Message */
            message: string;
            /** Plan Id */
            plan_id: string;
            /** Previous Status */
            previous_status: string;
            /** Status */
            status: string;
            /** Stopping */
            stopping: boolean;
        };
        /**
         * PlanExecutionStartedResponse
         * @description ``POST /execute`` (202): the plan, and how its run started.
         */
        PlanExecutionStartedResponse: {
            /** Assigned To */
            assigned_to: string;
            /** Created At */
            created_at?: string | null;
            /** Created By */
            created_by: string;
            /** Description */
            description: string;
            /** Execution Status */
            execution_status: string;
            /** Id */
            id: string;
            /** Job Id */
            job_id?: string | null;
            /** Message */
            message: string;
            /** Name */
            name: string;
            /** Next Run At */
            next_run_at?: string | null;
            /** Pir */
            pir: string;
            /** Pir Id */
            pir_id?: string | null;
            /** Project Id */
            project_id: string;
            /** Refined Pir */
            refined_pir: string;
            /** Requirement */
            requirement: string;
            /** Routing Rules */
            routing_rules: {
                [key: string]: unknown;
            };
            /** Schedule Cron */
            schedule_cron: string;
            /** Source Count */
            source_count: number;
            /** Source Limit */
            source_limit?: number | null;
            /** Sources */
            sources: components["schemas"]["CollectionSourceResponse"][];
            /** Sources Manual */
            sources_manual: number;
            /** Sources Missing Config */
            sources_missing_config: number;
            /** Sources Over Budget */
            sources_over_budget: number;
            /** Sources Queued */
            sources_queued: number;
            /** Status */
            status: string;
            /** Updated At */
            updated_at?: string | null;
            /** Warnings */
            warnings: string[];
            /** Worker Mode */
            worker_mode: string;
        };
        /**
         * PlanExecutionStatusResponse
         * @description Whether a run is in flight and how it is going, from the job table and the
         *     activity trail. Keys about the trail are absent before it has any events, and
         *     keys about the job row are absent before the plan's first run.
         */
        PlanExecutionStatusResponse: {
            /** Degraded */
            degraded?: {
                [key: string]: {
                    [key: string]: number;
                };
            } | null;
            /** Error */
            error?: string | null;
            /** Heartbeat At */
            heartbeat_at?: string | null;
            /** Job Id */
            job_id?: string | null;
            /** Job Status */
            job_status?: string | null;
            /** Last Event */
            last_event?: string | null;
            /** Message */
            message: string;
            /** Plan Id */
            plan_id: string;
            /** Seconds Since Heartbeat */
            seconds_since_heartbeat?: number | null;
            /** Seconds Since Last Event */
            seconds_since_last_event?: number | null;
            /** Sources Failed */
            sources_failed: number;
            /** Sources Succeeded */
            sources_succeeded: number;
            /** Status */
            status: string;
            /** Updated At */
            updated_at?: string | null;
        };
        /**
         * PlanFromPirResponse
         * @description A plan generated from a PIR, with how the generation went.
         */
        PlanFromPirResponse: {
            /** Assigned To */
            assigned_to: string;
            /** Created At */
            created_at?: string | null;
            /** Created By */
            created_by: string;
            /** Description */
            description: string;
            /** Eeis Captured */
            eeis_captured: number;
            /** Generation Failures */
            generation_failures: string[];
            /** Id */
            id: string;
            /** Llm Available */
            llm_available: boolean;
            /** Llm Plan Text */
            llm_plan_text: string;
            llm_requirements?: components["schemas"]["LlmRequirementsItem"] | null;
            /** Llm Status */
            llm_status: string;
            /** Name */
            name: string;
            /** Next Run At */
            next_run_at?: string | null;
            /** Pir */
            pir: string;
            /** Pir Id */
            pir_id?: string | null;
            /** Project Id */
            project_id: string;
            /** Refined Pir */
            refined_pir: string;
            /** Requirement */
            requirement: string;
            /** Routing Rules */
            routing_rules: {
                [key: string]: unknown;
            };
            /** Schedule Cron */
            schedule_cron: string;
            /** Source Count */
            source_count: number;
            /** Sources */
            sources: components["schemas"]["CollectionSourceResponse"][];
            /** Status */
            status: string;
            /** Updated At */
            updated_at?: string | null;
        };
        /** ProjectActivityItem */
        ProjectActivityItem: {
            /** Action */
            action: string;
            /** Entity Name */
            entity_name: string;
            /** Entity Type */
            entity_type: string;
            /** Id */
            id: string;
            /** Timestamp */
            timestamp: string;
        };
        /** ProjectActivityResponse */
        ProjectActivityResponse: {
            /** Activity */
            activity: components["schemas"]["ProjectActivityItem"][];
            /** Count */
            count: number;
        };
        /** ProjectBatchDeleteResponse */
        ProjectBatchDeleteResponse: {
            /** Deleted */
            deleted: number;
            /** Relational Rows Removed */
            relational_rows_removed: {
                [key: string]: number;
            };
        };
        /** ProjectDeleteResponse */
        ProjectDeleteResponse: {
            /** Entities Removed */
            entities_removed: number;
            /** Relational Rows Removed */
            relational_rows_removed: {
                [key: string]: number;
            };
            /** Status */
            status: string;
        };
        /** ProjectMemberItem */
        ProjectMemberItem: {
            /** Added At */
            added_at: string;
            /** Added By */
            added_by: string;
            /**
             * Role
             * @enum {string}
             */
            role: "owner" | "editor" | "viewer";
            /** Username */
            username: string;
        };
        /**
         * ProjectMembersResponse
         * @description A project's members, owners first. Admins are implicit owners and never listed.
         */
        ProjectMembersResponse: {
            /**
             * Access
             * @enum {string}
             */
            access: "open" | "restricted";
            /** Members */
            members: components["schemas"]["ProjectMemberItem"][];
            /** My Role */
            my_role: ("owner" | "editor" | "viewer") | null;
        };
        /** ProjectResponse */
        ProjectResponse: {
            /**
             * Access
             * @enum {string}
             */
            access: "open" | "restricted";
            /** Classification Level */
            classification_level: string;
            /**
             * Collection Count
             * @default 0
             */
            collection_count?: number;
            /**
             * Created At
             * @default
             */
            created_at?: string;
            /** Description */
            description: string;
            /**
             * Document Count
             * @default 0
             */
            document_count?: number;
            /**
             * Entity Count
             * @default 0
             */
            entity_count?: number;
            /** Id */
            id: string;
            /** My Role */
            my_role: ("owner" | "editor" | "viewer") | null;
            /** Name */
            name: string;
            /** Priority */
            priority: string;
            /**
             * Relationship Count
             * @default 0
             */
            relationship_count?: number;
            /** Status */
            status: string;
            /**
             * Updated At
             * @default
             */
            updated_at?: string;
        };
        /** ProviderOutcomeItem */
        ProviderOutcomeItem: {
            /** Properties */
            properties?: {
                [key: string]: unknown;
            } | null;
            /** Reason */
            reason?: string | null;
            /** Related */
            related?: number | null;
            /** Status */
            status: string;
        };
        /** ProxyConfigRequest */
        ProxyConfigRequest: {
            /**
             * Mode
             * @default direct
             */
            mode?: string;
            /**
             * Proxy Url
             * @default
             */
            proxy_url?: string;
            /**
             * Tor Port
             * @default 9050
             */
            tor_port?: number;
        };
        /** ProxyConfigResponse */
        ProxyConfigResponse: {
            /** Mode */
            mode: string;
            /** Tor Socks Proxy */
            tor_socks_proxy: string;
            /** Vpn Http Proxy */
            vpn_http_proxy: string;
        };
        /** ProxyModeItem */
        ProxyModeItem: {
            /** Mode */
            mode: string;
        };
        /** QueryRequest */
        QueryRequest: {
            /**
             * Max Hops
             * @default 2
             */
            max_hops?: number;
            /** Project Id */
            project_id: string;
            /** Query */
            query: string;
            /**
             * Token Budget
             * @default 8000
             */
            token_budget?: number;
            /**
             * Use Vector
             * @default true
             */
            use_vector?: boolean;
        };
        /** RegisterRequest */
        RegisterRequest: {
            /** Password */
            password: string;
            /**
             * Role
             * @default analyst
             */
            role?: string;
            /** Username */
            username: string;
        };
        /**
         * RelationshipItem
         * @description One edge touching an entity, its stored properties spread flat.
         *
         *     Open-ended (``extra="allow"``): the edge's own properties are spread onto
         *     the item as stored. The ones every extracted edge carries (the
         *     ``Relationship`` model's) are declared; an edge written by another path
         *     (an ATT&CK mapping, a CVE chain) adds its own. ``direction`` is relative to
         *     the entity asked about; ``neighbor_*`` is the other end whichever way the
         *     edge points.
         */
        RelationshipItem: {
            /** Admiralty Rating */
            admiralty_rating?: string | null;
            /** Confidence */
            confidence?: number | null;
            /** Corroboration Agreement */
            corroboration_agreement?: string | null;
            /** Corroboration Count */
            corroboration_count?: number | null;
            /** Corroboration Sources */
            corroboration_sources?: string[] | null;
            /** Direction */
            direction: string;
            /** Evidence */
            evidence?: string | null;
            /** First Seen */
            first_seen?: string | null;
            /** Id */
            id?: string | null;
            /** Last Seen */
            last_seen?: string | null;
            /** Method */
            method?: string | null;
            /** Neighbor Id */
            neighbor_id?: string | null;
            /** Neighbor Name */
            neighbor_name?: string | null;
            /** Polarity */
            polarity?: string | null;
            /** Project Id */
            project_id?: string | null;
            /** Rel Type */
            rel_type: string;
            /** Source */
            source?: string | null;
            /** Source Doc Id */
            source_doc_id?: string | null;
            /** Source Id */
            source_id?: string | null;
            /** Source Name */
            source_name?: string | null;
            /** Target Id */
            target_id?: string | null;
            /** Target Name */
            target_name?: string | null;
        } & {
            [key: string]: unknown;
        };
        /**
         * RelevantExcerptItem
         * @description A sentence that mentions a topic cluster's keywords.
         */
        RelevantExcerptItem: {
            /** Matched Keywords */
            matched_keywords: string[];
            /** Score */
            score: number;
            /** Text */
            text: string;
        };
        /** ReportExportResponse */
        ReportExportResponse: {
            /** Content */
            content: string;
            /** Report Type */
            report_type: string;
            /** Title */
            title: string;
        };
        /**
         * ReportResponse
         * @description A saved report: a Report node's stored properties.
         *
         *     Open-ended (``extra="allow"``) as every ``EntityProperties`` is; the fields
         *     the products view reads are declared.
         */
        ReportResponse: {
            /** Content */
            content?: string | null;
            /** Created At */
            created_at?: string | null;
            /** Entity Category */
            entity_category?: string | null;
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Project Id */
            project_id?: string | null;
            /** Relationship Count */
            relationship_count?: number | null;
            /** Report Type */
            report_type?: string | null;
            /** Status */
            status?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** ReportSavedResponse */
        ReportSavedResponse: {
            /** Content Length */
            content_length: number;
            /** Linked Entities */
            linked_entities: number;
            /** Report Id */
            report_id: string;
            /** Report Type */
            report_type: string;
            /** Title */
            title: string;
        };
        /** RequirementElementItem */
        RequirementElementItem: {
            /** Attempts */
            attempts: number;
            /** Confidence */
            confidence: string;
            /** Missing */
            missing: string;
            /** Ordinal */
            ordinal: number;
            /** Queries Tried */
            queries_tried: string[];
            /** Status */
            status: string;
            /** Text */
            text: string;
        };
        /** SaveReportRequest */
        SaveReportRequest: {
            /**
             * Analyst
             * @default system
             */
            analyst?: string;
            /** Content */
            content: string;
            /**
             * Entity Ids
             * @default []
             */
            entity_ids?: string[];
            /** Project Id */
            project_id: string;
            /**
             * Report Type
             * @default general
             */
            report_type?: string;
            /** Title */
            title: string;
        };
        /** SearchResponse */
        SearchResponse: {
            /** Count */
            count: number;
            /** Documents */
            documents: components["schemas"]["SearchResultItem"][];
            /** Entities */
            entities: components["schemas"]["SearchResultItem"][];
            /** Reports */
            reports: components["schemas"]["SearchResultItem"][];
            /** Results */
            results: components["schemas"]["SearchResultItem"][];
            /** Total */
            total: number;
            /** Truncated */
            truncated: boolean;
        };
        /** SearchResultItem */
        SearchResultItem: {
            /** Entity Type */
            entity_type: string;
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
            /** Preview */
            preview?: string | null;
            /** Reliability */
            reliability?: string | null;
            /** Report Type */
            report_type?: string | null;
        };
        /** SemanticSearchHit */
        SemanticSearchHit: {
            /** Chunk Index */
            chunk_index: number;
            /** Chunk Text */
            chunk_text: string;
            /** Document Id */
            document_id: string;
            /** Metadata */
            metadata: {
                [key: string]: unknown;
            };
            /** Similarity */
            similarity: number;
        };
        /** SemanticSearchRequest */
        SemanticSearchRequest: {
            /**
             * Limit
             * @default 20
             */
            limit?: number;
            /**
             * Min Similarity
             * @default 0.15
             */
            min_similarity?: number;
            /** Project Id */
            project_id: string;
            /** Query */
            query: string;
        };
        /** SemanticSearchResponse */
        SemanticSearchResponse: {
            /** Results */
            results: components["schemas"]["SemanticSearchHit"][];
            /** Total */
            total: number;
        };
        /**
         * SessionUser
         * @description Who a session belongs to. Login answers with it (the token itself is in
         *     the httpOnly cookie, out of reach of page scripts), and so does /auth/me.
         */
        SessionUser: {
            /** Role */
            role: string;
            /** Username */
            username: string;
        };
        /** SetMemberRequest */
        SetMemberRequest: {
            /**
             * Role
             * @enum {string}
             */
            role: "owner" | "editor" | "viewer";
        };
        /** ShortestPathResponse */
        ShortestPathResponse: {
            /** Edges */
            edges: components["schemas"]["TraversalEdgeItem"][];
            /** Found */
            found: boolean;
            /** Nodes */
            nodes: components["schemas"]["GraphNodeProperties"][];
            /** Path Length */
            path_length: number;
        };
        /** SkillListResponse */
        SkillListResponse: {
            /** Skills */
            skills: {
                [key: string]: unknown;
            }[];
        };
        /**
         * SnapshotDetailResponse
         * @description A snapshot with the edges among its entities. Open-ended like ``SnapshotResponse``.
         */
        SnapshotDetailResponse: {
            /** Created At */
            created_at?: string | null;
            /** Description */
            description?: string | null;
            /** Edge Count */
            edge_count: number;
            /** Edges */
            edges: components["schemas"]["SnapshotEdgeItem"][];
            /**
             * Entities
             * @default []
             */
            entities?: components["schemas"]["SnapshotEntityItem"][];
            /** Entity Count */
            entity_count?: number | null;
            /**
             * Entity Ids
             * @default []
             */
            entity_ids?: string[];
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Project Id */
            project_id?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** SnapshotEdgeItem */
        SnapshotEdgeItem: {
            /** Confidence */
            confidence?: number | null;
            /** Rel Type */
            rel_type: string;
            /** Source Id */
            source_id?: string | null;
            /** Target Id */
            target_id?: string | null;
        };
        /** SnapshotEntityItem */
        SnapshotEntityItem: {
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
        };
        /** SnapshotListResponse */
        SnapshotListResponse: {
            /** Count */
            count: number;
            /** Snapshots */
            snapshots: components["schemas"]["SnapshotResponse"][];
        };
        /**
         * SnapshotResponse
         * @description A saved subgraph (bin).
         *
         *     Open-ended (``extra="allow"``): a listed or fetched snapshot is the
         *     Snapshot node's stored properties, passed through as stored.
         */
        SnapshotResponse: {
            /** Created At */
            created_at?: string | null;
            /** Description */
            description?: string | null;
            /**
             * Entities
             * @default []
             */
            entities?: components["schemas"]["SnapshotEntityItem"][];
            /** Entity Count */
            entity_count?: number | null;
            /**
             * Entity Ids
             * @default []
             */
            entity_ids?: string[];
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Project Id */
            project_id?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** SourceEvaluationItem */
        SourceEvaluationItem: {
            /** Admiralty Rating */
            admiralty_rating: string;
            /** Corroborating Documents */
            corroborating_documents: number;
            /** Current Rating */
            current_rating: string;
            /** Document Id */
            document_id: string;
            /** Entity Count */
            entity_count: number;
            /** Name */
            name?: string | null;
        };
        /** SourceEvaluationRequest */
        SourceEvaluationRequest: {
            /**
             * Apply Ratings
             * @default false
             */
            apply_ratings?: boolean;
            /** Document Ids */
            document_ids?: string[];
            /**
             * Limit
             * @default 10
             */
            limit?: number;
            /** Project Id */
            project_id: string;
        };
        /** SourceEvaluationResponse */
        SourceEvaluationResponse: {
            /** Analysis */
            analysis: string;
            /** Documents Evaluated */
            documents_evaluated: number;
            /** Evaluations */
            evaluations: components["schemas"]["SourceEvaluationItem"][];
            /** Metrics */
            metrics: components["schemas"]["SourceMetricItem"][];
            /** Model */
            model: string;
            /** Ratings Applied */
            ratings_applied: number;
            /** Retrieval Mode */
            retrieval_mode: string;
            /** Skill Applied */
            skill_applied: string;
            /** Tokens Used */
            tokens_used: number;
        };
        /** SourceHealthItem */
        SourceHealthItem: {
            /** Disabled */
            disabled: number;
            /** Healthy */
            healthy: number;
            /** Total */
            total: number;
            /** Unhealthy */
            unhealthy: number;
        };
        /** SourceMetricItem */
        SourceMetricItem: {
            /** Content Length */
            content_length: number;
            /** Corroborating Documents */
            corroborating_documents: number;
            /** Created At */
            created_at: string;
            /** Current Rating */
            current_rating: string;
            /** Document Id */
            document_id: string;
            /** Entity Count */
            entity_count: number;
            /** Entity Names */
            entity_names: string[];
            /** Name */
            name?: string | null;
            /** Url */
            url: string;
        };
        /**
         * StatusResponse
         * @description A bare outcome: ``{"status": "deleted"}``, ``"ok"``, ``"logged_out"`` and the like.
         */
        StatusResponse: {
            /** Status */
            status: string;
        };
        /**
         * StixBundleResponse
         * @description A STIX 2.1 bundle; ``objects`` are STIX objects of mixed types.
         */
        StixBundleResponse: {
            /** Id */
            id: string;
            /** Objects */
            objects: {
                [key: string]: unknown;
            }[];
            /** Type */
            type: string;
            /** X Sentinel Omitted Entity Types */
            x_sentinel_omitted_entity_types?: {
                [key: string]: number;
            } | null;
        };
        /** StructuralGapItem */
        StructuralGapItem: {
            /** Count */
            count: number;
            /** Detail */
            detail: string;
            /** Examples */
            examples: string[];
            /** Kind */
            kind: string;
            /** Priority */
            priority: string;
            /** Title */
            title: string;
        };
        /** StructuralHoleItem */
        StructuralHoleItem: {
            /** Constraint */
            constraint: number;
            /** Degree */
            degree: number;
            /** Effective Size */
            effective_size: number;
            /** Entity Type */
            entity_type: string;
            /** Id */
            id: string;
            /** Is Broker */
            is_broker: boolean;
            /** Name */
            name: string;
        };
        /** SubgraphResponse */
        SubgraphResponse: {
            /** Edge Count */
            edge_count: number;
            /** Edges */
            edges: components["schemas"]["TraversalEdgeItem"][];
            /** Node Count */
            node_count: number;
            /** Nodes */
            nodes: components["schemas"]["GraphNodeProperties"][];
            /** Truncated */
            truncated?: boolean | null;
        };
        /**
         * SubmitPIRRequest
         * @description Submit a PIR to create a full collection plan via LLM.
         */
        SubmitPIRRequest: {
            /**
             * Created By
             * @default analyst
             */
            created_by?: string;
            /**
             * Extraction Mode
             * @default hybrid
             */
            extraction_mode?: string;
            /**
             * Pir
             * @default
             */
            pir?: string;
            /** Pir Id */
            pir_id?: string | null;
            /** Project Id */
            project_id: string;
        };
        /** SummarizeRequest */
        SummarizeRequest: {
            /** Conversation History */
            conversation_history?: {
                [key: string]: unknown;
            }[] | null;
            /**
             * Level
             * @default topic
             */
            level?: string;
            /** Project Id */
            project_id: string;
        };
        /** TimelineEventItem */
        TimelineEventItem: {
            /** Date Precision */
            date_precision?: string | null;
            /** Date Text */
            date_text?: string | null;
            /** Entity Type */
            entity_type?: string | null;
            /** Event Type */
            event_type: string;
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
            /** Timestamp */
            timestamp: string;
        };
        /** TimelineHistogramResponse */
        TimelineHistogramResponse: {
            /** Bins */
            bins: components["schemas"]["HistogramBinItem"][];
            /** Bucket */
            bucket: string;
            /** Dated */
            dated: number;
            /** Earliest */
            earliest?: string | null;
            /** Latest */
            latest?: string | null;
            /** Project Exists */
            project_exists: boolean;
            /** Undated */
            undated: number;
        };
        /** TimelineResponse */
        TimelineResponse: {
            /** Count */
            count: number;
            /** Events */
            events: components["schemas"]["TimelineEventItem"][];
            /** Offset */
            offset: number;
            /** Project Exists */
            project_exists: boolean;
            /** Total */
            total: number;
            /** Truncated */
            truncated: boolean;
            /** Types Present */
            types_present: string[];
        };
        /** TokenResponse */
        TokenResponse: {
            /** Access Token */
            access_token: string;
            /** Role */
            role: string;
            /**
             * Token Type
             * @default bearer
             */
            token_type?: string;
            /** Username */
            username: string;
        };
        /** TopicChildCreatedResponse */
        TopicChildCreatedResponse: {
            /** Name */
            name: string;
            /** Node Id */
            node_id: string;
            /** Parent Id */
            parent_id: string;
        };
        /** TopicConnectedEntityItem */
        TopicConnectedEntityItem: {
            /** Confidence */
            confidence?: number | null;
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
            /** Rel Type */
            rel_type?: string | null;
        };
        /** TopicContextEntityItem */
        TopicContextEntityItem: {
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id?: string | null;
            /** Name */
            name?: string | null;
        };
        /** TopicContextResponse */
        TopicContextResponse: {
            /** Connected Entities */
            connected_entities: components["schemas"]["TopicConnectedEntityItem"][];
            /** Document Count */
            document_count: number;
            /** Document Excerpts */
            document_excerpts: components["schemas"]["DocumentExcerptItem"][];
            /** Documents */
            documents: components["schemas"]["TopicDocumentItem"][];
            entity: components["schemas"]["TopicContextEntityItem"];
            /** Keywords */
            keywords: string[];
            /** Relationship Count */
            relationship_count?: number | null;
            /** Source Documents */
            source_documents: components["schemas"]["TopicDocumentItem"][];
        };
        /** TopicCreateRequest */
        TopicCreateRequest: {
            /**
             * Description
             * @default
             */
            description?: string;
            /** Name */
            name: string;
            /** Project Id */
            project_id: string;
        };
        /**
         * TopicCrossReferenceItem
         * @description A document that sits in more than one topic cluster.
         */
        TopicCrossReferenceItem: {
            /** Doc Id */
            doc_id: string;
            /** Doc Name */
            doc_name: string;
            /** Topic Ids */
            topic_ids: string[];
        };
        /** TopicDocumentItem */
        TopicDocumentItem: {
            /** Content Preview */
            content_preview: string;
            /** Id */
            id?: string | null;
            /** Keyword Matches */
            keyword_matches?: {
                [key: string]: number;
            } | null;
            /** Name */
            name?: string | null;
            /** Relevance Score */
            relevance_score?: number | null;
            /** Relevant Excerpts */
            relevant_excerpts?: components["schemas"]["RelevantExcerptItem"][] | null;
            /** Reliability Rating */
            reliability_rating?: string | null;
        };
        /** TopicEditRequest */
        TopicEditRequest: {
            /** Description */
            description?: string | null;
            /** Name */
            name?: string | null;
            /** Parent Id */
            parent_id?: string | null;
            /** Project Id */
            project_id: string;
        };
        /** TopicNodeDeletedResponse */
        TopicNodeDeletedResponse: {
            /** Deleted */
            deleted: boolean;
            /** Node Id */
            node_id: string;
        };
        /**
         * TopicNodeItem
         * @description One node of the topic tree: a branch, a topic cluster, a category, a
         *     document or an entity leaf.
         *
         *     Open-ended (``extra="allow"``): each kind of node carries its own keys
         *     (``keywords`` and ``doc_ids`` on clusters, ``reliability`` on documents,
         *     ``connections`` on actors, ``user_created``/``edited`` after an analyst's
         *     edit ...). A leaf has only ``id``, ``name`` and ``entity_type``.
         */
        TopicNodeItem: {
            /** Children */
            children?: components["schemas"]["TopicNodeItem"][] | null;
            /** Count */
            count?: number | null;
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
        } & {
            [key: string]: unknown;
        };
        /** TopicNodeUpdatedResponse */
        TopicNodeUpdatedResponse: {
            /** Node Id */
            node_id: string;
            /** Updated */
            updated: boolean;
        };
        /** TopicTreeResponse */
        TopicTreeResponse: {
            /** Children */
            children: components["schemas"]["TopicNodeItem"][];
            /** Cross References */
            cross_references?: components["schemas"]["TopicCrossReferenceItem"][] | null;
            /** Description */
            description?: string | null;
            /** Document Count */
            document_count: number;
            /** Edited */
            edited?: boolean | null;
            /** Edits Applied */
            edits_applied?: number | null;
            /** Edits Overlay */
            edits_overlay?: string | null;
            /** Edits Unmatched */
            edits_unmatched?: number | null;
            /** Entity Count */
            entity_count: number;
            /** Id */
            id: string;
            /** Label Source */
            label_source?: string | null;
            /** Labels Failed */
            labels_failed?: number | null;
            /** Labels Refined */
            labels_refined?: number | null;
            /** Name */
            name: string;
        };
        /**
         * TraversalEdgeItem
         * @description One edge of a traversal, its stored properties nested under ``props``.
         */
        TraversalEdgeItem: {
            /**
             * Props
             * @default {}
             */
            props?: {
                [key: string]: unknown;
            };
            /** Rel Type */
            rel_type: string;
            /** Source Id */
            source_id?: string | null;
            /** Target Id */
            target_id?: string | null;
        };
        /** UnmetCriterionItem */
        UnmetCriterionItem: {
            /** Eei */
            eei: string;
            /** Verdict */
            verdict: string;
            /** Why */
            why: string;
        };
        /** UpdateCollectionRequest */
        UpdateCollectionRequest: {
            /**
             * Plan
             * @default []
             */
            plan?: {
                [key: string]: unknown;
            }[];
            /**
             * Refined Pir
             * @default
             */
            refined_pir?: string;
            /**
             * Refinement
             * @default
             */
            refinement?: string;
            /**
             * Status
             * @default
             */
            status?: string;
        };
        /** UpdateEntityTypeRequest */
        UpdateEntityTypeRequest: {
            /** Entity Type */
            entity_type: string;
        };
        /**
         * UpdatePirRequest
         * @description Partial update — only the fields supplied are written.
         */
        UpdatePirRequest: {
            /** Eeis */
            eeis?: string[] | null;
            /** Priority */
            priority?: string | null;
            /** Refined Text */
            refined_text?: string | null;
            /** Status */
            status?: string | null;
            /** Text */
            text?: string | null;
            /** Title */
            title?: string | null;
        };
        /** UpdatePlanRequest */
        UpdatePlanRequest: {
            /** Assigned To */
            assigned_to?: string | null;
            /** Description */
            description?: string | null;
            /** Name */
            name?: string | null;
            /** Pir */
            pir?: string | null;
            /** Refined Pir */
            refined_pir?: string | null;
            /** Requirement */
            requirement?: string | null;
            /** Routing Rules */
            routing_rules?: {
                [key: string]: unknown;
            } | null;
            /** Schedule Cron */
            schedule_cron?: string | null;
            /** Status */
            status?: string | null;
        };
        /** UpdateSourceRequest */
        UpdateSourceRequest: {
            /** Config */
            config?: {
                [key: string]: unknown;
            } | null;
            /** Enabled */
            enabled?: boolean | null;
            /** Name */
            name?: string | null;
            /** Schedule Cron */
            schedule_cron?: string | null;
        };
        /** UploadRoutingItem */
        UploadRoutingItem: {
            /** Document Id */
            document_id: string;
            /** Entities Created */
            entities_created: number;
            /** Relationships Created */
            relationships_created: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** VpnActionRequest */
        VpnActionRequest: {
            /**
             * Action
             * @default start
             */
            action?: string;
        };
        /** VpnActionResponse */
        VpnActionResponse: {
            /** Ok */
            ok: boolean;
            /** Outcome */
            outcome?: string | null;
            /** Reachable */
            reachable: boolean;
        };
        /**
         * VpnStatusResponse
         * @description The VPN sidecar's state. When it cannot be reached only ``reachable`` and
         *     ``running`` (both false) are known, and the rest are null.
         */
        VpnStatusResponse: {
            /** City */
            city?: string | null;
            /** Country */
            country?: string | null;
            /** Mode */
            mode?: string | null;
            /** Public Ip */
            public_ip?: string | null;
            /** Reachable */
            reachable: boolean;
            /** Region */
            region?: string | null;
            /** Running */
            running: boolean;
            /** Status */
            status?: string | null;
        };
        /** VulnChainIngestResponse */
        VulnChainIngestResponse: {
            /** Cwes */
            cwes: number;
            /** Edges */
            edges: number;
        };
        /** VulnChainStatusItem */
        VulnChainStatusItem: {
            /** Cwes */
            cwes: number;
            /** Ingested */
            ingested: boolean;
        };
        /** WatchedEntityItem */
        WatchedEntityItem: {
            /** Entity Type */
            entity_type?: string | null;
            /** Id */
            id: string;
            /** Name */
            name?: string | null;
            /** Relationship Count */
            relationship_count: number;
        };
        /** WatchlistAddResponse */
        WatchlistAddResponse: {
            /** Entity Id */
            entity_id: string;
            /** Entity Name */
            entity_name?: string | null;
            /** Status */
            status: string;
            /** Watchlist Size */
            watchlist_size: number;
        };
        /** WatchlistRemoveResponse */
        WatchlistRemoveResponse: {
            /** Entity Id */
            entity_id: string;
            /** Status */
            status: string;
        };
        /** WatchlistRequest */
        WatchlistRequest: {
            /** Entity Id */
            entity_id: string;
            /** Project Id */
            project_id: string;
        };
        /** WatchlistResponse */
        WatchlistResponse: {
            /** Count */
            count: number;
            /** Watched Entities */
            watched_entities: components["schemas"]["WatchedEntityItem"][];
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_api_keys_api_admin_api_keys_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiKeyListResponse"];
                };
            };
        };
    };
    add_api_key_api_admin_api_keys_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApiKeyCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiKeyCreatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_api_key_api_admin_api_keys__key_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    activate_api_key_api_admin_api_keys_activate_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApiKeyActivateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApiKeyActivatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_config_api_admin_config_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminConfigResponse"];
                };
            };
        };
    };
    get_degraded_api_admin_degraded_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DegradedResponse"];
                };
            };
        };
    };
    get_enrichment_config_api_admin_enrichment_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EnrichmentConfigResponse"];
                };
            };
        };
    };
    update_enrichment_config_api_admin_enrichment_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EnrichmentConfigRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EnrichmentConfigResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_available_models_api_admin_llm_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LlmModelListResponse"];
                };
            };
        };
    };
    select_llm_api_admin_llm_select_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LLMConfigRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LlmSelectionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_proxy_config_api_admin_proxy_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProxyConfigResponse"];
                };
            };
        };
    };
    update_proxy_config_api_admin_proxy_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProxyConfigRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProxyConfigResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_vpn_status_api_admin_vpn_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VpnStatusResponse"];
                };
            };
        };
    };
    set_vpn_status_api_admin_vpn_status_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VpnActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VpnActionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    analyze_gaps_api_analysis_gaps_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GapAnalysisRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GapAnalysisResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_hypotheses_api_analysis_hypotheses_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HypothesesRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HypothesesResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    evaluate_sources_api_analysis_source_evaluation_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SourceEvaluationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceEvaluationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_assessment_api_assess_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateAssessmentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeneratedAssessmentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    assess_multiple_entities_api_assess_multi_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MultiAssessmentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MultiAssessmentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_attribution_api_attack_attribution_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttributionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    embed_api_attack_embed_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackEmbedResponse"];
                };
            };
        };
    };
    ingest_api_attack_ingest_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackIngestResponse"];
                };
            };
        };
    };
    ingest_vuln_chain_api_attack_ingest_vuln_chain_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VulnChainIngestResponse"];
                };
            };
        };
    };
    map_ttps_api_attack_map_post: {
        parameters: {
            query: {
                project_id: string;
                /** @description Also re-examine TTPs the LLM mapped before */
                remap?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackMapResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_matrix_api_attack_matrix_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackMatrixResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_navigator_layer_api_attack_navigator_layer_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NavigatorLayerResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_report_api_attack_report_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackReportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resolve_api_attack_resolve_post: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackResolveResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resolve_cve_api_attack_resolve_cve_post: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CveResolutionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_status_api_attack_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackStatusResponse"];
                };
            };
        };
    };
    get_technique_api_attack_technique__tid__get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path: {
                tid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttackTechniqueResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_d3fend_api_attack_technique__tid__d3fend_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tid: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["D3fendResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    change_password_api_auth_change_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PasswordChangedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    login_api_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionUser"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
        };
    };
    me_api_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionUser"];
                };
            };
        };
    };
    register_api_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    collection_dashboard_api_collection_dashboard_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionDashboardResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_plans_api_collection_plans_get: {
        parameters: {
            query?: {
                project_id?: string | null;
                status?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_plan_api_collection_plans_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePlanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_plan_api_collection_plans__plan_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_plan_api_collection_plans__plan_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdatePlanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_plan_api_collection_plans__plan_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeletedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_acquisitions_api_collection_plans__plan_id__acquisitions_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcquisitionLogItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    activate_plan_api_collection_plans__plan_id__activate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_activity_api_collection_plans__plan_id__activity_get: {
        parameters: {
            query?: {
                limit?: number;
                since?: string | null;
            };
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionActivityItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_plan_api_collection_plans__plan_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_plan_run_api_collection_plans__plan_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanCancelResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_catalog_api_collection_plans__plan_id__catalog_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataCatalogItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    complete_plan_api_collection_plans__plan_id__complete_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    execute_plan_endpoint_api_collection_plans__plan_id__execute_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ExecuteRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanExecutionStartedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_execution_status_api_collection_plans__plan_id__execution_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanExecutionStatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    pause_plan_api_collection_plans__plan_id__pause_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_sources_api_collection_plans__plan_id__sources_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionSourceResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_source_api_collection_plans__plan_id__sources_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddSourceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionSourceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_source_api_collection_plans__plan_id__sources__source_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
                source_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateSourceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionSourceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_source_api_collection_plans__plan_id__sources__source_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeletedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_source_acquisitions_api_collection_plans__plan_id__sources__source_id__acquisitions_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                plan_id: string;
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcquisitionLogItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_file_to_source_api_collection_plans__plan_id__sources__source_id__upload_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
                source_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_file_to_source_api_collection_plans__plan_id__sources__source_id__upload_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileUploadResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_plan_from_pir_api_collection_plans_from_pir_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SubmitPIRRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanFromPirResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_collections_api_collections_get: {
        parameters: {
            query?: {
                project_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LegacyCollectionResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_collection_api_collections_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateCollectionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LegacyCollectionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_collection_api_collections__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LegacyCollectionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_collection_api_collections__task_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateCollectionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LegacyCollectionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_collection_api_collections__task_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    execute_collection_api_collections__task_id__execute_post: {
        parameters: {
            query?: {
                extraction_mode?: string;
            };
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LegacyCollectionStartedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_collection_progress_api_collections__task_id__progress_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LegacyCollectionProgressResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_collection_status_api_collections__task_id__status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LegacyCollectionStatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_collection_count_for_project_api_collections_count__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CollectionCountResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    parse_plan_api_collections_parse_plan_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParsedPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_communities_api_communities_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommunityItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_connector_types_api_connector_types_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConnectorTypeItem"][];
                };
            };
        };
    };
    get_catalog_entry_api_data_catalog__catalog_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                catalog_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataCatalogItem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_catalog_preview_api_data_catalog__catalog_id__preview_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                catalog_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogPreviewResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_documents_api_documents_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_document_api_documents__doc_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentDetailResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_evidence_for_entity_api_documents__doc_id__evidence_get: {
        parameters: {
            query: {
                entity_name: string;
            };
            header?: never;
            path: {
                doc_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentEvidenceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_enrichment_api_enrichment_entities__entity_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CachedEnrichmentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    investigate_api_enrichment_entities__entity_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EnrichmentRunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_api_enrichment_entities__entity_id__refresh_post: {
        parameters: {
            query: {
                /** @description Provider name to force-refresh */
                provider: string;
            };
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EnrichmentRunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_providers_api_enrichment_providers_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EnrichmentProviderListResponse"];
                };
            };
        };
    };
    search_entities_api_entities_get: {
        parameters: {
            query: {
                entity_type?: string | null;
                limit?: number;
                offset?: number;
                project_id: string;
                query?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityProperties"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_entity_api_entities__entity_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityDetailResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_assessment_api_entities__entity_id__assess_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateAssessmentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssessmentCreatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_entity_documents_api_entities__entity_id__documents_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityDocumentsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_entity_type_api_entities__entity_id__type_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateEntityTypeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityTypeChangedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    merge_entities_api_entities_merge_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MergeEntitiesRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityMergeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_entity_type_hierarchy_api_entity_types_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityTypeHierarchyResponse"];
                };
            };
        };
    };
    export_entities_csv_api_export_entities_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityCsvExportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_graph_json_api_export_graph_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GraphExportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_mindmap_api_export_mindmap_get: {
        parameters: {
            query: {
                format?: string;
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicTreeResponse"] | components["schemas"]["MindmapTextExportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_report_api_export_report__report_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                report_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportExportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_stix_api_export_stix_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StixBundleResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_entity_timeline_api_geo_entity_timeline_get: {
        parameters: {
            query: {
                entity_id: string;
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntityTimelineResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_geo_locations_api_geo_locations_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeoLocationsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_nearby_api_geo_nearby__entity_id__get: {
        parameters: {
            query?: {
                radius?: number;
            };
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NearbyFeaturesResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_within_api_geo_within_get: {
        parameters: {
            query: {
                max_lat: number;
                max_lng: number;
                min_lat: number;
                min_lng: number;
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeoWithinResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_full_graph_api_graph_get: {
        parameters: {
            query: {
                limit?: number;
                min_centrality?: number;
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GraphViewResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_centrality_api_graph_centrality_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CentralityItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ego_network_api_graph_ego_network__entity_id__get: {
        parameters: {
            query: {
                hops?: number;
                project_id: string;
            };
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EgoNetworkResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_influence_propagation_api_graph_influence_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InfluenceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InfluenceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_statistics_api_graph_statistics_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GraphStatisticsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_structural_holes_api_graph_structural_holes_get: {
        parameters: {
            query: {
                project_id: string;
                top_n?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StructuralHoleItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ingest_document_api_ingest_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_ingest_document_api_ingest_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IngestResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ingest_batch_api_ingest_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_ingest_batch_api_ingest_batch_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchIngestResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    llm_query_api_llm_query_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LLMQueryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LlmQueryResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_skills_api_llm_skills_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SkillListResponse"];
                };
            };
        };
    };
    list_notes_api_notebook_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_note_api_notebook_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteCreatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_note_api_notebook__note_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_note_api_notebook__note_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    find_shortest_path_api_paths__entity_id_1___entity_id_2__get: {
        parameters: {
            query?: {
                project_id?: string | null;
            };
            header?: never;
            path: {
                entity_id_1: string;
                entity_id_2: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShortestPathResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_personas_api_personas_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaListResponse"];
                };
            };
        };
    };
    create_persona_api_personas_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonaRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_persona_api_personas__persona_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    activate_persona_api_personas__persona_id__activate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaActivatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_active_persona_api_personas_active_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaResponse"] | components["schemas"]["EmptyResponse"];
                };
            };
        };
    };
    list_pirs_api_pirs_get: {
        parameters: {
            query: {
                project_id: string;
                status?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PirResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_pir_api_pirs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePirRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PirResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_pir_api_pirs__pir_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                pir_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PirResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_pir_api_pirs__pir_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                pir_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdatePirRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PirResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_pir_api_pirs__pir_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                pir_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeletedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    assess_pir_api_pirs__pir_id__assess_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                pir_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["AssessPirRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PirAssessmentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_pir_requirements_api_pirs__pir_id__requirements_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                pir_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PirRequirementsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_projects_api_projects_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"][];
                };
            };
        };
    };
    create_project_api_projects_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_api_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_project_api_projects__project_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_project_api_projects__project_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDeleteResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_activity_api_projects__project_id__activity_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectActivityResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_project_members_api_projects__project_id__members_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMembersResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_project_member_api_projects__project_id__members__username__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                username: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetMemberRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMemberItem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_project_member_api_projects__project_id__members__username__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                username: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    batch_delete_projects_api_projects_batch_delete_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BatchDeleteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectBatchDeleteResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    graph_rag_query_api_query_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QueryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GraphRagQueryResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_reports_api_reports_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_report_api_reports_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveReportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportSavedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_report_api_reports__report_id__get: {
        parameters: {
            query?: {
                project_id?: string | null;
            };
            header?: never;
            path: {
                report_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_report_api_reports__report_id__delete: {
        parameters: {
            query?: {
                project_id?: string | null;
            };
            header?: never;
            path: {
                report_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_report_api_reports_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateReportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeneratedReportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    global_search_api_search_get: {
        parameters: {
            query: {
                limit?: number;
                project_id: string;
                q: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SearchResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    semantic_search_api_search_semantic_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SemanticSearchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SemanticSearchResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_snapshots_api_snapshots_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_snapshot_api_snapshots_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateSnapshotRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_snapshot_api_snapshots__snapshot_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotDetailResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_snapshot_api_snapshots__snapshot_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatusResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_subgraph_api_subgraph__entity_id__get: {
        parameters: {
            query?: {
                hops?: number;
                project_id?: string | null;
            };
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubgraphResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_timeline_api_timeline_get: {
        parameters: {
            query: {
                limit?: number;
                offset?: number;
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TimelineResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_timeline_histogram_api_timeline_histogram_get: {
        parameters: {
            query: {
                bucket?: string;
                limit?: number;
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TimelineHistogramResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_topic_tree_api_topics_get: {
        parameters: {
            query: {
                granularity?: string;
                method?: string;
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicTreeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_topic_context_api_topics__entity_id__get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicContextResponse"] | components["schemas"]["ErrorMessageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    summarize_topic_api_topics__entity_id__summarize_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entity_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SummarizeRequest"];
            };
        };
        responses: {
            /** @description Server-sent events: `data: {"text": ...}` frames, then `data: [DONE]`; a failure is one `data: {"error": ...}` frame. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_topic_node_api_topics__node_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                node_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TopicEditRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicNodeUpdatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_topic_node_api_topics__node_id__delete: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path: {
                node_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicNodeDeletedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_topic_child_api_topics__node_id__children_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                node_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TopicCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicChildCreatedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_watchlist_api_watchlist_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WatchlistResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_to_watchlist_api_watchlist_add_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WatchlistRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WatchlistAddResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    remove_from_watchlist_api_watchlist_remove_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WatchlistRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WatchlistRemoveResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_check_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthStatus"];
                };
            };
        };
    };
}
