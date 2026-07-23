# review-lab

Isolated experiment harness for improving PR review quality without changing the
global `deepreview` skill.

The core rule is blind separation:

- Reviewer inputs contain PR metadata, diff-derived analysis, and hashes.
- Benchmark goldens live only under `evaluator/`.
- Scoring or judging happens only after a review artifact already exists.

## Commands

Prepare a PR-AF benchmark subset without leaking goldens into reviewer inputs:

```bash
python3 experiments/review-lab/review_lab.py prepare-pr-af-subset --limit 5
```

Fetch and cache a live PR snapshot. For merged PRs the snapshot directory uses
`review_target_sha` (normally `mergeCommit.oid`) rather than only GitHub's
`headRefOid`, because benchmark goldens must be aligned to the reviewed tree:

```bash
python3 experiments/review-lab/review_lab.py fetch-pr \
  https://github.com/keycloak/keycloak/pull/41249
```

Fetch and cache a GitHub commit snapshot. This is used for PR-AF rows whose
source target is a commit URL rather than a pull request:

```bash
python3 experiments/review-lab/review_lab.py fetch-commit \
  https://github.com/discourse/discourse/commit/267d8be1f556ed59639ced396c885bb44586da19
```

Analyze a cached diff for changed files, graph health, and generic obligation
seeds:

```bash
python3 experiments/review-lab/review_lab.py analyze-diff \
  --diff ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH/patch.diff \
  --out ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH
```

Build the reviewer-facing context pack from a cached snapshot:

```bash
python3 experiments/review-lab/review_lab.py make-context-pack \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH
```

Build exact target-source excerpts around changed hunks. This is useful when
compact `lean-ctx` output may rewrite exact source tokens:

```bash
python3 experiments/review-lab/review_lab.py make-source-excerpt-pack \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH \
  --repo ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-N-TARGET
```

Create or reuse a detached PR target worktree. This cache survives later runs
and is keyed by owner, repo, PR number, and `review_target_sha`:

```bash
python3 experiments/review-lab/review_lab.py ensure-worktree \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH \
  --repo ~/.cache/code-review/pr-af-benchmark/repos/OWNER_REPO
```

Create a child Codex workspace inside a cached PR worktree. This copies only
source-check inputs under `.review-lab-inputs/` so child Codex can run with
`--cd` at the repo root and `lean-ctx` can read both source and review inputs
without escaping its project root:

```bash
python3 experiments/review-lab/review_lab.py make-child-workspace \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH \
  --repo ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-N-TARGET
```

By default this command verifies that `--repo` is checked out at the
snapshot's `review_target_sha`. Passing the moving cached repo clone instead of
a detached PR worktree fails fast; use `--allow-head-mismatch` only for an
explicit diagnostic run.

Create or reuse an auth-only `CODEX_HOME` for child Codex. This symlinks auth
metadata from the real Codex home, but intentionally omits global config,
AGENTS, rules, sessions, and skills:

```bash
python3 experiments/review-lab/review_lab.py ensure-child-codex-home
```

Use the printed path as `CODEX_HOME=...` when launching child Codex. For
benchmark child runs, pass `--disable plugins` as well; `--ignore-user-config`
alone did not prevent host-global review skills from being auto-read in one
probe run, and the event-log scanner caught that contamination.

Scan a saved child Codex `--json` event stream for isolation leaks such as
host-global skill reads or evaluator/golden paths:

```bash
python3 experiments/review-lab/review_lab.py scan-codex-event-log \
  --event-log ~/.cache/code-review/review-lab/cases/CASE/child.events.jsonl \
  --out ~/.cache/code-review/review-lab/cases/CASE/child-event-scan.json
```

Run the isolated multi-stage pipeline experiment. This wraps the blind inputs in
a PR-AF-like loop: planner, fixed cluster-oriented v7 reviewers, focused v8
subpass, evidence verifier, adversarial challenger, and synthesis. It is not a
global skill and writes only under `experiments/review-lab/` plus the durable
review-lab cache:

```bash
python3 experiments/review-lab/pipeline_v1.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

For the ledger-oriented pipeline, use `pipeline_v2.py`. It changes the unit of
work from prose findings to persistent contract cards and candidate ids before
synthesis. The wrapper is versioned independently of the global skill; check the
experiment notes before treating the latest wrapper version as the best baseline:

```bash
python3 experiments/review-lab/pipeline_v2.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_2.py` to reproduce the stronger current v2.2 baseline after
newer variants are added:

```bash
python3 experiments/review-lab/pipeline_v2_2.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_4.py` for the v2.4 experiment, which keeps the v2.2 eight-stage
shape but folds generic resource/locale rules into the existing stages:

```bash
python3 experiments/review-lab/pipeline_v2_4.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_5.py` for the v2.5 structured-carry experiment:

```bash
python3 experiments/review-lab/pipeline_v2_5.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_6.py` for the v2.6 verifier-calibration experiment:

```bash
python3 experiments/review-lab/pipeline_v2_6.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_7.py` for the v2.7 consequence-decomposition experiment:

```bash
python3 experiments/review-lab/pipeline_v2_7.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_8.py` for the v2.8 sentinel/time/matcher experiment:

```bash
python3 experiments/review-lab/pipeline_v2_8.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_9.py` for the v2.9 structured candidate-selection experiment:

```bash
python3 experiments/review-lab/pipeline_v2_9.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

Use `pipeline_v2_10.py` for the v2.10 branch/consequence-auditor experiment:

```bash
python3 experiments/review-lab/pipeline_v2_10.py \
  --case-id CASE \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-OR-COMMIT-TARGET \
  --input-name generic-adversarial
```

The pipeline cache key includes the pipeline version, model, worktree HEAD,
blind input-file hashes, stage prompt hash, and previous-stage output hashes.
Unchanged reruns reuse stage artifacts; changing prompts, input packs, model, or
upstream stage output invalidates downstream stages. Every child stage runs with
`--ignore-user-config`, `--ignore-rules`, `--ephemeral`, `--disable plugins`,
`--sandbox read-only`, and then runs the event-log scanner.

Audit pipeline ledger continuity after a multi-stage run:

```bash
python3 experiments/review-lab/ledger_check.py \
  --pipeline-dir ~/.cache/code-review/review-lab/cases/CASE/pipeline-v2 \
  --out-json ~/.cache/code-review/review-lab/cases/CASE/pipeline-v2/ledger-check.json \
  --out-markdown ~/.cache/code-review/review-lab/cases/CASE/pipeline-v2/ledger-check.md
```

The checker is diagnostic only: it verifies that contract and candidate ids are
carried from planner/reviewer stages into verifier, challenger, and synthesis.
It does not decide whether a candidate is true. When `manifest.json` exists, the
checker reads the current manifest stage list so stale artifacts from older
pipeline versions in the same directory do not get mixed into the audit.

Compare a pipeline variant against other judge runs for the same cases:

```bash
python3 experiments/review-lab/review_lab.py variant-deltas \
  --summary ~/.cache/code-review/review-lab/summary.json \
  --judge-file pipeline-v2.2-codex-judge.md \
  --out ~/.cache/code-review/review-lab/pipeline-v2.2-deltas.json
```

