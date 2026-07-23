# pipeline-v2 hole finder

You are finding holes and dropped evidence for case `{{CASE_ID}}`.

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

Task: compare planner contracts, reviewer updates, and candidate ids.

Output sections:

1. Contract Coverage Audit
   - For every `C-###`, mark covered, partially covered, or uncovered.
   - Name missing proof dimensions.

2. Candidate Continuity Audit
   - For every `K-###` or `K-new-###`, state whether it is carried forward,
     rejected with source fact, or dropped without enough explanation.

3. Required Follow-Up Checks
   - Generate follow-up tasks from uncovered contracts and dropped candidates.
   - Keep them generic and source-derived.
   - Pay special attention to broad cards that cover more than one semantic
     operation. If a broad card mixes producer/consumer API grammar,
     nil/escaping, sink/caller, or renderability/runtime behavior, request a
     split or carry the missing sub-dimension forward explicitly.

4. High-Risk Holes
   - Prioritize holes where the changed code crosses a process/browser/network/
     persistence/auth/render/test boundary, or where the same changed expression
     has more than one failure dimension.
