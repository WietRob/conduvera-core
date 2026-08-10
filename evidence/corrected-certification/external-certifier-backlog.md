# Externer Zertifizierungs-Runner — Backlog-Design (NICHT implementiert)

**Status:** DESIGN-ONLY (Work C, correct-conduvera-certification-record-and-stop-the-meta-loop)
**Ziel:** Eine wirklich externe Zertifizierungs-Instanz fuer kuenftige Conduvera-Release-Reviews,
die unabhaengig vom aktiven Hermes-Prozess laeuft. Keine Implementierung in diesem Goal.

## Warum

- 0.1.7-Review: 4 Delegationen brachen durch Iterationslimit/HTTP-503 ab; Selbstverifikation
  ersetzt keine unabhaengige Pruefung (INDEPENDENT_FINAL_REVIEW = NOT_COMPLETED).
- GLOBAL_REVIEW_FREEZE scheiterte am eigenen Kontrakt: orchestrator_state aenderte sich
  (Laufzeit-Side-Effekte des Hermes-Prozesses), und die Baseline darf nach Beobachtung
  des Mismatch nicht nachtraeglich angepasst werden.

## Erforderliche Eigenschaften (Backlog)

1. **Ausserhalb des aktiven Hermes-Prozesses** — eigenstaendiger Prozess/Kontext,
   kein Hermes-Agent mit Tools.
2. **Keine Hermes-Skill-/Memory-/Profil-Tools** — der Runner hat physisch keinen
   Zugriff auf skill_manage/memory/profile-Writes.
3. **Exakte Produkt-Commits read-only gemountet** — core/adapter/platform als
   ro-Mount der eingefrorenen SHAs, kein Schreibpfad ins Repo.
4. **Nur ein zufaelliges temporaeres Verzeichnis beschreibbar** — alle Ausgaben,
   Logs, Ergebnisse dorthin.
5. **Immutable Python-/Runtime-Image per Digest** — OCI-Image mit exaktem
   sha256-Digest (oder gleichwertig verifizierbares Runtime-Artefakt), inkl.
   Patch-Level.
6. **Netzwerk-Namespace waehrend des Builds deaktiviert** — nicht nur --no-index,
   sondern echte Isolation (z.B. unshare -n / --network none).
7. **Wheelhouse read-only gemountet** — die 6 hash-gesperrten Dists, ro.
8. **--require-hashes und --no-index** — wie im 0.1.7-Build-Lock etabliert.
9. **Signiertes maschinenlesbares Ergebnis** — Ergebnis-Receipt mit kryptografischer
   Signatur (Schluessel ausserhalb des Runners).
10. **Keine Repository-Mutation** — der Runner committet/pusht nichts.
11. **Kein Orchestrator-State-Checksummen-Claim** — ausser Hermes ist nachweislich
    gestoppt; Laufzeit-Side-Effekte werden nicht in Freeze-Baselines aufgenommen.
12. **Ephemere vs. persistente Autoritaets-Artefakte VOR der Baseline definiert** —
    nie nach dem Lauf reklassifiziert (Kontrakt-Konformitaet).

## Abgrenzung

- Das ist Backlog/Design. Implementierung ist ein separates, spaeteres Goal.
- Blockiert NICHT die weitere funktionale Conduvera-Entwicklung.
- Operative Produktion bleibt aus breiteren funktionalen/Runtime-Gruenden blockiert,
  nicht weil ein weiterer rekursiver Provenance-Release noetig waere.

## Referenz

- Erkenntnisse aus: evidence/corrected-certification/evidence-matrix.json (Achsen C/D/F/G),
  evidence/global-review-freeze/ (B1-Analyse, prepare-review-env.sh als Vorstufe).