This highlights single-run tradeoffs: hits unique to the variant, hits found by
other runs that the variant missed, and cases where one issue class was recovered
while another was dropped.

Prompt templates live under `experiments/review-lab/prompts/`. They are
experimental inputs for child Codex runs and are not installed into, or sourced
from, the global `deepreview` skill. Use `prompts/generic-adversarial-v8.md`
for the current generic no-checklist adversarial experiment with v7-style proofs
plus operation-triggered remote-fetch, CSS/legacy-browser, lazy-state, and
external-command argument checks, `prompts/generic-adversarial-v7.md` for the
v5-style sink/renderability prompt with focused trusted-HTML and browser
frame/security proofs, `prompts/generic-adversarial-v6.md` for the heavier
caller-evidenced sink variant, `prompts/generic-adversarial-v5.md` for mandatory
sink and renderability proofs, `prompts/generic-adversarial-v4.md` for the
hunk-level micro-contract ledger variant, `prompts/generic-adversarial-v3.md`
for the three-tier boundary-concern variant, `prompts/generic-adversarial-v2.md`
for the coverage-ledger-only variant, `prompts/generic-adversarial.md` for the
first strict falsification pass, and `prompts/source-check.md` for the
lesson-expanded source-check pass; `source-contract-audit.md` is retained as
legacy wording because it can trigger host-global review skills.

Generate a durable report of still-missed goldens with target-alignment status:

```bash
python3 experiments/review-lab/review_lab.py remaining-misses \
  --out ~/.cache/code-review/review-lab/remaining-misses.json
```

By default this also merges curated annotations from
`experiments/review-lab/annotations/remaining-misses.json`, adding an
`Assessment` column such as "Source-backed disagreement", "Manual adjudication
needed", or "Do not tune main reviewer".

Generate a compact outtake from the cached summary and remaining-miss report:

```bash
python3 experiments/review-lab/review_lab.py outtake \
  --out ~/.cache/code-review/review-lab/outtake.md
```

This reports best/union recall, remaining categories, case counts, and whether
any uncategorized prompt-improvement candidates remain.

Generate judged/unjudged coverage for the full PR-AF problem list:

```bash
python3 experiments/review-lab/review_lab.py benchmark-status \
  --out ~/.cache/code-review/review-lab/benchmark-status.md
```

This compares `problems.json` against the cached parseable summary and lists the
unjudged cases with severity mix and source URL.

Attach Graphify hunk-to-node coverage from a cached backend run:

```bash
python3 experiments/review-lab/review_lab.py attach-graphify-coverage \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH \
  --coverage ~/.cache/code-review/pr-af-benchmark/runs/RUN/graphify-coverage.json \
  --case-id owner#number
```

Generate focused `graphify explain` output for symbols mapped from changed
hunks:

```bash
python3 experiments/review-lab/review_lab.py make-graphify-symbol-pack \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH
```

If a cached Graphify `graph.json` exists but no hunk coverage file exists yet,
derive coverage directly from the graph and patch:

```bash
python3 experiments/review-lab/review_lab.py make-graphify-coverage \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH \
  --graph-json ~/.cache/code-review/pr-af-benchmark/graphs/graphify/OWNER_REPO/SHA/code-only-no-cluster/graphify-out/graph.json \
  --case-id owner#number \
  --mode code-only-no-cluster \
  --owner-repo owner/repo \
  --worktree ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-N-TARGET \
  --out ~/.cache/code-review/pr-af-benchmark/runs/owner-number-graphify-coverage.json
```

Build or reuse a clean-source Graphify cache that survives across runs:

```bash
python3 experiments/review-lab/review_lab.py ensure-graphify-cache \
  --owner-repo owner/repo \
  --repo ~/.cache/code-review/pr-af-benchmark/repos/OWNER_REPO \
  --sha REVIEW_TARGET_SHA \
  --mode code-only-cluster-clean
```

Audit an existing review artifact against the context pack and, optionally,
evaluator-only goldens:

```bash
python3 experiments/review-lab/review_lab.py audit-review \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/HEAD-PATCH \
  --review ~/reviews/REPO/PR-N/HEAD.md \
  --goldens ~/.cache/code-review/review-lab/cases/CASE/evaluator/pr-af-goldens.json \
  --out ~/.cache/code-review/review-lab/cases/CASE/evaluator/audit.json
```

After a blind review artifact exists, build an evaluator-only judge payload:

```bash
python3 experiments/review-lab/review_lab.py make-eval-payload \
  --review ~/reviews/REPO/PR-N/HEAD.md \
  --goldens ~/.cache/code-review/review-lab/cases/CASE/evaluator/pr-af-goldens.json \
  --out ~/.cache/code-review/review-lab/cases/CASE/evaluator/judge-input.json
```

Summarize all parseable judge outputs and choose the best recall per case:

```bash
python3 experiments/review-lab/review_lab.py summarize-results \
  --out ~/.cache/code-review/review-lab/summary.json
```

Before trusting a benchmark score, run an evaluator-only target alignment check.
This detects stale or contradicted goldens without exposing them to the reviewer:

```bash
python3 experiments/review-lab/review_lab.py target-alignment \
  --snapshot-dir ~/.cache/code-review/review-lab/snapshots/OWNER_REPO/PR-N/TARGET-PATCH \
  --repo ~/.cache/code-review/pr-af-benchmark/worktrees/OWNER_REPO/PR-N-TARGET \
  --goldens ~/.cache/code-review/review-lab/cases/CASE/evaluator/pr-af-goldens.json \
  --out ~/.cache/code-review/review-lab/cases/CASE/evaluator/target-alignment.json
```

## Cache Layout

The default cache root is:

```text
~/.cache/code-review/review-lab
```

Important files:

```text
cases/<case-id>/review-input.json
cases/<case-id>/evaluator/pr-af-goldens.json
cases/<case-id>/evaluator/judge-input.json
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/snapshot.json
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/patch.diff
snapshots/<owner_repo>/commit-<sha>/<target>-<patch>/snapshot.json
snapshots/<owner_repo>/commit-<sha>/<target>-<patch>/patch.diff
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/analysis/diff-summary.json
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/analysis/graph-health.json
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/analysis/graphify-coverage.json
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/analysis/graphify-symbol-pack.md
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/analysis/obligation-seeds.json
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/analysis/reviewer-context.md
snapshots/<owner_repo>/PR-<n>/<target>-<patch>/analysis/source-excerpts.md
summary.json
remaining-misses.json
outtake.md
benchmark-status.md
cases/<case-id>/<run>.events.jsonl
cases/<case-id>/<run>-event-scan.json
cases/<case-id>/pipeline-v1/<stage>.md
cases/<case-id>/pipeline-v1/<stage>.manifest.json
cases/<case-id>/pipeline-v1/<stage>.events.jsonl
cases/<case-id>/pipeline-v1/<stage>-event-scan.json
cases/<case-id>/pipeline-v2/<stage>.md
cases/<case-id>/pipeline-v2/<stage>.manifest.json
cases/<case-id>/pipeline-v2/<stage>.events.jsonl
cases/<case-id>/pipeline-v2/<stage>-event-scan.json
~/.cache/code-review/pr-af-benchmark/graphs/graphify/<owner_repo>/<sha>/<mode>/metadata.json
~/.cache/code-review/pr-af-benchmark/graphs/graphify/<owner_repo>/<sha>/<mode>/graphify-out/graph.json
~/.cache/code-review/pr-af-benchmark/clean-sources/<owner_repo>/<sha>/
~/.cache/code-review/pr-af-benchmark/worktrees/<owner_repo>/PR-<n>-<target>/
~/.cache/code-review/pr-af-benchmark/worktrees/<owner_repo>/commit-<sha>-<target>/
~/.cache/code-review/review-lab/codex-home-auth-only/
<cached-pr-worktree>/.review-lab-inputs/PR-<n>-<target>-<patch>/inputs/patch.diff
<cached-pr-worktree>/.review-lab-inputs/PR-<n>-<target>-<patch>/inputs/analysis/reviewer-context.md
<cached-pr-worktree>/.review-lab-inputs/PR-<n>-<target>-<patch>/inputs/analysis/source-excerpts.md
<cached-pr-worktree>/.review-lab-inputs/PR-<n>-<target>-<patch>/inputs/analysis/graphify-symbol-pack.md
<cached-pr-worktree>/.review-lab-inputs/pipeline-v1/<stage>.md
<cached-pr-worktree>/.review-lab-inputs/pipeline-v2/<stage>.md
<cached-pr-worktree>/LEAN-CTX.md
<cached-pr-worktree>/skills/karpathy-guidelines/SKILL.md
```

