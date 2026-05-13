# Matrix OS Module Boundaries

Status: authoritative boundary map for the merged Matrix OS state as of PR #7.

## Boundary principles

1. Matrix OS owns the harness/control plane, not every possible engine.
2. Compliance Change Control owns Change Request lifecycle authority.
3. Accountable Agent Layer consumes CCC state and owns AI-assisted change accountability enforcement.
4. ASPICE Support Utilities own traceability support only.
5. External engines stay separately maintainable until adapter PRs define explicit contracts.
6. Documentation must distinguish merged runtime from planned release-train work.

## Boundary table

| Area | Inside current Matrix OS? | Owner in this repo | Notes |
|---|---:|---|---|
| Python package baseline | Yes | Foundation / Packaging / CLI Baseline | Merged in PR #4 |
| CLI shell and root commands | Yes | Foundation / Packaging / CLI Baseline | `curaops.cli.main` |
| CR lifecycle | Yes | Compliance Change Control | Merged in PR #5 |
| CR evidence generation | Yes | Compliance Change Control | CCC evidence only |
| Verification-case management | Yes | Compliance Change Control | Under `cr verification` |
| AI-assisted change accountability gate | Yes | Accountable Agent Layer | Merged in PR #6 |
| Accountable-change evidence | Yes | Accountable Agent Layer | References CCC evidence where relevant |
| ASPICE conflict detection | Yes | ASPICE Support Utilities | Merged in PR #7 |
| ASPICE bidirectional link support | Yes | ASPICE Support Utilities | Merged in PR #7 |
| UI/dashboard | Scaffolding only | Matrix OS Harness | Original Matrix UI is preserved; no production dashboard claim |
| MCP server | Contract only | Matrix OS Harness | No server implementation yet |
| Editor scaffolding | Scaffolding only | Matrix OS Harness | Existing code editor widget is preserved; no IDE plugin yet |
| Safety Guard | No | External engine / later adapter | Remains standalone OSS trust funnel |
| agent-evidence-plane | No | External sidecar / later adapter | Candidate reusable evidence/audit sidecar |
| CAS Extractor | No | Later adapter/capability | Not in merged core |
| failure-driven-loop | No | Later adapter/capability | Not in merged core |
| peekxd | No | Later adapter/capability | Not in merged core |
| OpenCode plugin | No | Later adapter/capability | Not in merged core |
| ai-router | No | Later adapter/capability | Not in merged core |

## Allowed dependencies between merged modules

| Consumer | May depend on | Boundary rule |
|---|---|---|
| Accountable Agent Layer | Compliance Change Control public API | AAL may validate linked CR state but must not own CR lifecycle transitions |
| ASPICE Support Utilities | Filesystem/project documents | ASPICE utilities should not require CCC/AAL runtime state |
| Compliance Change Control | Foundation package/CLI baseline | CCC remains the CR lifecycle authority |
| CLI commands | Corresponding module services | CLI should stay thin and not duplicate domain logic |

## Disallowed coupling

| Disallowed coupling | Reason |
|---|---|
| AAL re-implements CR approval or lifecycle rules | CCC is authoritative for CR lifecycle |
| ASPICE utilities make CR approval decisions | ASPICE owns traceability support, not change control |
| Docs claim UI/MCP/editor features are merged | They are planned scaffolding scope, not current runtime |
| Matrix OS absorbs Safety Guard or evidence-plane internals without adapter PR | External engines remain separately maintainable |
| Docs use old internal shorthand labels or context letters | Public docs must use professional module names |
| Docs advertise non-existent commands | CLI help is the source of truth |

## Naming conventions

Use these names in current docs:

| Preferred term | Avoid |
|---|---|
| Foundation / Packaging / CLI Baseline | vague foundation-only labels |
| Compliance Change Control | CCC is acceptable after first definition only |
| Accountable Agent Layer | AAL is acceptable after first definition only |
| ASPICE Support Utilities | generic traceability stuff |
| Matrix OS Harness | broad platform claims |
| External Engines / Adapters | absorbed platform components |
