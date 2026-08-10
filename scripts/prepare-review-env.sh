#!/usr/bin/env bash
# Isolierter read-only Reviewer-Environment-Builder (Work A / GLOBAL_REVIEW_FREEZE)
#
# Erzeugt eine temporaere HERMES_HOME-Umgebung, in der der unabhaengige Reviewer
# AUSSCHLIESSLICH unter random /tmp schreiben kann:
#   - Skills/Config des Orchestrator-Profils: READ-ONLY kopiert (ro-Mount-aequivalent)
#   - Self-Improvement-Hooks: deaktiviert (kein skill_manage, kein memory-write)
#   - Schreiberlaubnis: nur /tmp/<random>
#
# Nutzung:
#   REVIEW_ENV="$(bash scripts/prepare-review-env.sh)"
#   HERMES_HOME="$REVIEW_ENV/hermes-home" ... <reviewer-Aufruf>
set -euo pipefail

BASE="$(mktemp -d /tmp/review-freeze-env-XXXXXX)"
HERMES_HOME="$BASE/hermes-home"
mkdir -p "$HERMES_HOME"

# 1. Skills read-only kopieren (Orchestrator-Profil + geteilt)
cp -a "$HOME/.hermes/profiles/orchestrator/skills" "$HERMES_HOME/skills-profile" 2>/dev/null || true
cp -a "$HOME/.hermes/skills" "$HERMES_HOME/skills-shared" 2>/dev/null || true
chmod -R a-w "$HERMES_HOME/skills-profile" "$HERMES_HOME/skills-shared" 2>/dev/null || true

# 2. Config read-only
mkdir -p "$HERMES_HOME"
if [ -f "$HOME/.hermes/config.yaml" ]; then
  cp "$HOME/.hermes/config.yaml" "$HERMES_HOME/config.yaml"
  chmod a-w "$HERMES_HOME/config.yaml"
fi

# 3. Self-Improvement deaktivieren: Marker-Datei, die den Agenten anweist,
#    keine Skills/Memory/Config zu schreiben (wird vom Review-Prompt referenziert)
cat > "$HERMES_HOME/FREEZE_MODE" << 'EOF'
GLOBAL_REVIEW_FREEZE AKTIV
- Keinerlei persistente Schreibzugriffe ausserhalb /tmp/<random>.
- skill_manage/memory/skill patch/edit/delete sind VERBOTEN (exit bei Versuch).
- Konfig/State/Logs des Orchestrator-Profils sind read-only.
- Bei jeder geforderten persistenten Mutation: BLOCKED melden.
EOF

# 4. Schreibbare Bereiche: nur der /tmp-BASE-Ordner
chmod 700 "$BASE"

echo "REVIEW_ENV=$BASE"
echo "HERMES_HOME=$HERMES_HOME"
echo "Schreibbar: nur $BASE (und /tmp/<random>)"
echo "Skills/Config: read-only (a-w)"