`graph-health.json` is a failure detector. If a graph backend reports no
symbols, flows, or impacted files for a non-empty runtime diff, review-lab marks
the graph output as `failed-empty` instead of treating it as useful context.

Graphify caches are keyed by owner/repo, review target SHA, mode, backend, and
cache schema version. Existing schema-1 caches are reused across runs; changing
the mode or cache schema forces recomputation.

Current graph-health artifact distribution across the subset is 13 `ok`, 11
`partial`, and 19 `unavailable`. `unavailable` means no graph backend has been
attached for that snapshot, not that a backend returned an empty graph. A true
empty graph should surface as `failed-empty`.

`obligation-seeds.json` is not a list of findings. It is a generic checklist of
changed-code contracts that reviewers or subagents should verify by reading the
other end of each contract.

`make-child-workspace` intentionally excludes evaluator goldens and packaged
benchmark results. Use it for child review prompts to avoid `lean-ctx` root
escape failures from detached worktrees. It also backfills
`inputs/analysis/reviewer-context.md` from the snapshot analysis or the legacy
snapshot-root context file, so a child run does not silently lose the main
reviewer context because the previous command used a non-default `--out`.
For generated benchmark worktrees only, it also materializes local instruction
stubs for `LEAN-CTX.md` and `skills/karpathy-guidelines/SKILL.md`; this avoids
child Codex stalls on host-global includes without touching global skills or
shared source clones.

`audit-review` is deterministic triage, not a semantic judge. It shows where an
existing review text appears not to touch obligation seeds or goldens so the next
review run can be inspected quickly.

`target-alignment` is evaluator-only. A `contradicted-by-target` golden should
not be counted as a review miss until the intended benchmark commit is manually
confirmed.

## Observed Failure Modes

- Run child reviewers from a local `.review-lab-inputs/` workspace inside the
  PR worktree. `--add-dir` alone does not make `lean-ctx` allow reads outside
  the child process project root.
- `make-child-workspace` now refuses repo/worktree HEAD mismatches by default.
  Keycloak #36882 exposed why: a child review launched from the cached repo
  clone saw a drifted source tree and had to treat the patch as authoritative.
- Treat compact `lean-ctx` output as lossy for exact source names and language
  tokens. In Keycloak #36882, compact output rewrote Java `return` to `ret` and
  displayed the `command` path component as `cmd`; use raw patch/source excerpts
  when deciding lifecycle/API-contract findings.
- Generate `analysis/source-excerpts.md` for cases where exact line content
  matters. Sentry #80528 and Grafana #80329 both showed the child reviewer
  correcting course after switching from compact output to bounded raw source
  reads. The excerpt file is still subject to `lean-ctx` compression if read
  through the default shell wrapper, so child prompts should explicitly prefer
  raw bounded reads for exact token decisions.
- Run evaluator judges with `--cd` set to the evaluator directory when possible.
  This lets `lean-ctx` read `judge-input.json` without path-escape failures.
- Materialize local instruction stubs in generated child/evaluator workspaces.
  Sentry #80168 verified that this removes repeated missing `LEAN-CTX.md` and
  Karpathy include failures while preserving the same blind evaluator payloads.
- Prefer an auth-only child `CODEX_HOME` for isolation-sensitive child runs.
  A direct empty `CODEX_HOME` fails authentication with 401s, but a generated
  auth-only home that symlinks `auth.json` and `installation_id` while omitting
  config, AGENTS, rules, sessions, and skills completed neutral smoke runs and
  did not read host-global Karpathy or `deepreview` paths. This is not complete
  isolation: a full Keycloak #36882 source-check launched with that auth-only
  home still loaded host-global `deepreview` and `dev` through the app-provided
  skill registry before reading the benchmark inputs.
- Save child `--json` event streams and run `scan-codex-event-log` when testing
  isolation. The auth-only Keycloak #36882 smoke event log scanned clean with
  `hit_count=0`; the full source-check task remained contaminated by host skill
  reads observed in the live event stream.
- Add explicit no-skill/no-host-skill-path instructions to source-check prompts.
  A Keycloak #36882 auth-only smoke run with those instructions scanned clean
  with `hit_count=0`, and a full CLI process-control source-check with the same
  guard also scanned clean and judged 1/1. Keep scanning full source tasks; the
  earlier auth-only run without the explicit guard still loaded host-global
  `deepreview` and `dev`.
- Local instruction stubs are not complete runtime isolation. Keycloak #33832
  showed that a child prompt phrased as an adversarial PR review could still load
  host-global `deepreview` files through shell reads after MCP path guards
  rejected them. Controlled child runs should use `--ignore-user-config`,
  `--ignore-rules`, and `--ephemeral` plus prompts that avoid triggering global
  skills when the benchmark intent is a scoped mini-pass. Sentry #94376 showed
  the same class of issue in evaluator judges: the judge payload stayed blind,
  but Codex startup still loaded host instruction context before reading it.
  Sentry #5 reproduced the same leak when the prompt said "adversarial follow-up
  PR review": local stubs and ignore flags kept the benchmark payload blind, but
  the child process still read host-global review skills before doing the scoped
  source audit. Sentry #67876 showed the leak is not limited to deepreview:
  even a bounded source-audit prompt read host-global Karpathy guidance before
  the generated local stub. Cal.com #11059 reproduced the leak on the evaluator
  side: the child source audit honored local stubs, but the judge first read
  `/Users/sasha/.agents/skills/karpathy-guidelines/SKILL.md` before the
  evaluator-local stub. Keycloak #37429 reproduced both variants: the child
  source audit read host-global `dev` and Karpathy instructions before local
  stubs, and the judge read host-global Karpathy before the evaluator-local
  stub. Keycloak #36882 reproduced the `deepreview` leak even with
  `--ignore-user-config`, `--ignore-rules`, `--ephemeral`, a local
  `LEAN-CTX.md`, and a local Karpathy stub, because the child prompt still used
  review-triggering language (`pull request`, `source audit`). Future isolated
  mini-passes should avoid global skill trigger words when they are testing a
  narrow source-check capability rather than the full skill. A neutral smoke run
  in the same #36882 worktree opened only the generated local stubs and local
  `.review-lab-inputs/.../README.md`, with no host-global `deepreview` path in
  the JSON event stream.
