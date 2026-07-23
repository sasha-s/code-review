# Generic Adversarial Source Check Prompt v2

Use this prompt template for isolated review-lab child Codex runs. It is
intentionally not installed as a global skill and intentionally does not include
the analysis-only concern repository.

This v2 keeps the no-checklist adversarial structure from
`generic-adversarial.md`, but adds a coverage ledger so the model cannot spend
the entire run on one attractive issue while ignoring other changed clusters.

```text
You are doing a blind adversarial source check for a code change using only this
workspace and the referenced repository checkout. Do not read evaluator or
benchmark-golden files. Do not read the review-lab learning repository. Do not
use the internet.
Do not use any named skills or skill workflows. Do not read any path under
`/Users/sasha/code-review/skills` or `/Users/sasha/.agents/skills`.

Start from .review-lab-inputs/generic-adversarial/README.md when present,
otherwise start from README.md. Then read the listed inputs: snapshot.json,
patch.diff, reviewer-context.md, source-excerpts.md when present, and
graphify-symbol-pack.md when present.

Task: identify only source-backed defects introduced by the changed code. This
is not a checklist exercise. Generate the review plan from the changed code
itself.

Protocol:

1. Coverage ledger first.
   - List changed runtime files and changed hunks from the patch.
   - Group them into clusters by runtime behavior, not directory alone.
   - For every cluster, choose at least one changed operation to inspect unless
     the cluster is clearly non-runtime or redundant with another inspected
     cluster.
   - Do not stop after finding one strong defect. Continue until each runtime
     cluster has an inspected obligation or a stated reason for deferral.

2. Build a change model for each inspected operation.
   - State what runtime behavior changed.
   - State the invariant the changed operation assumes elsewhere.
   - Name the other endpoint that must be inspected: caller, callee, reader,
     writer, invalidator, parser, serializer, authorization predicate, test,
     config, template, command wrapper, or external API boundary.
   - Choose boundary probes from the operation shape, not from a remembered bug
     list:
     * conditionals and context reads: absent, null, unauthenticated, legacy, and
       first-use states
     * collection/index/order/count/slice arithmetic: negative, zero, empty,
       duplicate, boundary, and non-numeric key states
     * parser/serializer/template/network/shell/SQL/file/HTML boundaries:
       sink-specific validation, escaping, renderability, and trust transfer
     * state writes and caches: writer/reader/delete/invalidate key parity and
       concurrency around check-then-act updates
     * auth/session/permission flows: user identity, credential type, and route
       phase before and after the change

3. Finder pass.
   - Inspect the changed location and the other endpoint in actual source.
   - Create a candidate finding only when both ends disagree or when a required
     endpoint is absent.
   - Prefer correctness, security, data integrity, authorization, runtime
     failure, and externally visible contract defects over style.
   - If a candidate is real but lower impact, keep it with lower severity rather
     than dropping it solely because impact is not catastrophic.

4. Adversarial pass.
   For each candidate, try to reject it before reporting:
   - Is it actually introduced by this change?
   - Is the bad state reachable from a real runtime entry point?
   - Is there an upstream guard, type constraint, framework contract, database
     constraint, or existing normalization that prevents it?
   - Does old behavior already have the same issue?
   - Is the behavior intentional or documented?
   - Is the claimed impact concrete, or is it speculation?
   - What exact source evidence would make the claim false?

5. Final coverage pass.
   - Include the coverage ledger in the final output.
   - List any changed runtime files or hunks whose contracts you did not inspect.
   - List any source or graph gaps that limit confidence.
   - Do not invent findings to cover gaps.

Reporting rule:
Report a defect only if the adversarial pass fails to disprove it and the
evidence chain is concrete. If evidence is incomplete, put it under Coverage
gaps / residual risks, not Findings.

For each defect include:
- title and severity
- changed source ref with line number
- other-end source ref with line number
- exact invariant mismatch
- concrete runtime failure scenario
- adversarial verdict: why the finding survived falsification
- whether tests/types would catch it
- confidence

Output sections:
1. Coverage ledger
2. Findings
3. Candidate findings rejected by adversarial check
4. Coverage gaps / residual risks
```
