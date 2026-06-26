#!/bin/bash
#
# CuraOps - Post-Checkout Hook
#
# This hook runs after git checkout/clone to:
# - Log session activity
# - Check ASPICE compliance
# - Notify of lock status changes
#

set -e

# Get previous and current HEAD
PREV_HEAD=$1
NEW_HEAD=$2
BRANCH_CHECKOUT=$3  # 1 if branch checkout, 0 if file checkout

# Only run on branch checkouts
if [ "$BRANCH_CHECKOUT" = "0" ]; then
    exit 0
fi

echo "🔄 CuraOps - Post-Checkout"

# Check if CuraOps is available
if ! python -c "import curaops" 2>/dev/null; then
    exit 0
fi

# Log session activity (if session manager available)
python -c "
import sys
sys.path.insert(0, '.')
try:
    from curaops.skills.session_manager import AgentSessionManager
    from pathlib import Path
    import os
    
    sm = AgentSessionManager()
    sessions = sm.list_sessions()
    active = [s for s in sessions if s.status == 'active']
    
    if active:
        print(f'Active session: {active[0].session_id[:8]}...')
except Exception:
    pass
" 2>/dev/null || true

# Check ASPICE compliance (if aspice available)
python -c "
import sys
sys.path.insert(0, '.')
try:
    from curaops.skills.aspice_conflict_detector import ConflictDetector
    from pathlib import Path
    
    detector = ConflictDetector()
    conflicts = detector.detect_conflicts()
    
    if conflicts:
        critical = [c for c in conflicts if c.severity.value == 'CRITICAL']
        if critical:
            print(f'⚠️  {len(critical)} critical ASPICE conflicts detected')
            print('   Run: matrix aspice check')
except Exception:
    pass
" 2>/dev/null || true

exit 0