- A healthy Graphify coverage result does not imply the review will hit all
  behavioral obligations. Grafana #79265 had full hunk coverage, but the first
  pass still missed caller-impact, affected-row, and temporal-contract issues.
- Build Graphify against a clean PR worktree or explicitly ignore
  `.review-lab-inputs/`. The Sentry #95633 Graphify run completed, but it also
  scanned reviewer-input JSON/Markdown copied into the worktree; coverage still
  mapped 5/5 files and 17/17 hunks after path-id disambiguation, but the graph
  cache notes this contamination.
- Prefer Graphify builds from a `git archive` clean source snapshot when child
  workspaces or instruction stubs already exist. Sentry #80168 was built both
  ways: the contaminated worktree graph saw 12,736 code files and review-lab
  JSON in zero-node warnings, while the clean-source graph saw 12,731 code files
  and no review-lab files. The clean clustered graph cached as
  `code-only-cluster-clean` mapped 4/4 changed files and 25/25 hunks, with 102143
  nodes, 281473 links, and 2293 communities.
- Keycloak #33832 verified the reusable clean Graphify cache command on a Java
  repo. The clean clustered cache for merge SHA `b95d12a...` mapped 11/11 changed
  runtime files and 17/17 hunks, with 84007 nodes, 292215 clustered edges, and
  1612 communities.
- Lexical target alignment is a triage signal, not proof. It can miss generic
  concurrency obligations and can over-credit stale or wrong goldens that merely
  share identifiers with the target.
- Some PR-AF rows are target-drifted or partially stale. Keycloak #41249 and
  Sentry #92393 had contradicted or misattached goldens; Grafana #79265 has two
  contradicted rows against the final merge target. `*sqlstore.DBSession` embeds
  xorm `Session`, whose target implementation defines `Exec(sqlOrArgs ...any)`,
  and `go test ./pkg/services/anonymous/anonimpl/anonstore` passes. The cited
  timestamp bounds also both use `device.UpdatedAt.UTC()` in `updateDevice`.
  Keycloak #41249 is especially clear:
  evaluator-only alignment shows the final target helper explicitly allows
  `currentUser == null`, so the initial-login `fillContextForm` miss is a
  contradicted benchmark expectation rather than an actionable source defect.
- Sentry #95633 shows a different benchmark mismatch: the main and
  test-maintenance passes found stronger queue lifecycle, filtered-offset,
  backpressure, and weak-test-contract issues, but scored 0/3 against PR-AF.
  One high-severity golden is likely stale for the final target because the
  repo requires Python 3.13, where `queue.Queue.shutdown()` exists; the other
  two goldens are low-severity test-maintenance notes (`max_wait = 50` reuse and
  a docstring/assertion mismatch). A later auth-only/no-skill queue/test-contract
  source-check used a clean clustered Graphify cache (118,046 nodes, 335,591
  edges, 2,022 communities; 5/5 files and 17/17 hunks mapped), scanned clean,
  and scored 1/3 by hitting the docstring/assertion mismatch while rejecting the
  Python API row. It also found stronger source-backed defects: graceful shutdown
  drops queued work, commits can stop before worker completions, enqueue-after-
  shutdown can be marked processed, and the promised backpressure is absent.
- Keycloak #36882 shows the difference between a generic reviewer judgment and a
  focused process-control pass. Exact-tree CLI exit/lifecycle challengers traced
  the new `picocli.exit(CompatibilityResult.FEATURE_DISABLED)` calls to
  `System.exit(...)`, but decided that production hard-exit was established for
  these non-server commands and reported only missing exit-code assertions and
  invalid-feature validation ordering. A later focused CLI process-control pass
  recovered the benchmark row by tracing `Runnable.run()` through
  `Picocli.parseAndRun`: in test launch mode `picocli.exit(4)` is suppressed,
  the runnable returns normally, and the command can be observed as success/0.
  An auth-only `CODEX_HOME` rerun also scored 1/1 and sharpened the source trace
  around distribution vs in-VM test-launch behavior, but it still triggered
  host-global `deepreview` and `dev` reads before producing the finding. A later
  auth-only run with explicit no-skill/no-host-path instructions scanned clean
  (`hit_count=0`) and also judged 1/1. This is now a clean isolated recovery and
  a generic concern-class lesson. A clean clustered Graphify cache for the same
  merge SHA built 87,482 nodes, 303,680 clustered edges, and 1,764 communities.
  Coverage is partial (`6/7` files, `10/16` hunks) because
  `UpdateCommandDistTest.java` did not map, but the runtime CLI command and
  `Picocli` surfaces mapped and raw source covered the test fallback.
- Keycloak #32918 is a mixed result. Cache/delegate and provider-self-call
  challengers hit the cleanup alias leak (1/2) and found related stale-cache
  invalidation issues, but both rejected the terse "recursive caching call"
  golden after tracing `session.identityProviders().getById(id)` as a
  single-ID cache hop rather than recursive list loading. Treat this as a weak
  or over-broad golden unless a maintainer confirms that any cache-provider
  re-entry should be considered invalid. A later cache-callgraph pass stayed
  1/2: it again hit the cleanup alias leak and found a source-backed stale
  login-list scenario where org-disabled wrappers suppress invalidation and a
  hidden/link-only IDP can reappear after org re-enable, but it explicitly
  rejected infinite recursive loading. A later clean auth-only/no-skill
  cache/delegate pass used fully healthy clustered Graphify coverage (`4/4`
  files, `12/12` hunks; 83,682 nodes, 291,431 clustered edges, 1,620
  communities), scanned clean with `hit_count=0`, and still judged 0/2. It found
  another source-backed stale-cache issue around `Boolean.parseBoolean(...)`
  invalidation versus exact `"true"` JPA config matching, while explicitly
  rejecting unbounded recursion. This strengthens the over-broad-golden
  assessment rather than a recall-improvement path.
- Keycloak #33832 is a good example of concern-class coverage. A full
  graph-assisted/deepreview-style pass scored 0/2 while finding broader
  provider-order, binary-compatibility, and malformed-DER issues. A controlled
  crypto-provider pass scored 1/2 by catching the default-keystore provider
  returned as Bouncy Castle. A narrow dead-write challenger scored 1/2 by
  catching discarded `ASN1Encoder` writes. Combining those blind passes scored
  2/2, with the broader issues retained as extras.
- Keycloak #37634 shows why the child input must include both source excerpts
  and the raw patch. The first controlled token-id pass scored 1/4 and found a
  stronger extra bug: client-credentials token IDs encode grant shortcut `na`
  because `Constants.GRANT_TYPE` is never set on that path. A second
  parser/test-contract pass, after explicitly reading `inputs/patch.diff`, hit
  the added `AssertEvents.isAccessTokenId` matcher polarity/index bug, the
  three-letter-vs-two-character Javadoc mismatch, and the broad
  `RuntimeException` test catch. Combining the blind passes scored 4/4.
