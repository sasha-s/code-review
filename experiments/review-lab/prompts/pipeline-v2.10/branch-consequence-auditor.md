# pipeline-v2 branch and consequence auditor

You are auditing candidate branch coverage for case `{{CASE_ID}}`.

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

Task: audit whether prior stages modeled the right branch and consequence for
each source-backed or unresolved candidate. Do not write final review prose.

Focus on generic branch families that frontier models often compress away:

- Parser/schema construction: object shape, computed keys, literal keys,
  wrapper-vs-value returns, validation-time exceptions, and caller expectations.
- Matcher/count invariants: fewer/equal/more repeated elements, ordering,
  placeholder grammar, translated/generated values, and existing tests that
  cover only one cardinality direction.
- Changed-call arguments: overload choice, argument order, default-owner/default
  scope assumptions, variadic expansion, and callee return contracts.
- State/time semantics: missing vs zero vs unchanged rows, caller-provided time
  vs write-time time, no-op writes intended only for side effects, and retry or
  concurrency windows.
- Template/resource syntax: changed delimiters, renderability, language/script,
  classpath/build inclusion, and source-visible spelling that affects external
  calls or generated output.

For each relevant candidate or changed source location:

1. Enumerate sibling branches before judging severity. A source fact for one
   branch does not reject another branch.
2. State the exact branch predicate, immediate source-level outcome, downstream
   consequence, and affected caller/user/state.
3. Run a cheap read-only micro-check when it is available from local source and
   does not require network, package install, or mutating files. Examples:
   `node -e` for pure JS object/schema construction, `python - <<'PY'` for pure
   string/matcher snippets, compiler/parser dry runs that do not write files, or
   bounded source reads of callee signatures and tests.
4. If a micro-check is unsafe, unavailable, or needs dependencies, record the
   exact reason instead of guessing.
5. Add a new candidate id only when the branch/consequence is source-backed and
   materially distinct from prior candidates.

Output exactly one fenced `json` block and no other prose. The JSON must have
this shape:

```json
{
  "case_id": "{{CASE_ID}}",
  "audited_candidates": [
    {
      "id": "K-### or K-new-branch-###",
      "contract_ids": ["C-###"],
      "source_refs": ["file:line"],
      "branch_predicate": "exact branch/input shape",
      "immediate_outcome": "source-level outcome",
      "downstream_consequence": "runtime/user/state/build consequence",
      "affected_caller_user_state": "caller/user/operator/state",
      "disposition": "source_backed | source_rejected | unresolved_gap",
      "micro_check": {
        "status": "ran | not_run",
        "command_or_read": "command/read summary or null",
        "result": "observed result or reason not run"
      },
      "sibling_branches": [
        {
          "branch_predicate": "sibling branch/input shape",
          "downstream_consequence": "distinct consequence",
          "disposition": "source_backed | source_rejected | unresolved_gap",
          "source_fact": "file:line or exact fact"
        }
      ],
      "selector_requirement": "sentence/fact the selector must preserve or reject with source evidence"
    }
  ],
  "wrong_branch_risks": [
    {
      "candidate_id": "K-###",
      "risk": "how a prior stage may have accepted/rejected the wrong branch",
      "required_selector_action": "include, reject, or keep as unresolved gap"
    }
  ]
}
```
