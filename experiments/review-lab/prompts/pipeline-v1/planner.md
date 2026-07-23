# pipeline-v1 planner

You are planning a blind source check for case `{{CASE_ID}}` using only this
repository checkout and the review-lab inputs named below.

Hard isolation rules:
- Do not read evaluator directories, benchmark goldens, judge outputs, packaged
  benchmark result files, the review-lab learning repository, or the internet.
- Do not use named skills or skill workflows.
- Do not read any path under `/Users/sasha/code-review/skills` or
  `/Users/sasha/.agents/skills`.

Start from exactly this file:

`{{INPUT_README}}`

Read the patch, context pack, source excerpts, and symbol pack listed there when
present. Treat `.review-lab-inputs/` as harness data, not product source.

Task: produce a plan for source-backed defect discovery. Do not write final
findings yet unless a planning blocker itself needs to be recorded.

Output sections:

1. Changed Runtime Clusters
   - Cluster id
   - Changed files and hunk behaviors
   - Primary runtime entry points to inspect
   - Other endpoints that must agree with the changed code
   - Triggered focused checks: remote fetch, trusted string/HTML, browser frame
     security, template/renderability, CSS/legacy layout, lazy state/concurrency,
     external command grammar, persistence/normalization, routing/auth, tests

2. Evidence Plan
   - For each cluster, name the exact source files/functions/templates/tests to
     inspect next and why.
   - Include graph/symbol-pack gaps and raw-source fallback needs.

3. False-Positive Traps
   - Source facts that would reject tempting but unsupported claims.
   - Old behavior that may already have the same issue.

4. Coverage Ledger
   - Every changed runtime hunk should be assigned to a cluster.
   - Non-runtime hunks should be marked as style, locale, test, migration-only,
     dependency-only, or documentation.