- Keycloak #37038 is a clean positive control for authorization-resource
  contract review. A focused group authorization pass scored 2/2 by tracing
  `canManage()` accepting `VIEW` for mutating group endpoints and
  `getGroupIdsWithViewPermission()` returning authorization resource IDs where
  JPA user filters require membership group IDs. It also found an extra
  hierarchy mismatch: per-user checks walk parent groups, but bulk search/count
  filters only exact membership IDs.
- Grafana #94942 is a clean positive control for feature-gate/implementation
  contract review. A SQL-expression pass scored 2/2 by finding both the
  always-false `enableSqlExpressions` helper and the in-memory DB methods that
  still return `"not implemented"`. It also found an extra legacy-parser gate
  bypass risk if SQL support is restored later.
- Grafana #97529 is a clean positive control for Go cache-concurrency review.
  The child pass scored 2/2 by finding the same-key `BuildIndex` duplicate build
  and overwrite race plus the unsynchronized `TotalDocs` map iteration racing
  with watcher/metric-triggered index creation. It also found an extra startup
  worker race on shared `err` and `totalBatchesIndexed`.
- Keycloak #40940 is a clean positive control for API-contract plus test-race
  review. The child pass scored 2/2 by connecting `getSubGroupsCount()`'s
  nullable deleted-delegate case to the non-null `GroupModel` contract and by
  catching the reader thread assertion before `join`.
- Keycloak #38446 is a clean positive control for credential-model contract
  review. The child pass scored 2/2 by hitting the Optional.get/form-rendering
  server-error path and the missing recovery credential id. It also found
  stronger recovery-code lifecycle issues: user-storage codes can be reused,
  final-code cleanup calls the local stored-credential API on federated
  credentials, and disable-by-type omits recovery codes.
- Sentry #67876 exposes a prioritization failure mode. Security/state-machine
  passes scored 2/3: both found static OAuth `state = pipeline.signature` and
  unsafe `integration.metadata["sender"]["login"]`, but both dropped the narrower
  missing `github_authenticated_user` null-reference while pursuing higher-impact
  callback/bypass issues. A later Graphify-backed nullability/state pass used a
  clean clustered cache with 90,658 nodes, 242,277 clustered edges, 2,147
  communities, and 3/3 changed files plus 20/20 hunks mapped. It still scored
  only 1/3: it hit the sender metadata `KeyError`, found extra source-backed
  OAuth `/user` failure handling and mutable-login-vs-stable-id issues, but
  dropped the static-state finding and still did not isolate missing
  `github_authenticated_user` state. A later neutral state-branch source-check
  pass used the same clean clustered coverage and scored 1/3: it re-hit the
  missing `metadata["sender"]` crash and found a stronger source-backed bypass
  where a missing/delayed installation webhook lets the pipeline create an
  integration without ever comparing `github_authenticated_user` to the app
  installer. It still did not hit the benchmark's narrower missing-state
  null-ref wording. The run avoided host-global `deepreview` but still loaded
  host-global Karpathy, so it is useful qualitative evidence but still not a
  fully clean isolation sample. A later auth-only/no-skill state-completeness
  pass scanned clean (`hit_count=0`) and scored 2/3: it re-hit static OAuth
  state and missing sender metadata, found the delayed-webhook bypass again, and
  still missed the benchmark's narrower missing-state null-ref wording. The
  lesson is that a narrower concern-class pass can improve local source quality
  while reducing or not improving benchmark recall unless complementary findings
  are unioned.
- Sentry #77754 shows the value and cost of concern-class aggregation. The first
  assignment-source pass scored 3/4, finding a stronger same-integration fanout
  regression, the import-time `queued` timestamp, and both misleading test names,
  but it rejected the raw-`datetime` task kwarg as safe under Sentry's current
  pickle Celery config. A Graphify-assisted task-boundary pass scored 2/4 by
  recovering the serializer-portability issue and sharpening the fanout finding,
  but it dropped the low-severity test-name notes. Combining the blind passes
  scored 4/4.
- Cal.com #8087 is a clean positive control for async side-effect review. A
  focused app-store/cleanup pass scored 2/2 by finding both the dynamic import
  rejection path that bypasses the existing null/false fallbacks and the
  `forEach(async ...)` cleanup paths where booking state, notifications, or
  local cancellation can proceed before calendar/video deletions settle. It also
  verified that built-in credential/app key normalization matched seeded app
  store keys.
- Cal.com #7232 is a clean positive control for workflow-reminder lifecycle
  review. The child pass scored 2/2 by finding unawaited reminder cancellation
  calls across booking/workflow paths and the `immediateDelete=true` email
  helper path that cancels SendGrid but leaves the `WorkflowReminder` row
  unmarked and undeleted. It also found a stronger cron-order defect: ordinary
  email cancellation defers provider cancellation to cron, but past cancelled
  rows can be deleted before provider cancellation runs. The benchmark golden is
  directionally useful but imprecise: the target code does call SendGrid on the
  immediate-delete path.
- Cal.com #8330 is a clean positive control for temporal-invariants review. The
  child pass scored 2/2 on `slotStartTime` vs `slotEndTime` and `dayjs(...) ===
  dayjs(...)`, and also found stronger scheduling defects around date overrides
  bypassing busy checks, midnight-shifted overrides, and multiple same-day
  override ranges.
- Cal.com #11059 is a useful precision failure. The token/schema-contract pass
  scored 4/5 by finding the hardcoded `"refresh_token"`, the `safeParse` wrapper
  persistence bug, and the raw `fetch Response` contract mismatch. It mentioned
  the computed Zod keys but framed their consequence as field stripping/token
  corruption, so the judge did not credit the benchmark's narrower invalid-schema
  runtime-error golden. A follow-up schema/runtime-contract pass used a durable
  clean-source Graphify cache for merge SHA `824145b...`; coverage mapped 39/39
  changed runtime files and 53/53 hunks. That pass scored 4/5 too, but hit the
  computed-key Zod defect and missed the hardcoded `refresh_token` fallback.
  Union recall for the case is now 5/5, which supports complementary blind
  passes but not a single-pass robustness claim.
- Sentry #80168 is a clean positive control for abstract-class/API-contract
  review. The child pass scored 2/2 by finding that `MetricAlertDetectorHandler`
  now inherits abstract members without implementations and by catching the stale
  list-vs-dict docstring. It also found an extra test fixture mismatch. A
  Graphify-assisted pass using clean clustered coverage also scored 2/2 and
  produced a tighter two-finding report, but dropped the extra test mismatch;
  Graphify helped focus, not broaden, this case.
- Sentry #80528 shows a severity/filtering gap. A refactor dataflow pass hit
  the transformed-config return bug but dismissed the `MonitorCheckIn` re-fetch
  as safe. A generic Django query-efficiency pass recovered 2/2 by checking
  whether the initial `.values(...)` payload could include the only missing
  per-check-in field (`trace_id`) and reuse the already-known monitor
  environment.
- Grafana #80329 shows the value of a narrow operational logging pass. The first
  broader child run stalled, but a constrained logging review hit 1/1 and found
  that routine cleanup progress was logged at `Error` level, including empty
  batches, plus an extra high-cardinality `ids`/SQL-condition payload concern.
