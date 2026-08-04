# uv.lock-Policy — Entscheidung durch Repository-Evidence (DOD-06)

Datum: 2026-08-04
Goal: establish-canonical-pre-buildroom-system-baseline

## Entscheidung

**uv.lock gehört NICHT ins Repo.** Es ist bewusst ausgeschlossen
(.gitignore, Zeile 34–35, mit Policy-Kommentar).

## Quelle (Repository-Evidence)

1. **AGENTS.md**: KEINE Lockfile-Aussage (grep: 0 Treffer für
   lockfile/uv.lock/dependency).
2. **pyproject.toml**: Manifest existiert ([project] mit dependencies,
   [build-system], requires-python >=3.10). Kein [tool.uv]-Lockfile-Eintrag.
3. **README.md / Contributing**: KEINE Lockfile-Policy (grep: 0 Treffer).
4. **Git-Historie**: `git log --oneline --all --follow -- uv.lock` =
   0 Treffer — uv.lock war NIE in irgendeinem Commit dieses Repos.
5. **Vergleichbare Artefakte**: package-lock.json existierte nur in 2 alten
   Matrix-OS-Initialcommits (1fe1386, c490aef); frontend/package.json ist
   im aktuellen HEAD NICHT mehr vorhanden → der Frontend-Lockfile-Pfad ist
   im aktuellen Stand tot (kein frontend/-Verzeichnis mit package.json).
   Der einzige lebende Paketmanager ist uv (pyproject.toml).
6. **frontend/AGENTS.md** (Subkontext): „Stack SSoT: frontend/package.json
   (and lockfile)" — betrifft einen Bereich, der im aktuellen HEAD nicht
   existiert; keine Relevanz für uv.lock.

## Begründung

- pyproject.toml ist das deklarative Manifest; uv erzeugt uv.lock on demand
  (`uv run` / `uv sync`) und kann es aus pyproject.toml reproduzieren.
- 0 historische Vorkommen von uv.lock im Repo = kein Präzedenzfall für
  Commit; der aktuelle Workflow (uv run python -m pytest) funktioniert
  ohne committetes Lockfile.
- Ein committetes Lockfile würde bei jeder Dependency-Änderung einen
  zusätzlichen Diff erzeugen, ohne dass CI/Release es benötigt.

## Reproduzierbarer Test

```bash
# Zeigt: uv.lock wird von git ignoriert (exit 0 = ignored)
git check-ignore uv.lock

# Zeigt: kein uv.lock in der Historie
git log --oneline --all --follow -- uv.lock | wc -l   # -> 0
```

## Konsequenz für CI/Release-Reproduzierbarkeit

- CI nutzt `uv run python -m pytest` → uv löst Dependencies aus
  pyproject.toml auf; Reproduzierbarkeit über PEP 621-Metadaten + uv's
  on-demand-Lock bei sync. Für voll deterministische Releases kann
  optional ein CI-Schritt `uv lock` + Hash-Verifikation ergänzt werden —
  NICHT Teil dieses Goals.
- Kein Bruch: alle 271 Tests + 1 Skip laufen ohne committetes uv.lock.

## Status

UV_LOCK_POLICY = PROVEN (ausgeschlossen, evidence-basiert)
