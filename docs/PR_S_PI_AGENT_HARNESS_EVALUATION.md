# PR S — Pi Agent Harness Evaluation for Matrix OS Control Center Runtime Base

Status: evidence-backed architecture evaluation only. No Raspberry Pi hardware, no pi-hermes, no SSH, no runtime execution, and no new Matrix OS evidence adapter are proposed here.

## Evidence sources inspected

Pi Agent Harness sources:

- Official project website: https://pi.dev/
- Official repository: https://github.com/earendil-works/pi
- Repository README: `README.md`, official repo states "Pi Agent Harness Mono Repo" and lists `@earendil-works/pi-coding-agent`, `@earendil-works/pi-agent-core`, and `@earendil-works/pi-ai`.
- Repository API metadata: `https://api.github.com/repos/earendil-works/pi` reports public repo, TypeScript primary language, MIT license, default branch `main`, clone URL `https://github.com/earendil-works/pi.git`.
- Root package metadata: `package.json` declares private npm workspaces under `packages/*`, `type: module`, scripts `build`, `check`, `test`, `profile:tui`, and `profile:rpc`, and engine `node >=22.19.0` at repo root.
- Package metadata inspected:
  - `packages/agent/package.json`
  - `packages/ai/package.json`
  - `packages/coding-agent/package.json`
  - `packages/tui/package.json`
  - `packages/web-ui/package.json`
- Source/API inventory inspected:
  - `packages/agent/src/harness/agent-harness.ts`
  - `packages/agent/src/harness/types.ts`
  - `packages/agent/src/harness/skills.ts`
  - `packages/agent/src/harness/session/*`
  - `packages/coding-agent/src/cli.ts`
  - `packages/coding-agent/src/cli/args.ts`
  - `packages/coding-agent/src/core/*`
  - `packages/coding-agent/src/modes/*`
  - `packages/ai/src/types.ts`
  - `packages/ai/src/api-registry.ts`
  - `packages/ai/src/env-api-keys.ts`
  - `packages/ai/src/providers/*`
- Contribution/license sources:
  - `LICENSE` is MIT, copyright Mario Zechner.
  - `CONTRIBUTING.md` says new issues/PRs from new contributors are auto-closed by default and that core should stay minimal; features not belonging in core should be extensions.
  - `AGENTS.md` documents project development rules, including contribution gates and package labels.

Matrix OS sources:

- `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md`
- `docs/MATRIX_OS_EVIDENCE_ADAPTER_REGISTRY.md`
- `docs/MATRIX_OS_OPERATOR_WORKFLOW.md`
- `conduvera/harness/gateway.py`
- `conduvera/harness/operator_status.py`
- `conduvera/evidence/adapters/registry.py`
- `conduvera/evidence/reporting.py`

## A) Pi Agent Harness inventory

### Identity, structure, language, package manager

- Official repo is `earendil-works/pi`, described by GitHub metadata as "AI agent toolkit: coding agent CLI, unified LLM API, TUI & web UI libraries, Slack bot, vLLM pods".
- The README names it "Pi Agent Harness Mono Repo" and lists the core packages.
- It is a TypeScript/JavaScript npm workspace monorepo. Evidence: root `package.json` has `type: module`, `workspaces: ["packages/*", ...]`, npm scripts, `package-lock.json`, `tsconfig*.json`, and `biome.json`.
- Main package layout:
  - `packages/ai`: unified LLM API.
  - `packages/agent`: general-purpose agent runtime/harness core.
  - `packages/coding-agent`: interactive coding-agent CLI.
  - `packages/tui`: terminal UI library.
  - `packages/web-ui`: reusable web UI components for AI chat interfaces.
- Build/check commands from README/root `package.json`:
  - `npm install`
  - `npm run build`
  - `npm run check`
  - `./test.sh`
  - `./pi-test.sh`
