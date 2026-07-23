# Source Contract Audit Prompt

Use this prompt template for review-lab child Codex runs. It is intentionally
not installed as a global skill.

This is the legacy wording used by earlier runs. For new isolation-sensitive
mini-passes, prefer `source-check.md`; this template uses words that can trigger
host-global review skills in child Codex.

```text
You are doing a blind source audit of a pull request using only this workspace
and the referenced repository checkout. Do not read evaluator or benchmark-golden
files. Do not use the internet.

Start from README.md, inputs/snapshot.json, inputs/patch.diff,
inputs/analysis/reviewer-context.md, inputs/analysis/source-excerpts.md, and any
referenced source files needed from the repo.

Task: identify source-backed defects introduced by this PR. Focus on changed
runtime contracts rather than style. For each changed scope, trace:
- caller intent from code, comments, method names, tests, and surrounding flow
- callee implementation and accepted input/output shapes
- old-vs-new behavior at the caller boundary
- missing/null/empty state and persisted legacy data
- identifier routing and ownership binding
- write/update/delete side effects, including empty update payloads and
  timestamp/cache freshness semantics
- script/CLI portability when changed scripts are part of the runtime workflow

Important review rules:
- Tests are evidence, not proof. If a changed test covers one state/count/order,
  still check adjacent missing, extra, duplicate, and empty variants.
- If changed code calls a write primarily to produce a side effect, do not drop
  the issue just because a downstream reader is elsewhere. Report it when the
  changed code itself establishes the intended side effect and the callee/payload
  makes that side effect a no-op or platform-dependent.
- If the benchmark-looking issue is contradicted by source, reject it explicitly
  under Non-findings instead of forcing a finding.
- Prefer behavioral defects with concrete user impact over low-value style nits.

For each finding include:
- title and severity
- exact source refs with line numbers
- caller/callee contract trace
- concrete failing scenario
- whether tests/types would catch it

Output sections:
1. Findings
2. Non-findings checked
3. Residual risks / source gaps
```