- Grafana #90045 is a clean positive control for logging/metrics-contract
  review. The child pass scored 3/3 by finding the lost enriched context logger,
  storage failures recorded as legacy duration/errors, and `name` used where
  `options.Kind` is required for metrics labels. It also found extra async
  observability problems: request cancellation can abort legacy backfill,
  DeleteCollection legacy failures are recorded as storage metrics, and async
  legacy errors are not logged with their concrete cause.
- Grafana #106778 is a clean positive control for UI actionability/contracts.
  The child pass scored 2/2 by finding the missing React `key` for Grafana
  filtered rows and the `promRule`-only `RuleActionsButtons` path where
  "Silence notifications" can be shown but cannot open the Ruler-backed drawer.
  It also surfaced an extra plausible `skipToken` ability bug: non-Grafana rules
  can inherit Grafana duplicate permissions through the fallback ability path.
- Grafana #90939 and Cal.com #14943 are clean positive controls for focused
  challenger passes. A cache/state-concurrency pass recovered Grafana's missing
  double-check and nil-cache overwrite in one finding (2/2). A background-job
  database-contract pass recovered Cal.com's stale retry increment and unscoped
  deletion predicate (2/2).
- Cal.com #10967 is a good prompt-scope failure case. Full Graphify coverage was
  healthy (22/22 changed files, 58/58 hunks), but the first calendar-contract
  pass scored 2/5: it found the null `mainHostDestinationCalendar.integration`
  crash and the Lark/Office365 create-contract issue, plus extra plausible
  multi-host calendar bugs. A generic changed-line sanity pass found the hidden
  organization billing-flag slug inversion and a real Google update/delete
  fallback bug, raising union recall to 3/5. A later runtime-contract routing
  pass stayed at 2/5: it re-found the crash and adapter-contract issue and added
  a source-backed Google update/delete fallback defect plus an `other_calendar`
  double-update risk, but the judge did not credit the fallback as the benchmark
  G3 because the golden describes the provided-`externalCalendarId` branch while
  the target code's concrete bug is the missing-ID fallback path. The remaining
  benchmark misses are a low-value optional-chain style row and that imprecise
  Google routing row. A later auth-only/no-skill adapter-routing source-check
  scanned clean (`hit_count=0`) and scored 1/5: it re-hit the null
  destination-calendar crash and again found the missing-ID fallback plus
  broader multi-host calendar issues, but still did not hit the style row or the
  provided-ID wording.
- Cal.com #14740 is a clean positive control for server-side contract review.
  Clustered clean Graphify coverage mapped 14/15 changed files and 21/24 hunks;
  the unmapped file was the locale JSON file, so the prompt explicitly required
  raw patch/source fallback. The add-guests pass scored 4/5 by finding the
  blacklist case-sensitivity bypass, the `isTeamAdmin && isTeamOwner` permission
  bug, the wrong original-`guests` email fanout argument, and missing
  server-side duplicate filtering. The miss was the low-value initial
  `[""]` UI state in `MultiEmail`. It also found stronger extra behavioral
  issues: cancelled/rejected bookings can be mutated, attendee rows are
  persisted before calendar update success is known, and event-type email-disable
  settings are ignored. A later client-form/state pass also scored 4/5 and
  source-rejected the remaining low-value `[""]` UI placeholder row: the normal
  dialog path validates `z.string().email()` before mutation and returns early
  when all rows are removed, so the empty sentinel does not reach the API through
  the UI path. This is a useful precision check rather than a recall gain.
- Cal.com #22532 is a precision failure around intended side effects. The first
  calendar-cache pass scored 1/2: it hit the Linux-incompatible `sed -i ''`
  helper script, but missed the empty `updateManyByCredentialId(..., {})`
  timestamp-touch bug after filtering it out as not directly feeding the new
  `CalendarCache.updatedAt` UI path. A timestamp-specific challenger proved that
  Prisma will not advance `SelectedCalendar.updatedAt` for an empty update
  payload, but still left it under false alarms because it required a separate
  downstream reader. Both passes found stronger adjacent cache-status defects:
  legacy `CalendarCache` rows are backfilled with migration time and delegated
  Google calendars can miss cache status/delete because displayed in-memory
  credential ids do not match DB cache credential ids. The reusable lesson is to
  report changed-code no-op side effects when the code/comment establishes the
  intended effect, even if another UI path uses a different timestamp. A later
  no-op side-effect audit still scored 1/2 and rejected the empty update after
  tracing the new UI to `CalendarCache.updatedAt` and the watch cron to channel
  fields rather than `SelectedCalendar.updatedAt`. It added stronger script
  findings: `ENV_FILE="../.env"` can update a parent directory when run from repo
  root, and `dev:cron` invokes undeclared `tsx` through `npx`.
  A later write-side-effect contract pass scored 2/2 by treating the changed
  write itself as the contract: `fetchAvailabilityAndSetCache()` says it is
  updating `SelectedCalendar.updatedAt`, but forwards `{}` through
  `SelectedCalendarRepository.updateManyByCredentialId()` to Prisma, leaving the
  intended timestamp side effect unproven/no-op. This raised both best-single
  and union recall by one and is the clearest reusable prompt improvement so
  far: changed writes that exist only for side effects must be audited at the
  callee/ORM semantics before a reviewer asks whether a downstream reader is
  independently proven.
- Keycloak #36880 is a useful partial miss even with healthy clustered
  Graphify coverage. The clean clustered cache mapped 10/10 files and 49/49
  hunks, and the child pass scored 2/3 by finding the V1/V2 listener cleanup
  gate and the `getClientsWithPermission` typed-resource enumeration bug. It
  missed the direct `hasPermission(ClientModel, scope)` owner-domain bug because
  it accepted the two-argument `findByName` default-owner contract after reading
  surrounding code, despite the target line using the three-argument
  `findByName(server, client.getId(), server.getId())`. This is a concrete
  adversarial-review failure mode: overload/default assumptions can override the
  exact changed call unless the challenger re-checks the callee signature and
  every argument value at the final line. A later targeted overload/owner-domain
  audit recovered that missed G2 but did not restate the listener cleanup defect,
  leaving best-single recall at 2/3 while union recall across the two judged
  attempts is 3/3.
- Keycloak #37429 shows both a raw-patch win and a sanitizer-test miss.
  Graphify mapped the Java/POM/test files, but not the large message-property
  diff surface, so the child prompt had to make the raw patch primary. The pass
  scored 2/4 by finding Italian text copied into Lithuanian account/login OTP
  strings and Traditional Chinese terms copied into a Simplified Chinese account
  string. It missed the extra-anchor sanitizer concern after deciding the
  changed-anchor test was enough, and it skipped the low-value `santizeAnchors`
  misspelling. The reusable lesson is that existing tests are evidence to read,
  not proof that neighboring state-machine/count/order cases are covered. A
  later sanitizer-source pass scored 1/4 but recovered the anchor-validation
  concern in the opposite, source-backed direction: translations can omit
  English anchors because `santizeAnchors()` iterates only translated anchors.
  It also found a stronger extra issue: changing JS admin/account bundles from
  i18next `{{0}}` placeholders to Java `MessageFormat`/choice syntax can render
  literal placeholders in React UI validation errors. Union recall is now 3/4;
  the remaining miss is only the private-helper spelling nit.
