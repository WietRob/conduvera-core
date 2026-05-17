# Matrix OS Governance Policy

Status: current governance policy for Matrix OS release safety. This document mirrors verified repository settings after the evidence/report CI gate was enforced on `main`.

This is not a production-readiness claim, certification claim, runtime integration, dashboard, MCP runtime, production audit-retention policy, or automatic rule-enforcement policy.

## Current branch protection state

Verified repository state for `WietRob/matrix-os`, branch `main`:

| Setting | Current value | Notes |
|---|---|---|
| Branch protected | yes | `main` is protected |
| Required status checks | yes | strict required check is enabled |
| Required check context | `Evidence/report focused gate` | job from `Matrix OS Evidence Quality Gate` |
| Strict status checks | yes | branch must be up to date before merge |
| Admin enforcement | no | admins are not currently bound by branch protection |
| Required GitHub PR reviews | no | GitHub branch protection does not currently require approvals |
| Required conversation resolution | no | GitHub branch protection does not currently require resolved threads |
| Force pushes | disabled | branch protection disallows force pushes |
| Branch deletion | disabled | branch protection disallows deleting `main` |

The required check protects the evidence/report surface by running focused packaging, evidence, adapter, product-coherence, operator-report, golden-fixture, contract-version, CLI comparison, and ruff gates.

## Current release policy

Every Matrix OS release-train slice should follow this minimum policy:

1. Start from clean, updated `main`.
2. Keep the slice narrowly scoped.
3. Avoid combining runtime, adapter, UI, MCP, dashboard, governance, and docs changes unless explicitly scoped together.
4. Run the focused local gate before opening or updating a PR.
5. Open a draft PR until local gates and scope checks are complete.
6. Use Kanban review fan-out for evidence/report, CI/release, architecture/boundary, or documentation concerns depending on the slice.
7. Mark ready only after review blockers are fixed or explicitly documented as non-blocking.
8. Merge only when the required GitHub check is green and unresolved review-thread checks are clear.
9. After merge, update local `main`, rerun focused verification, and confirm `main == origin/main`.

## Required GitHub check

The current required GitHub check is:

```text
Matrix OS Evidence Quality Gate / Evidence/report focused gate
```

The branch-protection context is:

```text
Evidence/report focused gate
```

This check is required and strict. It is a quality gate for the Matrix OS evidence/report surface. It is not a production deployment gate and does not certify Matrix OS for regulated production use.

## Review model

Matrix OS currently uses two review layers:

| Layer | Current enforcement | Purpose |
|---|---|---|
| GitHub required status check | enforced | prevent untested evidence/report regressions on `main` |
| Kanban review fan-out | operational process | independent review of evidence semantics, CI gates, release boundaries, docs honesty |
| GitHub required PR approval | not enforced | optional future policy |
| GitHub required conversation resolution | not enforced | optional future policy |

The recommended near-term stance is to keep GitHub approvals non-enforced while the release train is still moving quickly, but to keep Kanban reviews mandatory for governance-sensitive slices.

## Review roles

| Role | Review responsibility | Typical surfaces |
|---|---|---|
| Evidence/report contract reviewer | report contract stability, golden-output exactness, operator-value answers | `curaops/evidence/reporting.py`, `tests/fixtures/evidence/operator_report/`, report tests |
| CI/release gate reviewer | required checks, workflow correctness, local-vs-CI parity | `.github/workflows/`, focused pytest and CLI gates |
| Documentation/release manager | status accuracy, non-overclaiming, release-train consistency | `README.md`, `docs/RELEASE_TRAIN_STATUS.md`, index docs |
| Adapter/runtime boundary reviewer | no accidental runtime execution, adapter expansion, shell interception, MCP/dashboard drift | adapter docs/code, gateway docs, runtime-adjacent changes |
| Compliance/accountability reviewer | CR/AAL/ASPICE semantics and traceability claims | compliance docs, CCC/AAL/ASPICE tests |

## CODEOWNERS policy draft

`CODEOWNERS` is present as a routing draft. It documents likely review ownership for future GitHub review enforcement.

Current policy:

- CODEOWNERS is informational routing only unless GitHub branch protection is later changed to require owner review.
- CODEOWNERS does not replace Kanban review fan-out.
- CODEOWNERS does not imply production ownership, certification authority, or regulated approval authority.

## Decision matrix for future hardening

| Option | What changes | Benefit | Cost / risk | Recommended now? |
|---|---|---|---|---|
| Required CI only | keep current strict `Evidence/report focused gate` | fast merges with regression protection | human review remains process-based | yes |
| CI + optional Kanban review | document review tasks but do not enforce in GitHub | better release discipline without GitHub friction | depends on orchestrator discipline | yes |
| CI + required GitHub approval | require at least one approving review | prevents solo merges through GitHub | can slow urgent small slices; needs reviewer availability | not yet |
| CI + conversation resolution | require all review threads resolved | prevents unresolved bot/human findings from being ignored | can block on noisy or stale comments | later |
| CI + CODEOWNERS required review | route sensitive files to owners and require owner approval | strong governance over evidence/CI/runtime boundaries | requires stable owner set and branch-protection update | prepare, do not enforce yet |
| Admin enforcement | apply branch protection to admins | strongest bypass resistance | can block emergency maintenance | later decision |

## Scope boundaries

This governance policy does not add:

- new adapters;
- runtime execution;
- dashboard or report UI;
- MCP runtime;
- Hermes/OpenCode/Zed execution;
- shell interception;
- destructive execution;
- production audit retention;
- cloud persistence;
- automatic rule enforcement;
- production-readiness or certification claims.

## Future policy change process

Any move from the current lightweight policy to harder GitHub enforcement should be a separate explicit slice that:

1. states the desired branch-protection delta;
2. verifies current settings before mutation;
3. updates this policy document and release-train docs;
4. applies the repo setting through GitHub API or UI;
5. verifies the setting after mutation;
6. records whether admins, PR reviews, conversation resolution, or CODEOWNERS review are enforced.
