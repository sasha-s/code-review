# pipeline-v2 synthesis

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

Task: write the final review from the verified ledger and transition challenge.
Do not include benchmark or golden language.

Before writing final findings, perform a final ledger audit:
- Every planner `C-###` should be covered, rejected as non-runtime/supporting, or
  named as a coverage gap.
- Every candidate id should be included, rejected with source fact, or named as
  unresolved.
- Compound candidates should keep distinct nil/type, escaping, normalization,
  renderability, CRUD-not-found, auth/routing, and trust-boundary subfailures
  when source supports them.
- Broad contract audit: if one contract covers multiple semantic operations,
  make sure producer API grammar, receiver validation, sink caller guards,
  renderability, receiver nil/type, and interpolation escaping each have a final
  disposition when they appear in the changed code.
- Security/platform audit: when a change weakens browser/server platform
  protection or replaces it with an application-level guard, include it as a
  finding/concern unless source proves equivalent protection for the same threat
  model.
- Renderability audit: exact suspicious changed template/generator syntax must
  be a finding or boundary concern unless a source-backed syntax/render check
  proves it valid.
- Resource/locale audit: changed resource values that are displayed, parsed,
  loaded, or matched need final disposition for expected language/script,
  neighboring/base-locale consistency, message key spelling,
  placeholder/interpolation grammar, and translated HTML/anchor matcher grammar.
- Verified-candidate carry audit: every candidate marked verified finding or
  verified boundary concern by the verifier/challenger must appear in Findings
  or Source-Backed Boundary Concerns, unless it is explicitly rejected here with
  a source fact. Do not omit a verified candidate only because a higher-priority
  finding exists.
- Calibration audit: if source proves reachability, changed invariant mismatch,
  and concrete consequence, keep it as a finding or boundary concern even if no
  runtime test/build was run. Put missing execution proof in `tests/types`; do
  not demote source-proven behavior to a coverage gap solely for lack of a test.

Output sections:

1. Patch Inventory And Contract Coverage
   - Changed runtime clusters and contract ids covered.

2. Findings
   - Concrete source-backed defects.

3. Source-Backed Boundary Concerns
   - Real changed contract mismatches with limited or partially proven impact.

4. Candidates Rejected By Adversarial Check
   - Include the rejecting source fact.

5. Dropped Evidence / Coverage Gaps
   - Stage transition failures, unresolved contract dimensions, and test/runtime
     checks not run.

For every finding or boundary concern include title/severity, candidate id,
contract ids, changed source ref, other-end source ref, invariant mismatch,
scenario, adversarial verdict, tests/types, and confidence.
