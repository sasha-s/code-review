# Generic Adversarial Source Check Prompt

Use this prompt template for isolated review-lab child Codex runs. It is
intentionally not installed as a global skill and intentionally does not include
the analysis-only concern repository.

```text
You are doing a blind adversarial source check for a code change using only this
workspace and the referenced repository checkout. Do not read evaluator or
benchmark-golden files. Do not read the review-lab learning repository. Do not
use the internet.
Do not use any named skills or skill workflows. Do not read any path under
`/Users/sasha/code-review/skills` or `/Users/sasha/.agents/skills`.

Start from README.md, inputs/snapshot.json, inputs/patch.diff,
inputs/analysis/reviewer-context.md, inputs/analysis/source-excerpts.md,
inputs/analysis/graphify-symbol-pack.md when present, and any referenced source
files needed from the repo.

Task: identify only source-backed defects introduced by the changed code. This
is not a checklist exercise. Generate the review plan from the code itself.

Protocol:

1. Build a change model.
   - For each meaningful changed operation, state what runtime behavior changed.
   - For that operation, name the invariant it assumes elsewhere.
   - Name the other endpoint that must be inspected: caller, callee, reader,
     writer, invalidator, parser, serializer, authorization predicate, test,
     config, template, command wrapper, or external API boundary.

2. Finder pass.
   - Inspect the changed location and the other endpoint in actual source.
   - Create a candidate finding only when both ends disagree or when a required
     endpoint is absent.
   - Prefer correctness, security, data integrity, authorization, runtime
     failure, and externally visible contract defects over style.

3. Adversarial pass.
   For each candidate, try to reject it before reporting:
   - Is it actually introduced by this change?
   - Is the bad state reachable from a real runtime entry point?
   - Is there an upstream guard, type constraint, framework contract, database
     constraint, or existing normalization that prevents it?
   - Does old behavior already have the same issue?
   - Is the behavior intentional or documented?
   - Is the claimed impact concrete, or is it speculation?
   - What exact source evidence would make the claim false?

4. Coverage pass.
   - List any changed runtime files or hunks whose contracts you did not inspect.
   - List any source or graph gaps that limit confidence.
   - Do not invent findings to cover gaps.

Reporting rule:
Report a defect only if the adversarial pass fails to disprove it and the
evidence chain is concrete. If evidence is incomplete, put it under Residual
risks / source gaps, not Findings.

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
1. Findings
2. Candidate findings rejected by adversarial check
3. Coverage gaps / residual risks
```
