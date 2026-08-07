#!/usr/bin/env python3
"""Generator for the RC3 tree digest (Finding F3 — digest formula documented).

FORMULA (exakt, wie beim RC3-Bau verwendet):
- root = releases/core/core-2026-08-07-rc3
- Dateien = sorted(root.rglob('*')), Pfad relativ zum Root
- AUSGESCHLOSSEN: tree-manifest.json selbst (Metadaten, kein Release-Inhalt)
  und Symlinks (nur Ziel referenziert)
- Für jede reguläre Datei in Sortierreihenfolge:
    digest.update(rel.encode())
    digest.update(sha256(file_bytes).hexdigest().encode())   # HEX-STRING, nicht Bytes!
- Ergebnis: hexdigest() = 6fabeade7ccb3a35...
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path.home() / ".local/share/conduvera/releases/core/core-2026-08-07-rc3"
EXCLUDE = {"tree-manifest.json"}


def compute(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if rel in EXCLUDE or p.is_symlink():
            continue
        if p.is_file():
            digest.update(rel.encode())
            digest.update(hashlib.sha256(p.read_bytes()).hexdigest().encode())
    return digest.hexdigest()


if __name__ == "__main__":
    d = compute()
    print("Tree-Digest:", d)
    print("Erwartet:   6fabeade7ccb3a35...")
    ok = d.startswith("6fabeade7ccb3a35")
    print("REPRODUZIERT:", ok)
    sys.exit(0 if ok else 1)