- Root engine is `node >=22.19.0`; package engines are `node >=20.0.0`, `>=20.6.0`, or `>=22.19.0` depending on package.

### CLI entry points and modes

- `packages/coding-agent/package.json` declares `bin: { "pi": "dist/cli.js" }`; package description is "Coding agent CLI with read, bash, edit, write tools and session management".
- `packages/coding-agent/src/cli.ts` is the Node CLI entry point; it sets `process.title`, sets `PI_CODING_AGENT=true`, configures Undici proxy/timeout handling, and calls `main(process.argv.slice(2))`.
- `packages/coding-agent/src/cli/args.ts` defines `Mode = "text" | "json" | "rpc"` and supports flags for provider/model/API key, system prompt, thinking, continue/resume/fork/session/session-dir, tools, built-in tools, extensions, skills, prompt templates, themes, context files, list-models, offline, verbose, `@file` args, and unknown long flags for extension support.
- `packages/coding-agent/src/modes` contains `interactive`, `print-mode.ts`, and `rpc` paths. This supports interactive TUI-like operation, print/text/JSON workflows, and RPC process integration.

### TUI/Web UI

- `packages/tui/package.json` describes `@earendil-works/pi-tui` as a "Terminal User Interface library with differential rendering for efficient text-based applications".
- `packages/web-ui/package.json` describes `@earendil-works/pi-web-ui` as "Reusable web UI components for AI chat interfaces powered by @earendil-works/pi-ai".
- The coding-agent package copies interactive themes/assets and export-HTML assets during build, indicating a terminal-first UI with exportable session artifacts.

### Agent runtime and run/session state

- `packages/agent/package.json` describes `@earendil-works/pi-agent-core` as a "General-purpose agent with transport abstraction, state management, and attachment support".
- `packages/agent/src/harness/agent-harness.ts` defines `AgentHarness`, a high-level orchestration wrapper around `Agent`. The inspected summary shows it manages prompt execution, turn lifecycle, persistent sessions, steering/follow-up queues, tool selection and hooks, model/thinking changes, skills, prompt templates, compaction, branch navigation/summarization, event subscriptions, abort handling, and idle-state coordination.
- `packages/agent/src/harness/types.ts` defines contracts for skills, prompt templates, execution environment abstraction, session tree/storage/repository APIs, harness runtime state, events/hooks, compaction/tree navigation, and harness options.
- `packages/agent/src/harness/session` contains JSONL and in-memory repo/storage implementations: `jsonl-repo.ts`, `jsonl-storage.ts`, `memory-repo.ts`, `memory-storage.ts`, `repo-utils.ts`, `session.ts`, and `uuid.ts`.
- `packages/coding-agent/src/core` contains large session/runtime/service files including `agent-session.ts`, `agent-session-runtime.ts`, `agent-session-services.ts`, `session-manager.ts`, and `session-cwd.ts`.

### Tool registry and extension/plugin/skill concepts

- Pi has a first-class skill concept. `packages/agent/src/harness/types.ts` defines `Skill` loaded from `SKILL.md` or supplied by an application, with `name`, `description`, `content`, `filePath`, and optional `disableModelInvocation`.
- `packages/agent/src/harness/skills.ts` loads skills recursively from directories, honors ignore files, parses YAML frontmatter, supports source-tagged skills, validates diagnostics, and formats skill invocation prompts.
- Pi has prompt templates: `PromptTemplate` and `AgentHarnessResources` are defined in `packages/agent/src/harness/types.ts`; `packages/agent/src/harness/prompt-templates.ts` exists.
- Pi has extension/package concepts. Evidence: coding-agent CLI args support `extensions`, `noExtensions`, unknown long flags for extension support; root workspaces include extension examples under `packages/coding-agent/examples/extensions/...`; website/package catalog describes extensions, skills, prompt templates, themes, and Pi packages.
- Pi has a tool system at agent/harness level. Evidence: `AgentHarness` keeps a `tools` map and active tool names; `AgentTool` is part of imported runtime types. Coding-agent package description explicitly names read, bash, edit, and write tools.

