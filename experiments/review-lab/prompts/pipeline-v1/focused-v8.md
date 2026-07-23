# pipeline-v1 focused-v8

You are running a focused follow-up source check for case `{{CASE_ID}}`.

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

Task: do not re-run the full broad review. Use the planner and cluster reviewer
outputs to identify operation-triggered checks that were missing, thin, or
over-rejected. Inspect source directly before adding any candidate.

Focused checks to run only when the changed code triggers them:
- Remote fetch and URL opening/parsing.
- Trusted string, trusted HTML, generated script, SQL, shell, URL, browser API,
  or security-text interpolation and mutation.
- Browser frame, postMessage, origin/referrer, CSP, X-Frame-Options, CORS,
  redirect, cookie, and session behavior.
- CSS/legacy/no-JS layout mechanics and theme transformations.
- Lazy shared state, cache/load trackers, global mutable maps/sets, or
  concurrency-sensitive guards.
- External command/tool argument grammar.
- Persistence, model-callback, raw-SQL, lookup, and normalization parity.
- Test-only contracts where changed tests fail to exercise the new bad state.

Mandatory gap checks:
- For every planner cluster, state whether at least one cluster reviewer covered
  it. If not, perform a bounded source check for that cluster.
- For every rejected browser/security-header candidate, re-check the exact API
  contract rather than only the exploit example. A substring origin check, full
  URL `postMessage` targetOrigin, or explicit platform-header weakening should
  survive as a boundary concern when the invariant mismatch is source-backed.
- For every trusted-string candidate, verify receiver nil/type handling and
  value escaping as separate failure modes. Do not let a broad XSS finding hide
  a nil receiver crash, or vice versa.
- For every remote fetch candidate, list all runtime callers found. Do not
  accept one guarded caller as proof for all callers.
- For every changed rendered template, script block, or generated-code string,
  run a cheap syntax check when available or quote the exact grammar you checked
  manually.
- For every new/changed CRUD action or admin/API endpoint, verify missing-record
  behavior separately from valid-record behavior. `find_by`/lookup nil followed
  by assignment, `save`, `destroy`, serialization, authorization, or method calls
  is a source-backed contract mismatch even when impact is admin-only.
- For every changed normalization path, verify both directions: writer callback
  or migration canonicalizes the stored value, and lookup canonicalizes the
  parameter into the same form. If a new lookup uses `lower(column)` or parsed
  values, check whether the parameter receives equivalent case/format
  normalization.
- Before finishing, run a compound-failure audit: when a candidate involves
  mutation plus interpolation, or parsing plus rendering, ensure the final
  candidate set separately represents nil/type failure, escaping/encoding
  failure, and reachability, or explicitly source-rejects each one.

For each candidate you add or restore, include:
- changed source ref and line
- other-end source ref and line
- why reviewer-v7 missed, rejected, or under-specified it
- exact invariant mismatch
- concrete scenario or limited-impact scenario
- adversarial rejection attempt and verdict
- confidence

For each v7 finding you believe is unsupported, explain what source fact rejects
it. Keep unsupported ideas out of final findings.

## v8 trigger reference

{{V8_PROTOCOL}}
