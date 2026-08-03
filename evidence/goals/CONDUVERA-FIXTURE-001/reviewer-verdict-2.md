# Unabhängiges Follow-up-Review (DOD-LIVE-10) — CONDUVERA-FIXTURE-001

- Review-Typ: Unabhängiges Follow-up-Review nach REQUEST_FIX (Erst-Review: Session deleg_859998f4)
- Review-Session: frisch, ohne Implementierungskontext (unabhängig vom Builder)
- Datum: 2026-08-03
- Geprüft: goal-receipt.json (DOD-LIVE-Matrix 01–12), 7 Pflicht-Prüfpunkte read-only, SHA-256 unabhängig nachgerechnet (sha256sum)
- Keine Mutationen am Repository; einzige Write-Aktion: dieses Verdikt-Dokument (explizit beauftragt)

---

REVIEWER-VERDIKT: REQUEST_FIX

BEGRÜNDUNG:
Die tragenden Claims sind weiterhin vollständig evidence-basiert verifiziert — beide angewendeten Fixes
sind nachweisbar wirksam, und 14 von 15 im Receipt eingetragenen SHA-256 stimmen mit dem unabhängig
nachgerechneten sha256sum der referenzierten Dateien überein (inkl. der vollständigen response-Kette
response.txt → response_sha256 in process-evidence.json). Es verbleibt jedoch genau ein realer
Nachweis-Mismatch im Receipt selbst: Der DOD-LIVE-01-Eintrag (goal-receipt.json, Zeile 32) trägt einen
self-referentiellen evidence_sha256 (05b377f8…), der NICHT dem aktuellen Inhalt der goal-receipt.json
entspricht (tatsächlich: 6fd29399…). Ursache ist der nach dem FIX-2-Edit (PENDING → REQUEST_FIX) nicht
neu berechnete self-Hash. Da DOD-LIVE-11 ausdrücklich „keine hart kodierten Werte" garantiert, ist ein
inkonsistenter eingetragener Hash ein P2-Defekt im Evidence-Contract und schließt APPROVE aus
(Label-Findings-Konsistenz). Der Fix ist minimal und präzise spezifiziert; nach der Korrektur ist
ein APPROVE ohne weitere Findings zu erwarten.

FINDINGS:
1. [P2] DOD-LIVE-01 evidence_sha256 inkonsistent (goal-receipt.json Zeile 32):
   Eingetragen sha256:05b377f8ec2f70977ca64851a9297c5aa63d7856c679e1c7f57ed00839979cec,
   unabhängig berechnet für die referenzierte Datei (goal-receipt.json selbst):
   6fd2939994371de6438fc1b699763db89cd646f3a90ff50054db6449c8c4fc83. Der Wert ist nach dem
   FIX-2-Edit stale (self-referentieller Hash wurde nicht neu berechnet).
   Fix: (a) Wert auf 6fd29399… aktualisieren ODER (b) self-Reference auflösen, z. B. DOD-LIVE-01 auf
   ein externes Artefakt (evidence/checks/receipt_correction.out mit exitcode) zeigen lassen, ODER
   (c) die self-hash-Konvention explizit dokumentieren und nach jedem Receipt-Edit die Neuberechnung
   sicherstellen. Maßgeblich: eingetragener Wert muss nach dem Fix wieder dem realen sha256sum der
   referenzierten Datei entsprechen bzw. die Referenz extern sein.