### Model/provider routing

- `packages/ai/package.json` describes `@earendil-works/pi-ai` as a "Unified LLM API with automatic model discovery and provider configuration" and exports providers including Anthropic, Azure OpenAI Responses, Google, Google Vertex, Mistral, OpenAI Codex Responses, OpenAI Completions, OpenAI Responses, OAuth, and Bedrock.
- `packages/ai/src/types.ts` defines known providers including Amazon Bedrock, Anthropic, Google, Google Vertex, OpenAI, Azure OpenAI Responses, OpenAI Codex, DeepSeek, GitHub Copilot, xAI, Groq, Cerebras, OpenRouter, Vercel AI Gateway, Z.ai, Mistral, MiniMax, Moonshot, HuggingFace, Fireworks, Together, OpenCode, Kimi Coding, Cloudflare, and Xiaomi variants.
- `packages/ai/src/api-registry.ts` has `registerApiProvider`, `getApiProvider`, `getApiProviders`, `unregisterApiProviders`, and `clearApiProviders`, allowing API provider registration and source-id-scoped unregistering.
- `packages/ai/src/env-api-keys.ts` maps provider IDs to environment variables and contains provider-specific credential behavior such as GitHub Copilot token sources and Anthropic OAuth precedence.

### State/memory/context management

- Pi supports persistent session state through harness session repositories and coding-agent session manager files.
- Pi supports context transformation hooks and compaction. Evidence: `agent-harness.ts` imports `compact`, `prepareCompaction`, `collectEntriesForBranchSummary`, and `generateBranchSummary`, and its context-transform hook can rewrite/replace messages before model invocation.
- Pi supports skills and AGENTS.md-style contextual rules. Evidence: README links `AGENTS.md`; `AGENTS.md` has project-specific agent rules; skills are loaded from `SKILL.md`.

### License/forkability

- MIT license permits use, copy, modification, merge, publish, distribution, sublicense, and sale with copyright/license notice preservation.
- Forking is allowed by GitHub metadata.
- Practical contribution friction is high: `CONTRIBUTING.md` says new issues and PRs from new contributors are auto-closed by default; approval is needed for future PR acceptance. That affects upstream contribution but not local fork legality.

## B) Matrix OS ↔ Pi concept mapping

| Matrix OS concept | Current Matrix OS evidence | Pi concept | Fit |
|---|---|---|---|
| Gateway | `conduvera/harness/gateway.py` lines 1-5: declarative only, no launch/socket/MCP/shell mutation | `AgentHarness` orchestrates actual prompt/run lifecycle | Conceptually adjacent but not same layer. Matrix OS Gateway is a policy/descriptor boundary; Pi Harness is an execution harness. |
| HarnessGatewayRegistry | `HarnessGatewayRegistry.default()` returns static descriptors for runners/tools/surfaces/capabilities | Pi has runtime resources, tool maps, provider registry, extensions, skills | Good reference for future backend registry, but direct replacement would collapse descriptor-only boundary into runtime execution. |
| Evidence Backbone | `conduvera/evidence/reporting.py` validates EventEnvelope JSONL streams and builds reports | Pi sessions are JSONL/in-memory session stores, not Matrix OS EventEnvelope streams | Requires explicit adapter/contract if Pi run events are ever consumed. Do not treat Pi session JSONL as Matrix OS evidence. |
| Evidence Adapter Registry | `conduvera/evidence/adapters/registry.py` lists only agent-evidence-plane, safety-guard, failure-loop translation-only adapters | Pi has no Matrix OS adapter in current repo | No current compatibility. A future adapter must be a separate focused PR. This task must not create it. |
| Operator Status | `build_harness_operator_status` only reads evidence and registries; no runner execution | Pi can run agents interactively/print/RPC | Pi could be a future backend observed by status, but current operator status must remain read-only. |
| Matrix UI/TUI preservation | `matrix-ui-code-editor` surface descriptor points to existing Matrix UI widget paths | Pi has its own TUI package and interactive mode | Borrow TUI patterns possible; replacing Matrix UI with Pi TUI would be scope risk. |
| Hermes/OpenCode/local-shell runners | Matrix OS registers them as future descriptors with `runtime_enabled=False` | Pi is itself a coding-agent runtime and has provider support for `opencode`/`opencode-go` model/provider IDs | Pi could be an additional future runner/backend descriptor, not a substitute for Hermes/OpenCode control. |
| Safety Guard / agent-evidence-plane / failure-loop | Matrix OS has translation-only adapters and metadata | Pi has runtime hooks/tools but no specific Matrix OS Safety Guard evidence contract | Requires explicit event boundary; no direct evidence compatibility found. |

