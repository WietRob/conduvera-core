#!/usr/bin/env python3
"""Reproduzierbarer Core-interner Managed-Live-Lauf (CONDUVERA-GOAL-1.0).

Call-Path (beweisbar, DOD-01/02):

    FixtureRunner.run()
      └─ HarnessAdapterRegistry.load_adapter("hermes")
         (Komponente der einzigen Registry-Authority HarnessGatewayRegistry)
      └─ HermesAdapter.start_session(live=True)
           ├─ isoliertes HERMES_HOME erzeugen (config custom:litellm + workload/local)
           ├─ Hermes CLI selbst spawnen (subprocess.Popen, start_new_session=True)
           ├─ PID/PGID/create_time erfassen → SessionHandle(trace_id)
           └─ Hermes → Live-LiteLLM :4000 → workload/local → Qwen → CONDUVERA_FIXTURE_OK
      └─ wait_for_completion + collect_evidence
      └─ Trace-Kette goal→task→attempt→session→adapter→pid→pgid→route→model→event
         → state/call-trace.json + MXOS-EVIDENCE-1.0.0

Voraussetzungen: Live-LiteLLM (dream-litellm), ai-stack text-Modus,
LITELLM_API_KEY in der Prozess-Umgebung (bestehende Injection; wird nie
gelesen/ausgegeben). Kein ai-stack model use, keine ODS-/Auth-Änderung.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from curaops.buildroom.fixture_runner import FixtureRunner  # noqa: E402
from curaops.harness.gateway import HarnessGatewayRegistry  # noqa: E402


def main() -> int:
    gateway = HarnessGatewayRegistry(
        adapter_registry_path=ROOT / "fixtures" / "harness-registry.yaml"
    )
    adapter = gateway.load_adapter("hermes")

    runner = FixtureRunner(
        fixture_dir=ROOT / "fixtures" / "live" / "core-run",
        route_manifest=ROOT / "fixtures" / "ods" / "route-manifest.yaml",
        adapter=adapter,
        producer={"name": "conduvera-core", "version": "0.1.0"},
        goal_id="CONDUVERA-FIXTURE-001",
        live=True,
    )
    result = runner.run(
        "Managed fixture: Core→Buildroom→Registry→Adapter→Hermes→LiteLLM→workload/local"
    )
    print(f"STATUS: {result.status}")
    print(f"FINAL: {result.final_status_readable}")

    trace_path = ROOT / "fixtures/live/core-run/state/call-trace.json"
    if trace_path.is_file():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        print(f"TRACE: {json.dumps(trace, indent=2, ensure_ascii=False)}")
    else:
        print("TRACE: fehlt — Lauf nicht komplett")
        return 1

    # Antwort exakt?
    resp_files = sorted((ROOT / "fixtures/live/core-run/worktrees").rglob("*.response.txt"))
    ok = any(f.read_text().strip() == "CONDUVERA_FIXTURE_OK" for f in resp_files)
    print(f"ANTWORT_EXAKT: {ok}")
    return 0 if (result.status == "completed" and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
