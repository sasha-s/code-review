# pipeline-v2 evidence verifier

You are verifying every carried candidate for case `{{CASE_ID}}`.

Hard isolation rules:
- Do not read evaluator directories, benchmark goldens, judge outputs, packaged
  benchmark result files, the review-lab learning repository, or the internet.
- Do not use named skills or skill workflows.
- Do not read any path under `/Users/sasha/code-review/skills` or
  `/Users/sasha/.agents/skills`.

Start from exactly this review input README:

`{{INPUT_README}}`

Also read these prior pipeline artifacts:

{{PREVIOUS_ARTIFACTS}}

Task: assign a disposition to every candidate id. A candidate may not disappear.

For each candidate answer:
- linked contract ids
- introduced or materially changed by this diff
- reachable runtime/test/migration/deploy path
- changed source ref and other-end source ref
- exact source evidence supporting it
- exact source evidence that would reject it
- consequence matrix:
  - branch predicate or input shape that triggers the behavior
  - immediate source-level outcome at the changed line
  - downstream runtime failure mode or semantic break
  - affected caller, user, operator, or stored state
- final disposition: verified finding, verified boundary concern, rejected, or
  unresolved coverage gap

Policy:
- Findings need concrete source-backed impact.
- Boundary concerns need a real changed invariant mismatch with limited or
  partially proven impact.
- Do not require a runnable test to verify a finding when the source already
  proves the changed path, invariant mismatch, and consequence. Missing tests are
  evidence gaps to mention, not a reason to demote source-proven behavior to
  `unresolved coverage gap`.
- Classify a concurrency candidate as a verified finding or boundary concern
  when source shows a read/check/admission decision separated from the write that
  enforces it, and no transaction, lock, unique constraint, or atomic upsert
  source fact closes the race. Do not demand a stress test when the interleaving
  is visible in source.
- For update/delete/affected-row candidates, keep distinct meanings separate:
  missing-record/no matched row, matched-but-unchanged row, driver-specific row
  count behavior, and misleading sentinel/error mapping are separate
  consequences. If the changed code maps zero affected rows to a domain error,
  verify the missing-record consequence unless source proves the record must
  exist at that point.
- For time-window/current-time candidates, do not reject solely because one
  high-level caller stamps `now`. If the changed store/service/API accepts a
  caller-provided timestamp or compares multiple time sources for the same active
  population, classify the mismatch at least as a boundary concern unless source
  proves all runtime callers canonicalize the same time basis.
- For API/helper methods, interfaces, stores, jobs, and resource verifiers,
  direct callers, tests, admin paths, generated wiring, and external package
  call sites can all be runtime contracts. Do not reject a candidate merely
  because the most common caller is safe if the changed callable remains exposed
  to other source-visible callers with weaker preconditions.
- Rejections need source facts. "Not important", "admin-only", "not fully
  exploited", or "old code was also imperfect" are not enough by themselves.
- If a candidate has multiple dimensions, verify each dimension separately.
  Do not let a broad finding hide a nil/type, escaping, normalization,
  renderability, or CRUD-not-found subfailure.
- Do not accept a broad category match as enough. A candidate that identifies a
  suspicious API call, schema, parser, counter, timestamp, anchor, placeholder,
  or state transition must also state the exact consequence it causes. If the
  source supports two sibling consequences, keep both; if only one is proven,
  reject or gap the other with the source fact.
- If the consequence depends on a branch or input shape, name the predicate.
  Examples of predicate shape include missing vs present fields, zero affected
  rows vs unchanged rows, simplified vs traditional script, generated syntax vs
  validation semantics, missing anchors vs extra anchors, and caller-supplied vs
  canonicalized timestamps.
- If the planner created a broad contract instead of split subcontracts, verify
  the sub-dimensions anyway and keep source-backed ones visible as findings,
  concerns, or explicit gaps.
- For renderability candidates, reject only after source or a syntax/render check
  proves the changed grammar is valid.
- For resource/locale candidates, reject only after checking the expected
  locale/script, neighboring/base resource value, loader key, placeholders,
  translated HTML/anchor grammar, and verifier/parser behavior that consumes the
  resource value.
- For browser/framework/external API candidates, verify producer argument grammar
  separately from receiver-side validation.
- For security-header/platform-protection candidates, reject only if source
  proves equivalent protection for the same browser/client threat model.
- If an exact changed template/control-flow construct is suspicious and no syntax
  check proves it valid, keep it as a verified boundary concern or unresolved
  renderability candidate with the exact construct quoted. Do not reduce it to a
  generic coverage gap.
