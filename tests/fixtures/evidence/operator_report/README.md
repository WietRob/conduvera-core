# Evidence Operator Report Golden Fixtures

This directory is a regression contract for Matrix OS operator-facing evidence reports.

Files:

- `product_coherence.events.jsonl` — deterministic Matrix OS `EventEnvelope` stream.
- `product_coherence.expected.txt` — expected text report output.
- `product_coherence.expected.md` — expected Markdown report output.
- `product_coherence.expected.json` — expected JSON report output.

The fixture locks the product-coherence operator answers for:

- approved Change Request `CR-MXOS-001`,
- accountable change evidence from `hermes-agent` run `run-900`,
- requirement `SW-REQ-AUTH-007`,
- ASPICE traceability gap `verification_case`,
- Safety Guard blocked action `rm production.db`,
- failure observation and proposed rule `rule_product_coherence_regression`,
- proposed rule status `enforced=false` / `policy_action=none`,
- adapter counts for native, agent-evidence-plane, Safety Guard, and failure-loop evidence.

Determinism rules:

- event IDs, timestamps, ordering, CR IDs, run IDs, requirement IDs, and adapter names are stable;
- golden outputs must not include temporary paths or host-specific absolute paths;
- intentional report output changes must update the corresponding expected files in the same change.

Boundaries:

- this is not production audit retention;
- this is not a dashboard or UI runtime;
- this does not execute external runtimes;
- this does not add a new adapter;
- this does not enforce proposed rules.
