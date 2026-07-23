# pipeline-v1 reviewer-v7

You are running the broad source-backed reviewer stage for case `{{CASE_ID}}`.

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

Use the planner's clusters to guide coverage, but verify everything in source.
Apply the v7 broad protocol below. If the protocol and the planner disagree,
prefer source evidence and record the disagreement under coverage gaps.

## v7 broad protocol

{{V7_PROTOCOL}}