- Sentry #94376 is a good example of finding a stronger adjacent contract while
  partially recovering ingestion/cache goldens. Clean clustered Graphify coverage mapped 6/7
  files and 13/15 hunks, with only `pyproject.toml` unmapped. The upsampling
  query-contract pass scored 1/3 by finding the actual-vs-outer dataset routing
  bug in dashboard split queries. It missed `client_sample_rate = 0.0` because
  the review focused on query transforms instead of event ingestion, and it
  rejected the benchmark's Python `hash()` cache-key concern after finding no
  cache key in the changed helper. It also found plausible extra transform gaps:
  `eps()`/`epm()` and aliased `count()` remain raw sampled aggregations. A later
  boundary/cache audit again scored 1/3: it rejected `client_sample_rate=0` after
  tracing production ingestion, where zero/invalid rates are intentionally not
  weighted, still found no source-backed cache invalidation path, and added
  stronger extras around raw top-event ranking versus weighted returned counts
  plus aggregate aliases/equation y-axes bypassing the transform. A helper/data
  semantics pass also scored 1/3: it found a stronger `Factories.store_event`
  divergence where truthy invalid sample rates like `1.5` or `"0.1"` are accepted
  even though production rejects them, and it explicitly rejected cache-key
  speculation because no changed source constructs/deletes such a key. A later
  auth-only/no-skill data/cache source-check scanned clean (`hit_count=0`) and
  scored 2/3 by recovering judge credit for the factory sample-rate row plus the
  routed-dataset row. It still rejected the Python `hash()` cache-key row after
  finding no changed cache writer/delete path. This is a concrete example where
  a generic concern-class prompt can improve recall, but only when it stays
  anchored to changed source contracts.
- Sentry #1 is a clean positive control for focused pagination/auth contract
  review on the `ai-code-review-evaluation/sentry-greptile` fork. The target
  commit was already present in the existing Sentry clone, so the detached
  worktree stayed keyed to the benchmark owner/repo without cloning another
  Sentry-sized repository. Clean clustered Graphify coverage mapped 3/3 files
  and 5/5 hunks. The child pass scored 3/3 by finding negative Django QuerySet
  slicing, nullable `organization_context.member` on token-authenticated requests,
  and numeric `math.floor`/`ceil` cursor logic applied to `datetime` audit-log
  keys.
- Sentry #5 shows why generic concern-class follow-ups are useful but still need
  source-backed rejection. The first API/validator pass scored 0/3 while finding
  plausible extras around field filtering, ignored detector owners, and
  falsy-zero browser report validation. A narrower blind contract challenger
  scored 2/3 by finding the detector update key mismatch (`type` validated but
  `detector_type` persisted) and the replay `zip(error_ids, events.values())`
  ordering bug. It explicitly rejected the browser error-response-format golden
  after checking the changed response paths, and found an additional plausible
  replay bug: raw nodestore blobs are used directly instead of reconstructing
  `Event` objects, so valid exception events can produce blank title/message
  context. A later response-contract pass scored 2/3 and recovered the browser
  Reporting API 422 response-shape row by comparing adjacent error branches: a
  non-list JSON body returns an empty 422 while serializer failures return
  `{"error", "details"}`. It did not restate the detector-key issue, so
  best-single recall stayed 2/3 but union recall for the case is now 3/3. Clean
  clustered Graphify coverage mapped 104/105 files and 321/325 hunks; only
  `devservices/config.yml` was unmapped.
- Sentry #92393 looks misattached or stale relative to the fetched PR target.
  The benchmark goldens are all paginator defects, but the fetched PR is
  `feat(spans): Evict spans during insert` and changes only span buffer,
  consumer, Lua script, and span tests. A clean clustered Graphify cache mapped
  all 6 changed files and 37/37 hunks on the merge target, then the child review
  found source-backed Redis set-to-zset migration and root-span eviction issues.
  Evaluator-only target alignment gives all three paginator goldens
  `patch_identifier_score=0.0` and `target_identifier_score=0.0`. The Codex
  judge still scored 0/3 because none of the paginator goldens are on the
  changed source surface. This is a benchmark-row adjudication problem, not a
  reason to tune reviewers toward unrelated files.
- Discourse commit `267d8be1f5` validates the new commit-URL harness path. The
  clean clustered Graphify cache mapped 2/2 changed files and 3/3 hunks, and the
  auth-only/no-skill child run scanned clean. It scored 0/1 because the benchmark
  row focused on `include_website_name` predicate naming and `'.' << website_host`
  style, while the source-backed review found stronger behavioral defects:
  `website_name` bypasses TL0 anonymous field redaction, URL ports are stripped,
  and host comparisons are case-sensitive.
- Discourse commit `5f8a130277` is the second commit-URL validation case. The
  clean clustered Graphify cache mapped 9/10 changed files and 13/14 hunks; only
  `config/locales/server.en.yml` needed raw patch fallback. The auth-only/no-skill
  child run scanned clean and scored 0/2. It found stronger source-backed signup
  issues: blocked-email matching is exact-string and bypassable by case/whitespace,
  and `user.email.blocked` is missing from non-English server locales. The missed
  rows are lower or weaker signal: a read-side match-count update and an imprecise
  regex example where the real unanchored-domain concern is suffix-after-domain,
  not the cited `evil.example.com` subdomain.
- Discourse commit `6669a2d94d` produced the first Discourse recall hit. The
  clean clustered Graphify cache mapped 7/10 files and 16/20 hunks, with SCSS and
  locale YAML handled through raw fallback. The clean child run scored 1/2 by
  finding the nil `TopicUser` unsubscribe crash. It also found an extra GET-toggle
  semantics issue where the unsubscribe link can change watched/tracked topics to
  regular, then a repeated GET can mute them. The remaining miss is only the
  misspelled `stopNotificiationsText` property, which both producer and consumer
  use consistently.
- Discourse commit `060cda7772` scored 2/3 on the clean auth-only/no-skill pass.
  Graphify mapped 6/8 changed files and 9/13 hunks; admin SCSS and client locale
  YAML used raw fallback. The run hit the async `findMembers()` race and exact-
  multiple empty-page pagination bug, and also found extra public group truncation
  plus stale-offset-after-delete issues. The remaining miss is a test-method
  contract row: one spec uses PUT for `remove_member` even though routes map PUT
  to `add_members` and DELETE to `remove_member`.
- Discourse commit `4f8aed295a` is the first clean no-plugins run after the
  scanner caught host-global `dev` skill reads in an earlier invalid attempt.
  Graphify mapped 18/22 changed files and 21/26 hunks, with CSS, locales, and
  site settings handled by raw fallback. The valid run scored 0/6: it found
  plausible missing asset precompile, raw HTML import XSS, referer JS escaping,
  and async spec-contract issues, but missed every expected source-backed defect:
  `open(url)` SSRF, substring origin validation, full-referrer postMessage
  targetOrigin, ALLOWALL/referer framing, nil/unescaped URL handling in
  `TopicEmbed.import`, and the invalid `<%- end if %>` template block.