2. [P2, klein] DOD-LIVE-08-Eintrag ohne eigenes evidence_sha256/exitcode (goal-receipt.json
   Zeilen 114–119): verweist nur auf evidence_path adapter_boundary.out; der Nachweis (Hash
   0e96d7ca…, exitcode 0, „5 passed") existiert zwar über DOD-LIVE-02 und evidence_checks, der
   Eintrag selbst erfüllt das eigene Kriterium „evidence_path + evidence_sha256 + exitcode" aber
   nicht. Fix: evidence_sha256 + exitcode ergänzen oder explizit auf den DOD-LIVE-02-Eintrag
   verweisen.

SHA256-CHECKS (unabhängig mit sha256sum nachgerechnet; alle Pfade relativ zu
/home/roberto_schmidt/projects/matrix-os-wt-goal-contract):
- evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json
  → 6fd2939994371de6438fc1b699763db89cd646f3a90ff50054db6449c8c4fc83
  (Receipt-Eintrag DOD-LIVE-01 behauptet 05b377f8… → MISMATCH, siehe Finding 1)
- evidence/checks/regression_full.out
  → d33b680b4ee085ad2bd691f49e7822b7fd42cc2dc6851d9d5ba220f3311ffa28 ✅ (DOD-LIVE-09)
- evidence/checks/adapter_boundary.out
  → 0e96d7ca7406320840ee2e704cbada03e2fe4b6d6aea1d667b4f685b07e7e24d ✅ (DOD-LIVE-02/08)
- evidence/checks/goal_lint_valid.out
  → a81caecb9756c1268eadaf69329bfdd84670d3d2a9350c106338565dd3ca9d8e ✅
- evidence/checks/goal_lint_incomplete.out
  → 2337ed569aa04a6b6e8ceb9a71293aa1ea8a0970ec02265eb7b2c8dbe143ca0d ✅
- evidence/checks/bootstrap_receipt.out
  → 54bca9bfaaab991bf5d0a76f7c28691b72a71f926a31155189c84767c7a2f2a1 ✅
- evidence/checks/goal_contract_tests.out
  → f83d9d610e658c2588951f9d5fcf5eb6869412bb3ff4984e533ea0cdb5fce58f ✅
- evidence/checks/fixture_slice_tests.out
  → 7b3b0d5a921d7788afd5d0591f4f23616773499e68d52f759b0a65c29bc0ff2c ✅
- fixtures/live/live-run-009-bootstrap/bootstrap-output.txt (FIX 1)
  → dec4f79d7cefde4d8bd42b025727dd1374c2b0286fa5f641a9a90de0fd7be704 ✅ (DOD-LIVE-03)
- fixtures/live/live-run-005/process-evidence.json
  → a2af6cc446dc4552d444d62290419f6a660b6b4ff73f5470e01a94fd90cb36a4 ✅ (DOD-LIVE-04)
- fixtures/live/live-run-005/mxos-evidence-live-run-005.json
  → 66845801dcab37e5b21e45d191ccdc9fb7ec8c5dcfefe1f4c132bb95c4253087 ✅ (DOD-LIVE-05)
- fixtures/live/live-run-005/response.txt
  → c8a786cab2621aba8724e063b6f391edcbb431f43228959a03c507c3eae90a8b ✅
  (entspricht exakt response_sha256 in process-evidence.json — unabhängig verifizierte Kette)
- fixtures/live/live-run-006-timeout/process-evidence.json
  → 99a564416e5c5c74f9914b6002a9d9c115056e60d5ad9165618e87139716547b ✅ (DOD-LIVE-06)
- fixtures/live/live-run-007-cancel/process-evidence.json
  → b566a3b443a388994c452b9e78799df6538e1877a5181f7f3a45cb5138d4a60e ✅ (DOD-LIVE-06)
- fixtures/live/live-run-008-reconcile/reconcile-evidence.json
  → d917d916297e71c19681ce8805c441b5617e9ead6777aaf12321313bf8414def ✅ (DOD-LIVE-07)

Ergebnis: 14/15 eingetragene Hashes korrekt; einziger Mismatch ist der self-referentielle
DOD-LIVE-01-Hash (Finding 1).

---

## Prüfprotokoll der 7 Punkte (read-only)

1. goal-receipt.json — DOD-LIVE-Matrix 01–12 vollständig; jeder PASS mit evidence_path und
   (evidence_sha256 | output_sha256 | exitcode | detail) bzw. vergleichbarem Nachweis; keine hart
   kodierten PASS-Werte ohne ausführbaren Check — bis auf Finding 1 (DOD-LIVE-01-Hash) und
   Finding 2 (DOD-LIVE-08-Eintrag). DOD-LIVE-10: REQUEST_FIX + reviewer_verdict + reviewer_confirms
   + fixes_applied dokumentiert (FIX 2 verifiziert). DOD-LIVE-11/12 sind Meta-Checks ohne Datei,
   per Inhalt nachvollziehbar.
2. evidence/checks/regression_full.out — Inhalt: „237 passed in 0.70s" ✅; exitcode 0 im Receipt
   (evidence_checks, command + timestamp) dokumentiert ✅.
3. fixtures/live/live-run-005/process-evidence.json — PID 595774, PGID 595774, create_time
   „Mo Aug 3 14:20:19 2026", exitcode 0, response CONDUVERA_FIXTURE_OK, response_exact true,
   foreign_process_invariant true ✅.
4. fixtures/live/live-run-005/response.txt — exakt „CONDUVERA_FIXTURE_OK" (21 Bytes inkl.
   Standard-Trailing-Newline); SHA-256 = response_sha256 aus process-evidence.json ✅.
5. live-run-006-timeout (PID/PGID 596261, SIGTERM→grace 15s→SIGKILL, after_sigterm, exit 0,
   beendet, foreign invariant true), live-run-007-cancel (PID/PGID 596621, SIGKILL an eigene PGID,
   exit -9, beendet, foreign invariant true), live-run-008-reconcile (PID/PGID 597595,
   pid_match check-ok, pgid_match True, overrides_external True, keine Duplikate, Cleanup nur eigene
   PGID) — alle konsistent mit Receipt-Details ✅.
6. live-run-009-bootstrap/bootstrap-output.txt (FIX 1) — Inhalt exakt
   „CONTRACT_ID=CONDUVERA-GOAL-1.0 CONTRACT_HASH=sha256:d9824e6d3f2db5b8bc55a2e74c790a622f87b8bacc0b42e21c5a82f1619eb7ee";
   contract_hash stimmt mit goal_contract/contract_hash des Receipts überein; SHA-256 =
   dec4f79d… (entspricht DOD-LIVE-03 und Vorgabe) ✅.
7. curaops/harness/registry.py + curaops/buildroom/fixture_runner.py — Core importiert KEINEN
   konkreten HermesAdapter: fixture_runner.py importiert nur curaops.evidence.contract und
   curaops.harness.registry; Adapter wird per registry.load_adapter("hermes") (Zeile 83) dynamisch
   geladen; registry.py definiert HarnessAdapterProtocol (Protocol) + HarnessAdapterRegistry mit
   importlib-Import und fail-closed-Pfaden (CAPABILITY_UNAVAILABLE statt ImportError). String
   „hermes_adapter" existiert im curaops/-Core 0× (nur in tests/, fixtures/harness-registry.yaml
   als Registry-Konfiguration und tests/goal/) ✅. adapter_boundary.out: „5 passed in 0.03s" ✅.