## C) Control-center fit analysis

Target chain:

`Client/Operator -> Matrix OS Gateway -> Registry -> Access Check -> Route Selection -> Backend Choice -> Fallback -> Run Lifecycle -> Evidence Emission -> Operator UI`

Fit by stage:

1. Client/Operator: Pi has strong terminal/operator affordances through CLI, interactive mode, print/JSON mode, RPC mode, TUI, and session resume/fork. Matrix OS currently has CLI operator status and preserved UI attach points. Fit: strong as reference, medium as backend.
2. Matrix OS Gateway: Matrix OS Gateway is intentionally declarative and non-executing. Pi AgentHarness is executing runtime orchestration. Fit: weak as direct gateway replacement; good as downstream runtime candidate behind a gateway.
3. Registry: Pi has provider registry and tool/resource registration concepts. Matrix OS has static descriptors. Fit: good reference for backend/provider registry shape, but Matrix OS must keep fail-closed descriptors and policy boundaries.
4. Access Check: No evidence found that Pi provides Matrix OS CCC/AAL-style access checks or Safety Guard enforcement compatible with Matrix OS. Fit: weak unless Matrix OS wraps Pi behind an access-checking route-plan layer.
5. Route Selection: Pi supports provider/model selection and provider registration. Matrix OS lacks backend routing. Fit: strong concept reference for model/provider route selection, but Matrix OS needs runner-level route plans, not just model provider routing.
6. Backend Choice: Pi can be a backend candidate for coding-agent runs. Fit: medium; it is a runtime backend, not a generic control center for Hermes/OpenCode/local-shell without additional adapters.
7. Fallback: Pi has multi-provider model routing and model/provider configuration, but no Matrix OS fallback execution contract was verified. Fit: medium as concept, not ready as Matrix OS behavior.
8. Run Lifecycle: Pi AgentHarness explicitly manages prompt execution, phases, queues, abort/idle, sessions, compaction, and events/hooks. Fit: strong as runtime reference.
9. Evidence Emission: Pi has session state and events/hooks, but no Matrix OS EventEnvelope output or registered Matrix OS adapter. Fit: weak until an explicit Pi evidence contract exists.
10. Operator UI: Pi has TUI/web UI components; Matrix OS has preserved Matrix UI/TUI surface descriptors. Fit: good reference, but do not replace Matrix UI in a runtime PR.

Conclusion: Pi fits best as an architecture reference and possible future runtime backend behind Matrix OS Gateway, not as a forked foundation and not as an immediate control-center runtime.

## D) Option decision matrix