- Discourse commit `d1c69189f3` scored 0/4 on a clean no-plugins pass. Graphify
  mapped 21/24 changed files and 28/31 hunks, with locales and site settings
  handled by raw fallback. The review found adjacent migration/category/port
  defects, but missed the source-backed expected rows: `before_validation` nil
  mutation, missing admin update/destroy not-found checks, case-sensitive
  `lower(host) = ?` lookup, and raw-SQL migration values bypassing model
  normalization for scheme/path.
- Discourse commit `ffbaf8c542` is the first post-template-update Discourse
  recovery case. Graphify mapped 3/3 files and 5/5 hunks. The clean no-plugins
  run scored 2/3 by finding the Ruby `downsize` method override and the hardcoded
  client upload-size policy. The remaining source-backed miss is the animated GIF
  branch: `allow_animation` selects `gifsicle --resize-fit`, which expects WxH
  geometry rather than the new `"80%"` dimensions argument.
- Discourse commit `d38c4d5f74` is a stylesheet-only low-severity case where the
  graph is intentionally empty for SCSS (`0/32` files, `0/94` hunks mapped) and
  raw excerpts carry the review. The clean no-plugins SCSS pass scored 2/3 by
  finding concrete light/dark contrast regressions; the remaining miss is another
  selector-specific lightness inversion in topic-post styles.
- Discourse commit `ecfa17b5a7` is a full-coverage i18n fallback/pluralization
  case. The clean no-plugins pass scored 0/2 while finding adjacent fallback
  cache/loading issues. The missed low-severity rows are lazy `@loaded_locales`
  thread-safety and String/Symbol locale normalization/double-loading.
- Discourse commit `5b229316ee` completed the full PR-AF problem list. It is a
  flexbox SCSS migration with empty graph coverage for stylesheets, so raw
  excerpts carried the review. The clean no-plugins pass scored 0/2 while finding
  adjacent header overflow, small-action alignment, and missing Mozilla alignment
  prefix issues. The expected rows were the non-Ember/noscript header panel float
  regression and an invalid `-ms-align-items` declaration; the latter is low-value
  because the same mixin already emits the valid `-ms-flex-align`.
- Single-pass reviews miss concern classes. Generic challenger passes recovered
  Cal.com auth/hygiene issues, Sentry process-lifecycle issues, Grafana logging
  continuity issues, Grafana anonymous-device caller/error-taxonomy issues, and
  Sentry queue test-contract weaknesses.

## Current Subset Snapshot

As of the latest local summary, the best parseable single-review score is
112/136 across 50 judged cases and 170 judge artifacts. Union recall across
judged attempts is 117/136, with the delta coming from complementary focused
passes on cases such as Keycloak #37429, Cal.com #11059, Grafana #79265, Sentry
#5, and Sentry #94376.
The full PR-AF problem list is now judged: 50 cases / 136 goldens, with 0
unjudged cases. The denominator still includes stale, contradicted, imprecise,
and low-value benchmark rows such as Sentry #92393, Keycloak #41249, Grafana
#79265's `Exec(args...)` row, and low-value style/test rows.

Keycloak #36882 also exposed and now verifies a target-alignment bookkeeping
fix: its detached worktree is correctly at merge SHA `0f91e67b9025...`, but the
old target-alignment artifact recorded `repo_dir` as the base clone and
`worktree_head` as that clone's stale `0f8222...` checkout. `target-alignment`
now resolves the cached detached worktree when the requested repo path is at the
wrong SHA, records `source_status=resolved-detached-worktree`, and keeps the
  stale requested head for auditability. The corrected alignment still marks the
  `picocli.exit` row as weak-target-evidence. A later focused source pass
  recovered the row, so this is now a prompt-scope lesson plus a child-isolation
  caveat rather than an unresolved benchmark miss.

Sentry #95633 remains a poor target for quality-oriented prompting. Its only
high-severity golden claims `queue.shutdown(immediate=False)` may not exist in
the standard library, but the target repo declares Python 3.13
(`python_requires >=3.13`, Ruff `target-version = ['py313']`, and devenv
Python 3.13.1), where `queue.Queue.shutdown()` and `queue.ShutDown` are the
intended stdlib API. The remaining test-maintenance miss is the low-value
repeated `max_wait = 50` row; the docstring/assertion mismatch was later
recovered by a clean queue/test-contract pass.

### Remaining Miss Triage

Current generated miss report: 14 cases, 19 missed goldens, 19 annotated
(`/Users/sasha/.cache/code-review/review-lab/remaining-misses.json`).
Current remaining categories: 2 contradicted, 3 misattached/stale, 3 imprecise,
3 low-value style, 1 low-value side-effect, 1 low-value test-contract,
1 low-value test style, 1 overbroad, 1 source-rejected low-value, 1 stale, and
2 weak rows.

- Strong prompt-improvement evidence: Cal.com #22532 shows that reviewers must
  audit write-side-effect contracts at the callee/ORM boundary. This produced a
  2/2 single pass and should feed the next isolated prompt iteration.
- The isolated `prompts/source-check.md` now includes generic lessons from later
  runs: trace writer/reader completeness for new state or persisted metadata
  values, trace CLI process-control through the command framework rather than
  treating direct exit helpers as equivalent to returned exit codes, distinguish
  zero/false/empty from missing values, verify cache writer/delete key parity,
  compare changed test names/docstrings to the actual assertions and timing,
  audit URI/open trust boundaries, check postMessage/framing contracts, verify
  normalization parity across callbacks/raw SQL/lookups, check nil mutation and
  admin not-found handling, trace runtime-option helper dispatch branches,
  batch-check mechanical stylesheet substitutions for outliers, sanity-check
  changed template renderability, inspect shared lazy singleton state, verify
  canonical key normalization for load/cache trackers, and audit flex/grid
  migrations against legacy/no-JS DOM variants.
- Source-backed but deliberately rejected weak rows: Cal.com #14740's empty
  `[""]` UI placeholder, Sentry #67876's missing `github_authenticated_user`
  "null ref" wording, and Cal.com #10967's provided-`externalCalendarId` wording
  all conflict with the exact source path the reviewer traced.
- Mostly low-value rows: Keycloak #37429's private-helper spelling nit,
  Cal.com #10967's redundant optional-chain row, and Sentry #95633's test
  maintenance comment should not drive the main review skill.
- Suspicious or stale rows needing manual benchmark adjudication before more
  reviewer tuning: Sentry #92393, Keycloak #41249, Keycloak #32918, Grafana
  #79265's `Exec(args...)`/UTC rows, and Sentry #94376's remaining cache-key row.
- Genuine hard recall gaps still worth future generic work: remote-fetch trust
  boundaries, exact postMessage origin/targetOrigin contracts, framing policy
  checks, template syntax sanity, nil mutation/not-found handling, normalization
  parity across model callbacks and raw SQL migrations, runtime-option helper
  dispatch, mechanical stylesheet outliers, flex/no-JS layout variants, shared
  lazy state, canonical key normalization, narrow branch/state exhaustiveness,
  and exact changed-call argument tracing. The latest Discourse expansion now
  gives concrete source-backed examples across server, browser, CSS, and i18n;
  several older remaining goldens in this bucket are benchmark-quality disputes
  rather than clear defects.
