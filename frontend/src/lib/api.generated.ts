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
         * @description Switch the active LLM provider and model at runtime.
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
        /** Login */
        post: operations["login_api_auth_login_post"];
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
         * @description Approve and execute a collection plan — activates and triggers autonomous acquisition.
         *
         *     Launches a background task that iterates over all sources, acquires data
         *     via registered connectors, runs entity extraction, and builds the knowledge graph.
         *     File upload sources are skipped (require manual upload).
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
         * @description Poll the execution progress of a running collection plan.
         *
         *     The in-memory plan_executor tracker only covers the synchronous plan_executor
         *     path; the agentic loop (run_agentic_loop) records progress to CollectionActivity
         *     instead. Fall back to that trail so the endpoint reflects a real agentic run
         *     (previously it always reported "idle" while a crawl was in flight).
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
         *     polarity). An entity is deleted only once every one of its edges has been
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
        /** List Projects */
        get: operations["list_projects_api_projects_get"];
        put?: never;
        /** Create Project */
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
        /** Get Report */
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
        /** ApiKeyActivateRequest */
        ApiKeyActivateRequest: {
            /** Key Id */
            key_id: string;
            /** Provider */
            provider: string;
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
        /**
         * AssessPirRequest
         * @description Optional inputs for a satisfaction assessment.
         */
        AssessPirRequest: {
            /** Source Limit */
            source_limit?: number | null;
        };
        /** BatchDeleteRequest */
        BatchDeleteRequest: {
            /** Project Ids */
            project_ids: string[];
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
        /** ChangePasswordRequest */
        ChangePasswordRequest: {
            /** Current Password */
            current_password: string;
            /** New Password */
            new_password: string;
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
        /** EnrichmentConfigRequest */
        EnrichmentConfigRequest: {
            /** Auto Enabled */
            auto_enabled: boolean;
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
        /** HealthResponse */
        HealthResponse: {
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
        /** LoginRequest */
        LoginRequest: {
            /** Password */
            password: string;
            /** Username */
            username: string;
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
        /** ProjectResponse */
        ProjectResponse: {
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
        /** SkillListResponse */
        SkillListResponse: {
            /** Skills */
            skills: {
                [key: string]: unknown;
            }[];
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
        /** WatchlistRequest */
        WatchlistRequest: {
            /** Entity Id */
            entity_id: string;
            /** Project Id */
            project_id: string;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": unknown;
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
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
}
