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

Output first a `Candidate Disposition Table` with one row per candidate id and
these exact columns:

`Candidate | Contracts | Disposition | Severity | Include In Final? | Changed Ref | Other-End Ref | Consequence`

Rules for the table:
- `Disposition` must be one of `verified finding`, `verified boundary concern`,
  `rejected`, or `unresolved coverage gap`.
- `Include In Final?` must be `yes` for every verified finding or verified
  boundary concern unless the same row gives an exact source fact that rejects
  it.
- `Consequence` must state the user/runtime/security/test consequence, not just
  the code smell.
- Do not merge candidate ids in this table. Related candidates can point to the
  same contracts, but each id keeps its own consequence.

For each candidate answer:
- linked contract ids
- introduced or materially changed by this diff
- reachable runtime/test/migration/deploy path
- changed source ref and other-end source ref
- exact source evidence supporting it
- exact source evidence that would reject it
- final disposition: verified finding, verified boundary concern, rejected, or
  unresolved coverage gap

Policy:
- Findings need concrete source-backed impact.
- Boundary concerns need a real changed invariant mismatch with limited or
  partially proven impact.
- Rejections need source facts. "Not important", "admin-only", "not fully
  exploited", or "old code was also imperfect" are not enough by themselves.
- If a candidate has multiple dimensions, verify each dimension separately.
  Do not let a broad finding hide a nil/type, escaping, normalization,
  renderability, or CRUD-not-found subfailure.
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
