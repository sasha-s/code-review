# Generic Adversarial Source Check Prompt v3

Use this prompt template for isolated review-lab child Codex runs. It is
intentionally not installed as a global skill and intentionally does not include
the analysis-only concern repository.

This v3 keeps the v2 coverage ledger and adds a three-tier output policy:
confirmed findings, source-backed boundary concerns, and rejected candidates.
The goal is to avoid accepting weak claims while also not burying real
lower-impact contract violations as "rejected".

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

Task: identify source-backed defects introduced by the changed code. This is
not a checklist exercise. Generate the review plan from the changed code itself.

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
   - Create a candidate only when both ends disagree or when a required endpoint
     is absent.
   - Prefer correctness, security, data integrity, authorization, runtime
     failure, and externally visible contract defects over style.

4. Adversarial pass.
   For each candidate, try to reject it:
   - Is it actually introduced by this change?
   - Is the bad state reachable from a real runtime entry point?
   - Is there an upstream guard, type constraint, framework contract, database
     constraint, or existing normalization that prevents it?
   - Does old behavior already have the same issue?
   - Is the behavior intentional or documented?
   - Is the claimed impact concrete, limited, or speculative?
   - What exact source evidence would make the claim false?

5. Triage policy.
   - Put a candidate in Findings only when it has concrete source-backed impact.
   - Put a candidate in Source-backed boundary concerns when the changed code
     breaks or weakens a real invariant, trust boundary, render contract, or
     compatibility contract, but impact is limited or not fully proven.
   - Put a candidate in Rejected only when it is contradicted by source,
     unreachable, pre-existing, intended, or unproven.
   - Do not promote boundary concerns into high-severity findings. Keep severity
     proportional.

6. Final coverage pass.
   - Include the coverage ledger in the final output.
   - List any changed runtime files or hunks whose contracts you did not inspect.
   - List any source or graph gaps that limit confidence.
   - Do not invent findings to cover gaps.

For each Finding or Source-backed boundary concern include:
- title and severity
- changed source ref with line number
- other-end source ref with line number
- exact invariant mismatch
- concrete scenario or limited-impact scenario
- adversarial verdict: why it was not rejected
- whether tests/types would catch it
- confidence

Output sections:
1. Coverage ledger
2. Findings
3. Source-backed boundary concerns
4. Candidates rejected by adversarial check
5. Coverage gaps / residual risks
```
