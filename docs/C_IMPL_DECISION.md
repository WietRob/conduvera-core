# Compliance Change Control Implementation Decision (Superseded Historical Note)

**Status:** HISTORICAL / NON-AUTHORITATIVE
**Purpose:** preserve the implementation-routing decision that led to package canonicalization and contract cleanup.

This document no longer freezes or replaces current PR #3 code. Treat it as historical context only. Current implementation and review decisions must come from the authoritative Compliance Change Control documents and the current PR hardening audit.

## Current canonical paths

| Area | Current path | Notes |
|------|--------------|-------|
| Compliance Change Control core | `curaops/skills/change_request/` | Python-package-safe underscore path. |
| Accountable Agent Layer core | `curaops/skills/accountable_agent/` | Python-package-safe underscore path. |
| Compliance CLI wiring | `curaops/cli/commands/skills.py` today; planned split into dedicated command modules remains a future cleanup. | Do not treat old freeze language as current policy. |

## Historical decision retained

The original decision correctly identified that public package paths should avoid hyphenated module names and that Compliance Change Control should be separated from Accountable Agent Layer concerns. That principle remains valid; the old freeze table and prototype-path references have been removed because they contradicted the current branch state.

## Current merge guidance

Do not merge PR #3 based on this historical note. Use the active hardening audit, current tests, and grep proof for professional terminology and doc/code consistency.
