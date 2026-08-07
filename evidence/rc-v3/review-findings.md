# Review-Findings RC3 (deleg_c8901de5) — Verdict: BESTANDEN MIT FINDINGS

**Datum:** 2026-08-07 · **Reviewer:** deleg_c8901de5 (unabhängige Session, read-only)
**Verdikt:** BESTANDEN MIT FINDINGS — 9/10 DODs voll PASS, DOD-07 teilerfüllt.
Alle Findings sind dokumentarisch/verifikatorisch; keine funktionalen Defekte,
keine Invarianz-Verletzung, keine Mutation (Porcelain 0/0/0/0 vor und nach).

## F1 (P2, dokumentarisch) — SBOM nennt 2d6641e nicht
- SBOM.spdx.json enthält keinen `sourceInfo`/`downloadLocation`-Verweis auf
  den Apache-2.0-Quell-Commit 2d6641e (nur purl).
- Anforderung "alle 5 Artefakte nennen 2d6641e" = 4/5 erfüllt (PROVENANCE.md,
  THIRD_PARTY_NOTICES.md, NOTICE, provenance-receipt.json ✓).
- Lizenz-Konklusionen selbst sind korrekt (Apache-2.0 AND LicenseRef-Proprietary).
- **Status: NICHT gefixt** — ein SBOM-Fix würde den geprüften Adapter-Head
  ändern. Überführt in Folge-Goal: "sourceInfo: 2d6641e" in SBOM.spdx.json
  beim nächsten Adapter-Release nachtragen.

## F2 (P3, dokumentarisch) — deleg_1ce08b78 nicht wörtlich dokumentiert
- rc2-review-blocked-status.json nennt deleg_779042e8/deleg_1815b51d/
  deleg_c78bf2b0 (die ersten 3 503-Abbrüche), aber nicht deleg_1ce08b78
  (4. Versuch, ebenfalls 503 ohne Verdict).
- Sachverhalt inhaltlich belegt: 503-Abbruch ohne Verdict → ersetzt durch
  deleg_d2b9aaaa = BESTANDEN 10/10.
- **Status: HIER DOKUMENTIERT** — deleg_1ce08b78 = 4. Review-Versuch (RC2),
  brach am 503/Iterations-Budget nach Prüfpunkten 1-5 ab, kein Verdict.
  Die 5 Versuche waren: 779042e8, 1815b51d, c78bf2b0, 1ce08b78 (alle 503),
  dann d2b9aaaa (BESTANDEN via lokaler Inferenz).

## F3 (P2, verifikatorisch) — Tree-Digest-Formel nicht reproduzierbar
- Manifest-Inhalt 100 % validiert (3671/3671 Dateien gegen Platte, 0
  Abweichungen), aber die Digest-Formel war nicht dokumentiert → ~270
  Re-Hash-Varianten des Reviewers matchten nicht.
- **Status: GESCHLOSSEN (ohne RC3-Mutation)** — exakte Formel + Generator:
  evidence/rc-v3/generate-tree-digest.py. Verifiziert:
  `python3 generate-tree-digest.py` → 6fabeade7ccb3a35ebdf2deaae2ff34ae59c8d2e36a01b707da2794a408d2c12
  == Manifest-Digest. RC3 blieb read-only.

## Reviewer-Transparenz
- touch-Test setzte die mtime von RC3/tree-manifest.json (Owner-utimensat);
  Inhalt unverändert (3671/3671, 903661 Bytes). Append-Write → EACCES.
- Live-PONG erzeugte Session-Artefakte nur in /tmp/rc3-wt.
