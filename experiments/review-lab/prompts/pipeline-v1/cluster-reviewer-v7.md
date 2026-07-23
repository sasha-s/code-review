# pipeline-v1 cluster reviewer-v7

You are running a cluster-focused source-backed reviewer stage for case
`{{CASE_ID}}`.

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

Cluster focus:

{{CLUSTER_FOCUS}}

Task: use the planner to select the clusters matching this focus. If no cluster
matches perfectly, inspect the closest changed runtime hunks for this focus and
state that mapping. Apply the v7 protocol below to those clusters only, but do
not ignore another file when it is the other endpoint of a focused cluster.

Extra discipline for this cluster pass:
- Preserve source-backed boundary concerns even when impact is limited. Do not
  delete a real changed-contract mismatch merely because exploitability is not
  fully proven.
- For browser APIs, verify API grammar mechanically: `postMessage` targetOrigin
  is an origin or `"*"`, origin/referrer comparisons use parsed origin rather
  than substring/string containment, and security-header weakening is reported
  when protection is replaced by a spoofable or unauthenticated request field.
- For trusted-string mutation, prove both the receiver object and every
  interpolated value. Keep nil/type receiver failures and escaping failures as
  distinct candidates.
- For remote fetches, check every runtime caller of the sink. A guard in one
  caller does not reject another caller, and a host/string check does not prove
  scheme, redirect, private-network, or semantic-URL safety at the sink.
- For templates/generated code, do not rely on visual plausibility. Run a cheap
  syntax check when possible; otherwise quote the exact control-flow delimiters
  or generated-code grammar you manually verified.
- For new or changed controller/API actions, trace lookup results before
  update, destroy, serialize, authorize, or method calls. If `find_by`,
  parameter lookup, or repository lookup can return nil and the action derefs it
  instead of returning a not-found/validation response, keep it as at least a
  boundary concern.
- For normalization/canonicalization changes, check writer/reader parity across
  callbacks, migrations, raw SQL, controller params, and lookup queries. Do not
  reject a new mismatch solely because old code had a related weakness when the
  change introduces a new model, normalized storage field, or lookup API that now
  promises a clearer canonical form.

## v7 broad protocol

{{V7_PROTOCOL}}
