# outcome-ledger

Offline mining of what actually happened to the findings the scheduled
`deepreview` watcher has been posting to `TheEdgeApp/TheEdge` PRs.

## Hard boundary (same rule as `learning-repository/`)

This directory is **analysis-only**.

- Do not load the ledger, its summary, or any family/acceptance statistic into a
  reviewer prompt.
- Do not reference it from `prompts/source-check.md`.
- Do not reference it from the global `deepreview` skill or any other skill.
- Do not copy it into child workspaces.
- If a future experiment wants to use it (e.g. to down-weight a
  false-positive-prone finding family), add an explicit opt-in selector and
  measure that path separately.

It also inherits review-lab's blind separation rule: this tool runs strictly
*after* a review artifact already exists. It never participates in producing one.

## Safety properties

- **Read-only against GitHub.** Every API call is a GET. Nothing posts, edits,
  reacts to, or resolves anything.
- **Read-only against `~/TheEdge`.** Only `git show` / `git log` / `git cat-file`
  / `git rev-parse` / `git merge-base` / `git ls-tree` are permitted (enforced
  in `gh_fetch.git()`). No checkouts, no worktrees, no fetches, no index or ref
  writes.
- **Never touches watcher state.** `reviewed-prs.tsv`, `posted-comments.tsv`,
  `attempts.tsv`, and `theedge-pr-review-watch.sh` are read and never written.
- **Output lives out of any git repo**, under `~/.review/TheEdge/ledger/`,
  because it contains private product data (finding text, file paths, PR titles).
  Only the code lives here in `code-review`.

## Layout

```
parse_reviews.py         markdown -> findings (ledger tables + fallbacks)
gh_fetch.py              read-only GitHub + git collectors, disk-cached
join_outcomes.py         finding -> outcome label, with explicit signal strength
build_outcome_ledger.py  CLI: parse / fetch / join / all
```

## Usage

```bash
python3 experiments/review-lab/outcome-ledger/build_outcome_ledger.py all
# or one stage at a time
python3 .../build_outcome_ledger.py parse      # no network
python3 .../build_outcome_ledger.py fetch      # cached; re-runs are ~free
python3 .../build_outcome_ledger.py join       # no network
python3 .../build_outcome_ledger.py fetch --refresh   # force re-fetch
```

Outputs (all under `~/.review/TheEdge/ledger/`):

| file | contents |
| --- | --- |
| `findings.jsonl` | one row per finding, with outcome label, strength, basis, and raw signals |
| `findings.raw.jsonl` | pre-join parse output |
| `reviews.jsonl` | one row per review artifact (round, head, timestamps, parse counts) |
| `summary.json` | overall / per-severity / per-family acceptance rates, ranked families, biases |
| `parse_report.json` | parse coverage, honestly counted |
| `cache/gh/PR-<n>/*.json` | cached GitHub responses |
| `cache/commit_files.json` | cached `sha -> changed files` from local git |

## Finding identity

A finding is keyed by `(PR, ledger id)` — e.g. `(988, "R7")`. `deepreview`
maintains a cumulative Findings Ledger across rounds with stable ids, so the same
row reappears in every later round file with an updated status. The ledger folds
those appearances into one record: first round, last round, status history, final
status. `finding_uid` is `sha1("TheEdge|<pr>|<id>|<normalized first text>")[:16]`.

## Signal strength

Never collapsed into one number. See the docstring in `join_outcomes.py`:

- **strong** — the reviewer re-verified the finding against a later head in a
  later round and recorded a terminal status (`resolved` / `still-open` /
  `rejected` / `obsolete`), or a human comment on the PR names the finding's
  ledger id.
- **medium** — a human replied on the PR or reacted after our comment was
  posted. PR-level, not finding-level.
- **weak** — files the finding cites changed in commits pushed after the review,
  and/or the PR reached a terminal state. **Circumstantial.** A file changing
  after a review is not evidence that the finding was accepted.
- **none** — reviewed once, never re-reviewed, no post-review activity.

Acceptance rate is computed **only over strong labels**, and its denominator is
always reported alongside it.

## Null baselines and validity tests

`null_baseline.py` exists because a rate is not a result until something random
has been run through the same pipeline. It writes `null_baseline.json`.

```bash
python3 experiments/review-lab/outcome-ledger/null_baseline.py
```

| test | what it asks |
| --- | --- |
| T1 | Do synthetic findings pointing at random files score like real ones on the file-changed-after proxy? |
| T2 | What acceptance rate would that proxy have reported, real vs control? |
| T3 | Does post-review churn differ between `acted_on` and `not_acted_on`, or is the verdict a rubber stamp? |
| T4 | Do resolved statuses cite commits that actually exist and touch the cited files? |
| T5 | How many `acted_on` findings have nothing but the reviewer's word behind them? |
| T6 | Do per-round verdicts move monotonically or flap? |

**Result: the file-changed-after proxy is retired as a label.** A synthetic
finding pointing at a random file the PR had already touched at review time
scores 0.675 on it, against 0.917 for real findings — roughly three quarters of
the signal is free. It stays in `findings.jsonl` as weak corroboration and
produces zero acceptance labels.

**What could not be baselined:** the strong label itself. Null-baselining
deepreview's re-review verdict means injecting fabricated findings into a live
re-review round and measuring how many come back `resolved` — that requires
running reviews, not reading them, so it is out of scope for a read-only tool.
T3, T4 and T6 are indirect validity evidence, not a substitute. The proposed
experiment is written up in `null_baseline.json` under
`what_could_not_be_baselined`.

**Do not prune reviewer prompts from the family table.** With Wilson intervals
applied, exactly one family of 21 separates from the corpus rate, and its
interval is [0.24, 0.76]. The ranking is noise at this sample size; the summary
carries `distinguishable_from_corpus_rate` on every row for this reason.
