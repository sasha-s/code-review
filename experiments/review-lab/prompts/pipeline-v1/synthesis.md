# pipeline-v1 synthesis

You are synthesizing the final source-check artifact for case `{{CASE_ID}}`.

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

Task: produce the final review artifact. Use verifier decisions unless the
challenger restored or dropped a candidate with stronger source evidence.

Keep the final output concise enough for a human reviewer, but include the proof
needed to audit each claim. Do not include candidates that are only plausible.
Do not include benchmark or golden language. Preserve source-backed boundary
concerns when the changed code violates a real security, renderability,
trust-boundary, compatibility, nil/type, or user-visible contract, even if the
impact is limited.

Before writing the final output, run two final audits:
- CRUD/normalization audit: ensure missing-record derefs and writer/reader
  normalization mismatches that survived verifier/challenger are represented as
  findings or boundary concerns, not only in rejected notes.
- Compound-failure audit: when the same changed path has nil/type failure and
  escaping/encoding failure, represent both distinctly or explicitly say which
  one source rejected.

Output sections:

1. Patch Inventory And Proof Ledger
   - Changed runtime files and hunk behaviors.
   - Cluster coverage and any explicit deferrals.

2. Findings
   - Concrete source-backed defects introduced by the change.

3. Source-Backed Boundary Concerns
   - Lower-confidence or limited-impact invariant, trust-boundary,
     compatibility, renderability, or user-visible contract concerns.

4. Candidates Rejected By Adversarial Check
   - Include the source fact that rejected each candidate.

5. Stage Failure Modes And Coverage Gaps
   - Where a prior stage dropped evidence, over-accepted a claim, or lacked
     source/graph coverage.

For every finding or boundary concern include:
- title and severity
- changed source ref with line number
- other-end source ref with line number
- exact invariant mismatch
- concrete scenario or limited-impact scenario
- adversarial verdict
- whether tests/types would catch it
- confidence
