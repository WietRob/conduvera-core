# Buildroom Characterization Test — Failures

Datum: 2026-08-03 · Runner: pytest 9.1.1 · Umgebung: isoliertes HOME (temp),
importierte Legacy-Quelle (`legacy/buildroom/source/`), Policy-Fixture
(`legacy/buildroom/fixtures/execution-backends.yaml`). Kein Live-State-Zugriff in
PASS-Fällen; Live-State-Abhängigkeiten sind unten klassifiziert.

## Gesamt: 270 PASS / 36 FAIL / 10 NOT_COLLECTED (historisch)

## Klassifikation der Fehler

| Klasse | Anzahl | Bedeutung |
|---|---|---|
| FAIL_LIVE_STATE_DEPENDENT | 35 | Tests laden reale Profile (`~/.hermes/profiles/.../SOUL.md`), echte ProjectPacks (`resolve_project("peekxd")`, `"curaops-vrp"`, `~/.hermes/buildroom/projects/*.yaml`) oder Fleet-Router-State. Im isolierten HOME nicht vorhanden → erwarteter Fehler ohne Live-State. |
| FAIL_MISSING_ISOLATED_FIXTURE | 1 | `test_autopilot_runner_stops_immediately_on_terminal_hold` liest `parents[1]/buildroom_autopilot_runner.sh`; Wrapper liegt unter `wrappers/`, nicht neben `tests/`. |

## Detailliste (36 FAIL)

- **legacy.buildroom.tests.test_buildroom_builder_pr_reviewer_v20.TestBuilderPrReviewerMode** :: `test_reviewer_body_contains_verdict_options` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_dreamer_yaml_robustness_v25_1.TestDreamerSOULYamlQuoting** :: `test_soul_contains_yaml_quoting_hard_rule` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_dreamer_yaml_robustness_v25_1.TestDreamerSOULYamlQuoting** :: `test_soul_example_shows_quoted_values` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_execution_governance** :: `test_real_peekxd_pack_retains_full_autonomous_policy` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_execution_governance** :: `test_real_curaops_pack_has_authorized_engineering_finish_line` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_execution_governance** :: `test_profile_contracts_contain_required_hard_rules` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_execution_governance** :: `test_profile_preloads_match_declared_execution_contracts` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_execution_governance** :: `test_governed_task_envelopes_require_execution_evidence_without_real_dispatch` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_execution_governance** :: `test_real_native_builder_and_reviewer_models_use_temporary_owner_exception` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_external_execution_runtime** :: `test_projectpacks_remain_native_and_only_peekxd_is_autonomous` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_integration_seam** :: `test_peekxd_projectpack_remains_native` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_integration_seam** :: `test_curaops_projectpack_enables_authorized_engineering_finish_line` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_no_progress** :: `test_autopilot_runner_stops_immediately_on_terminal_hold` — FAIL_MISSING_ISOLATED_FIXTURE (Test liest Path(__file__).parents[1]/buildroom_autopilot_runner.sh; Wrapper liegt unter legacy/buildroom/wrappers/, nicht neben tests/.)
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_01_resolve_project_peekxd_loads_yaml` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_02_resolve_project_dummy_loads_yaml` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_03_buildroom_loop_dry_run_project_peekxd` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_04_buildroom_loop_dry_run_project_dummy` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_06_dummy_project_uses_no_peekxd_paths` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_07_evidence_dir_comes_from_project_pack` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_08_repo_path_comes_from_project_pack` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_09_state_file_comes_from_evidence_dir` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_10_branch_prefix_comes_from_project_pack` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_11_test_command_comes_from_project_pack` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_12_strategy_files_come_from_project_pack` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_15_legacy_file_remains_compatibility_but_new_work_uses_buildroom_loop` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_buildroom_project_pack_v23_1** :: `test_evidence_path_helper_uses_project_pack_root` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_routing_rules_exist_only_in_yaml` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_programmer_override_selects_real_model` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_designer_canonical_without_active_override` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_frontend_without_design_is_blocked` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_reviewer_independence_selects_non_codex` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_gemma_unavailable_is_blocked_runtime` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_qwen_profiles_have_distinct_runtime_contracts` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_runtime_profile_models_match_router_policy` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_authorization_is_single_use_and_identity_bound` — FAIL_LIVE_STATE_DEPENDENT
- **legacy.buildroom.tests.test_capability_router_enforcement** :: `test_route_log_has_required_fields` — FAIL_LIVE_STATE_DEPENDENT

## Historisch (10 NOT_COLLECTED)

Tests, die `peekxd_buildroom_loop_v13..v19_1` importieren (historische
Orchestrator-Versionen; Quellen nicht als aktiver Code importiert, nur Hashes in
SOURCE_MANIFEST.json):
- test_buildroom_candidate_parser.py
- test_buildroom_canonical_schema_v19.py
- test_buildroom_compliance_retry_flow_v18_1.py
- test_buildroom_directive_compliance_v18.py
- test_buildroom_directive_templates_v17.py
- test_buildroom_pr_orchestration_v15.py
- test_buildroom_provider_fallback_v14.py
- test_buildroom_state_machine_v13.py
- test_buildroom_stop_after_phase_v16.py
- test_buildroom_strict_schema_v19_1.py

## Hinweise

- Keine Produktions-Semantik wurde verändert, um Tests grün zu machen.
- 'Suite passed' wird NICHT behauptet: 36 Fehler sind klassifiziert, 10 historisch.
- Fehlerklassen sind reproduzierbar (isolierte Umgebung + Fixtures, s. ORIGIN.md).
