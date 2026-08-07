#!/bin/bash
#
# CuraOps Safety Guard - Pre-Commit Hook
# 
# This hook prevents accidental deletion of protected paths.
# It validates all staged deletions against Safety Guard rules.
#
# Installation:
#   cp pre-commit.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Or use: matrix hooks install
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔒 CuraOps Safety Guard - Pre-Commit Hook"
echo "=========================================="

# Get the list of staged deletions
STAGED_DELETIONS=$(git diff --cached --name-only --diff-filter=D)

if [ -z "$STAGED_DELETIONS" ]; then
    echo -e "${GREEN}✓ No deletions staged${NC}"
    exit 0
fi

echo "Checking staged deletions..."

# Check if we're in a Python project with CuraOps
if python -c "import conduvera.skills.safety_guard" 2>/dev/null; then
    # Use Python Safety Guard
    BLOCKED=0
    
    for file in $STAGED_DELETIONS; do
        # Check with Safety Guard
        result=$(python -c "
import sys
from pathlib import Path
from conduvera.skills.safety_guard import SafetyGuard

try:
    sg = SafetyGuard()
    sg.validate_path('$file', 'delete')
    sys.exit(0)
except Exception as e:
    print(str(e))
    sys.exit(1)
" 2>&1) || BLOCKED=1
        
        if [ $BLOCKED -eq 1 ]; then
            echo -e "${RED}🚫 BLOCKED: $file${NC}"
            echo -e "   Reason: $result"
        else
            echo -e "${GREEN}✓ Safe: $file${NC}"
        fi
    done
    
    if [ $BLOCKED -eq 1 ]; then
        echo ""
        echo -e "${RED}ERROR: Commit blocked by Safety Guard${NC}"
        echo "One or more files are protected and cannot be deleted."
        echo ""
        echo "To bypass this check (use with caution):"
        echo "  git commit --no-verify"
        exit 1
    fi
else
    # Fallback: Check against common protected patterns
    BLOCKED=0
    
    for file in $STAGED_DELETIONS; do
        # Check against protected patterns
        if echo "$file" | grep -qE "^\.git/|^\.env|^\.env\.local|^secrets/|^production/|^backup/|^\.ssh/|^\.aws/"; then
            echo -e "${RED}🚫 BLOCKED: $file (protected path)${NC}"
            BLOCKED=1
        elif echo "$file" | grep -qE "\.key$|\.pem$|\.p12$|password|secret|credential"; then
            echo -e "${YELLOW}⚠️  WARNING: $file (contains sensitive keywords)${NC}"
            # Don't block, just warn
        else
            echo -e "${GREEN}✓ Safe: $file${NC}"
        fi
    done
    
    if [ $BLOCKED -eq 1 ]; then
        echo ""
        echo -e "${RED}ERROR: Commit blocked by Safety Guard${NC}"
        echo "Protected paths cannot be deleted."
        echo ""
        echo "To bypass this check (use with caution):"
        echo "  git commit --no-verify"
        exit 1
    fi
fi

echo ""
echo -e "${GREEN}✓ All deletions passed safety check${NC}"
exit 0