| Option | Benefits | Risks | Integration effort | Scope risk | Technical fit | Impact on existing architecture | Test/DoD criteria |
|---|---|---|---|---|---|---|---|
| A) Matrix OS forked Pi | Fast access to mature TS agent runtime, CLI, TUI, provider registry, sessions, extensions, skills | High architectural takeover risk; Python Matrix OS CCC/AAL/Evidence/Gateway would be subordinated to TS runtime; upstream contribution gate friction; likely breaks Matrix UI/TUI preservation | High | Very high | Medium for runtime; low for evidence/governance | Major rewrite/fork governance; risks blind fork prohibited by task | DoD would require fork policy, license notices, parity tests, evidence contract, Matrix UI migration plan, and operator safety gates. Not appropriate now. |
| B) Matrix OS adapts Pi as runtime backend | Reuses Pi run lifecycle, provider routing, sessions, RPC/JSON modes; preserves Matrix OS as control plane if wrapped correctly | Requires backend adapter, process/RPC boundary, evidence mapping, safety/access checks, fallback semantics; no current Matrix OS Pi adapter | Medium-high | High | Medium-high for one coding-agent backend; low for current evidence | Adds new runner/backend surface; must not replace Gateway/Evidence Backbone | DoD: Pi backend descriptor, dry-run route plan, no execution by default, explicit evidence contract, fail-closed tests, no new adapter until separately reviewed. |
| C) Matrix OS borrows Pi concepts only | Low-risk; can adopt route-plan, provider registry, skills/extensions vocabulary, session/fork concepts, TUI patterns without runtime coupling | May defer real execution; requires careful translation into Matrix OS Python contracts | Low-medium | Low | High for architecture shaping | Preserves CCC/AAL/Evidence/Gateway and Matrix UI; improves runtime design | DoD: ADR or interface contract citing Pi paths, Matrix-owned route-plan schema, fail-closed tests, no runtime execution. |
| D) Matrix OS remains separate and builds own runtime | Maximum control and alignment with evidence/safety architecture; avoids external coupling | Slower; risks reinventing runtime/session/provider machinery Pi already solved | Medium-high | Medium | High for Matrix OS guarantees; lower for speed | Preserves architecture fully; runtime remains Matrix-native | DoD: Matrix-native runner orchestrator spec, tests for access checks/fallback/evidence, incremental backend slices. |

## E) Recommended architecture decision

Decision: C — Matrix OS should borrow Pi concepts only for the next slice.

Rationale:

- Matrix OS already has a deliberately non-executing Gateway, evidence adapters, and operator status. Pi is an execution harness; directly forking or embedding it now would violate the existing boundary discipline.
- Pi provides strong evidence for useful runtime concepts: agent harness lifecycle, sessions, JSONL/in-memory state, provider registry, CLI modes including RPC, skills, prompt templates, extensions, TUI/web UI components, and model/provider routing.
- Matrix OS missing pieces are control-plane pieces: route planning, backend selection, fallback policy, access checks, and evidence emission. Those should be specified before choosing or running a backend.
- A future Option B remains viable only after Matrix OS defines a Pi-compatible interface contract and can dry-run route decisions without executing Pi.

## F) Minimal next PR proposal

Recommended next PR: Matrix OS runtime decision ADR + route-plan/dry-run Gateway slice.

Concrete slice:

- Add a short ADR or architecture doc defining the Matrix OS runtime route-plan contract:
  - operator request input;
  - candidate backend descriptor IDs such as `hermes`, `opencode`, `local-shell`, and future `pi-agent-harness` descriptor-only candidate;
  - access-check result;
  - route-selection reason;
  - fallback order;
  - expected evidence event types;
  - explicit `execute: false` dry-run boundary.
- Add a descriptor-only `pi-agent-harness` runner candidate if and only if it is marked `runtime_enabled=False`, `execution_status="future-adapter-contract-only"`, and `external_boundary="standalone; future runtime backend only; not executed by Matrix OS"`.
- Add tests proving dry-run route plans do not launch Pi, Hermes, OpenCode, shell, MCP, or adapters.
- Do not add a Pi evidence adapter in this PR.

## G) Risks / blockers

