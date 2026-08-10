# LIVE Managed-Session-Proof (MXOS-SAFETY-1 / MXOS-RUNTIME-1)

**Datum:** 2026-08-10 · **Basis:** conduvera-core 63fb334cc02ee101f95c48e41de9dcfcfd5f6f9c
**Adapter:** conduvera-hermes-adapter 0.1.7 (d1cedd219478c44f6fec662f3208a4d4537f6323),
  Wheel 1e6523cbeb9240fb49d19aeb0e38be47906ad17eb3a56a03b58691f6624b602a
**Route:** workload/local (custom:litellm -> 127.0.0.1:4000, LITELLM_API_KEY aus env)
**Hermes-Binary:** /home/roberto_schmidt/.local/bin/hermes (v0.20.0)

## Exakter Start-Befehl (Work F)

```python
gw = HarnessGatewayService(registry_path="conduvera/harness/contracts/harness-registry.yaml",
                           execution_mode="LIVE")
reg = ManagedSessionRegistry("/tmp/slice-managed-reg.json")
rt = ManagedSessionRuntime(registry=reg, gateway_service=gw, worktree_base="/tmp/slice-managed-proof")
res = rt.start(task_id="MXOS-SAFETY-1", attempt_id="attempt-001",
               repo="conduvera-core", base_commit="63fb334cc02ee101f95c48e41de9dcfcfd5f6f9c",
               harness_descriptor="hermes-adapter.v1",
               model_binding={"route": "workload/local"}, timeout_s=60,
               prompt="Antworte mit genau einem Wort, ohne Punkt: PONG")
```

## Session-Identität

| Feld | Wert |
|---|---|
| session_id (Runtime) | mxs_4d3f56fe19654904 |
| adapter_session_id | mxfix_045674bda965 |
| task_id | MXOS-SAFETY-1 |
| attempt_id | attempt-001 |
| instance_id | attempt-001-<8hex> |
| ownership_class | MANAGED |
| managed | true |
| pid | 2226511 |
| pgid (scope) | 2226511 |
| boot_id | 2f59b8cf |
| start_time | 4076943 |
| command | /home/roberto_schmidt/projects/hermes-agent/venv/bin/python3 .../hermes -z ... |
| worktree | /tmp/slice-managed-proof/wt-MXOS-SAFETY-1-attempt-001 |

## Status-Ergebnis (RUNNING)

```
STATUS(running): True -> {'session_id': 'mxs_4d3f56fe19654904', 'state': 'RUNNING',
  'pid': 2226511, 'pgid': '2226511', 'adapter_session_id': 'mxfix_045674bda965'}
```
Prozess-Existenz via `ps -p 2226511 -o pid,pgid,stat,cmd`: `2226511 2226511 Rs ...` (JA).

## Cancel-Ergebnis

```
CANCEL: True -> {'session_id': 'mxs_4d3f56fe19654904', 'state': 'CANCELLED'}
PROZESS NACH CANCEL: WEG (ps -p 2226511 leer)
```

## Externe-Session-No-Adoption-Beweis

```
Extern beobachtet: pid=<Proof-Prozess> class=EXTERNAL_MANUAL_OBSERVED
EXTERN UNBERÜHRT: pid=<Proof-Prozess> lebt=JA  (nach cancel weiterhin)
```
Der externe Prozess wurde registriert (EXTERNAL_MANUAL_OBSERVED, control_rights=none),
cancel() lehnt EXTERNAL_* ab (code EXTERNAL_SESSION_NOT_CONTROLLABLE), der Prozess
wurde nie signalisiert.

## MXOS-EVIDENCE-1.0.0 Event-Kette (7 Events, alle hash-validiert)

| Event | event_hash (Präfix) |
|---|---|
| session.created | sha256:9174f90392137 |
| session.start.requested | sha256:f51230a5cb9c0 |
| session.started | sha256:c73e1f44916ac |
| session.status.observed | sha256:47c594f4644be |
| session.cancel.requested | sha256:5071d360176a6 |
| session.cancelled | sha256:66794d321e0e8 |
| session.cleanup.completed | sha256:6ce08be570515 |

Alle Events enthalten schema_version/event_id/event_type/occurred_at/producer/subject/
payload/severity/integrity/event_hash/correlation_id/run_id und validieren gegen
EventEnvelope (MXOS-EVIDENCE-1.0.0).

## Registry-Final

```
REGISTRY-FINAL: state=CANCELLED
REGISTRY-PERMISSIONS: 0o600
```

## Verknüpfte Tests (tests/test_managed_session.py, 14 passed)

1. MANAGED start lifecycle
2. RUNNING status via process fingerprint (nicht PID allein)
3. cancel() beendet den kompletten managed scope
4. cancel() lehnt EXTERNAL_MANUAL_OBSERVED ab
5. cancel() lehnt EXTERNAL_UNKNOWN ab
6. External session adoption unmöglich
7. PID-Reuse -> LOST (neuer Prozess nie kontrolliert)
8. Atomare Registry-Writes + 0600
9. MXOS-EVIDENCE event hashes validieren
10. Cleanup entfernt nur session-owned Ressourcen
11. Externe Prozessliste unverändert
