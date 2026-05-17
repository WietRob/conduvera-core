# Matrix OS Governance Enforcement Decision

Status: decision record for the governance enforcement question after the evidence/report quality gate became required on `main`.

Decision: keep GitHub required pull-request approvals, CODEOWNERS owner review, conversation resolution, and admin enforcement non-enforced for now. Keep the strict required `Evidence/report focused gate` enforced and keep Kanban review fan-out as the operational review process for governance-sensitive slices.

This is not a production-readiness claim, certification claim, runtime integration, dashboard, MCP runtime, production audit-retention policy, or automatic rule-enforcement policy.

## Question

Should Matrix OS immediately require GitHub pull-request approval, CODEOWNERS owner review, conversation resolution, or admin enforcement in addition to the already-enforced evidence/report CI gate?

## Current verified state

Verified repository state for `WietRob/matrix-os`, branch `main`:

| Setting | Current value | Decision impact |
|---|---|---|
| Branch protected | yes | keep |
| Required status check | `Evidence/report focused gate` | keep enforced |
| Strict status checks | yes | keep enforced |
| Admin enforcement | no | do not enforce yet |
| Required GitHub pull-request approvals | no | do not enforce yet |
| Required conversation resolution | no | do not enforce yet |
| CODEOWNERS owner review | not required | keep as routing draft |
| Force pushes | disabled | keep |
| Branch deletion | disabled | keep |

## Decision

Keep the current lightweight governance posture:

1. The `Matrix OS Evidence Quality Gate / Evidence/report focused gate` remains the hard GitHub gate for `main`.
2. Kanban review fan-out remains the mandatory operational review process for governance-sensitive slices.
3. GitHub pull-request approvals remain non-enforced.
4. GitHub required conversation resolution remains non-enforced.
5. CODEOWNERS remains a routing draft, not a hard owner-review gate.
6. Admin enforcement remains off.
7. Any future setting mutation must be a separate explicit governance slice with before/after verification.

## Rationale

Matrix OS is still in a focused release-train phase. The evidence/report surface now has an enforced regression anchor, but the project still benefits from quick, narrow slices.

Hard GitHub approvals are useful once reviewer availability, ownership boundaries, and release cadence are stable. Enforcing them too early can slow small documentation, fixture, and harness-contract updates without adding much safety beyond the already-required evidence gate plus Kanban review.

The current balance is:

| Control | Enforcement | Why |
|---|---|---|
| Evidence/report CI gate | hard GitHub enforcement | prevents unverified report/evidence regressions on `main` |
| Kanban review fan-out | operational enforcement | gives independent semantic/release/docs review without GitHub bottleneck |
| CODEOWNERS | routing only | prepares future hard owner review without enabling it prematurely |
| Required GitHub approval | not enforced | avoid reviewer-availability bottleneck while release train is still moving quickly |
| Conversation resolution | not enforced | avoid blocking on stale/noisy threads until review practice matures |
| Admin enforcement | not enforced | preserve emergency maintenance ability |

## Operational policy after this decision

For governance-sensitive slices, the release orchestrator should:

1. start from clean, updated `main`;
2. keep the slice narrow;
3. run the focused local gate;
4. open a draft pull request;
5. verify the required GitHub evidence/report check;
6. create Kanban review tasks for the relevant surfaces;
7. fix concrete review blockers;
8. create re-review tasks when blockers were fixed;
9. mark ready only after local gates, required GitHub check, and Kanban review evidence are clean;
10. verify unresolved GitHub review threads before merge;
11. squash merge;
12. run post-merge verification on `main`.

## Escalation triggers for future hard enforcement

Revisit hard GitHub approvals or CODEOWNERS owner review if any of these occur:

| Trigger | Candidate response |
|---|---|
| A governance-sensitive change merges without Kanban review evidence | require one GitHub approval for governance-sensitive areas |
| A report/evidence contract regression escapes despite required CI | expand required checks or add owner review for report/evidence paths |
| Runtime, adapter, or MCP slices become frequent | require owner review for runtime-adjacent CODEOWNERS paths |
| Review comments are repeatedly ignored | enable required conversation resolution |
| Emergency/admin bypass causes drift | consider admin enforcement after emergency process exists |
| Multiple maintainers become active | require at least one non-author approval |

## Decision matrix

| Option | Decision | Why |
|---|---|---|
| Required CI only | keep | already enforced and useful |
| CI plus operational Kanban review | keep | current best balance of speed and independent review |
| CI plus required GitHub approval | defer | needs stable reviewer availability and owner model |
| CI plus required conversation resolution | defer | useful later once GitHub comments are primary review channel |
| CI plus CODEOWNERS owner review | prepare only | CODEOWNERS exists, but enforcement waits |
| Admin enforcement | defer | emergency maintenance process not yet documented |

## What this decision does not do

This decision does not add:

- new adapter;
- runtime execution;
- dashboard or report UI;
- MCP runtime;
- Hermes/OpenCode/Zed execution;
- shell interception;
- destructive execution;
- production audit retention;
- cloud persistence;
- automatic rule enforcement;
- certification or production-readiness claims;
- required GitHub pull-request approvals;
- required CODEOWNERS owner review;
- required conversation resolution;
- admin enforcement.

## Future setting-mutation checklist

A future enforcement slice that changes branch protection must include:

1. current branch-protection API evidence;
2. explicit desired setting delta;
3. updated governance policy and release docs;
4. actual GitHub API or UI mutation;
5. post-mutation branch-protection API evidence;
6. local gate results;
7. GitHub required-check result;
8. post-merge verification.