- Pi's runtime is TypeScript/Node while Matrix OS current contracts are Python; embedding without an RPC/process boundary would create tight coupling.
- Pi session JSONL/state is not Matrix OS EventEnvelope evidence. Treating it as evidence without a conversion contract would violate the Evidence Backbone.
- Pi can execute tools such as bash/edit/write in coding-agent mode; Matrix OS must not expose this until access checks, safety gates, and explicit dry-run/execute boundaries exist.
- Pi has its own TUI/web UI; replacing Matrix UI/TUI would be a large product pivot and is not needed for runtime evaluation.
- Contribution upstream may be operationally difficult because new contributor issues/PRs are auto-closed by policy.
- No direct Pi integration with Matrix OS Safety Guard, agent-evidence-plane, failure-loop, CCC, AAL, or ASPICE was verified.
- ASSUMPTION: The task's "GitHub/pi.dev Agent Harness project" refers to the public `earendil-works/pi` repo linked from pi.dev and titled "Pi Agent Harness Mono Repo" in README. I found no separate `github.com/pi-dev/...` official repo during web search.

## H) Exact DoD and verification criteria

For the next PR to be acceptable:

1. It must be a dry-run/ADR/interface slice, not runtime execution.
2. It must preserve Matrix OS Gateway as a policy/descriptor control plane.
3. It must not launch Pi, Hermes, OpenCode, local shell, MCP, Zed, or any adapter.
4. It must not add a new Evidence Adapter Registry entry unless a separate adapter PR explicitly defines input schema, supported event types, conversion behavior, and fail-closed tests.
5. It must include tests that unknown backend IDs fail closed.
6. It must include tests that `pi-agent-harness`, if added as descriptor, has `runtime_enabled=False` and no execution command.
7. It must include tests that route-plan output names expected evidence event types without emitting evidence.
8. It must document the distinction between Pi Agent Harness and Raspberry Pi hardware.
9. It must cite Pi evidence paths/URLs used for architecture decisions.
10. It must leave Matrix UI/TUI preserved and only identify future attach points.

## Final verdict

STATUS: PR S READY
DECISION: C
RECOMMENDED NEXT PR: Runtime decision ADR plus route-plan/dry-run Gateway slice with optional descriptor-only `pi-agent-harness` candidate marked non-executing.

WHY:

- Pi is a mature TypeScript agent harness with CLI, TUI/web UI packages, provider routing, sessions, skills, extensions, and runtime lifecycle primitives.
- Matrix OS currently owns a descriptor-only Gateway, evidence contracts, translation-only adapters, and read-only operator status; these should remain the control plane.
- Pi's strongest fit is as a concept source and possible future backend, not a forked Matrix OS foundation.
- Pi does not currently emit Matrix OS EventEnvelope evidence or register with Matrix OS Evidence Adapter Registry.
- Pi runtime execution would require explicit access checks, safety gates, backend routing, fallback policy, and evidence mapping first.
- A dry-run route-plan slice answers the immediate Matrix OS gap without violating non-goals.
- MIT license permits future fork/backend experiments, but upstream contribution policy and architectural coupling make a blind fork risky.
- Pi TUI/Web UI can inform Matrix OS UI design without replacing preserved Matrix UI/TUI.
- Option B can be reconsidered after an interface contract and dry-run route plans exist.
- Option A is too large and violates the no-blind-fork intent.

DO NOT DO NEXT:

- Do not fork Pi as Matrix OS foundation.
- Do not connect to Raspberry Pi hardware.
- Do not inspect or use pi-hermes.
- Do not add SSH/deployment assumptions.
- Do not execute Pi, Hermes, OpenCode, shell, MCP, or Zed from Matrix OS.
- Do not add a Pi evidence adapter in the route-plan PR.
- Do not claim Matrix OS controls Hermes/OpenCode/Pi today.
- Do not replace Matrix UI/TUI with Pi TUI.
- Do not broaden Evidence Adapter Registry to accept arbitrary Pi session events.
- Do not add governance or branch-protection changes.
