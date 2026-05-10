---
name: sync-and-review
description: Sync local main, refresh code-review-graph if main moved, then run /deepreview against a list of PR numbers. Use when reviewing one or more PRs and you want fresh main + fresh graph context before each review.
---

# Sync and Review

Workflow: prepare a clean main + up-to-date code graph, then run the `deepreview` skill against each PR in the list.

Operates on the current git repository (whatever directory the session is running in). Does **not** push, force-push, or modify branches other than `main`.

## Arguments

Space- or comma-separated list of PR numbers. Examples:

- `/sync-and-review 760 758 752`
- `/sync-and-review 760,758,752`

If no PRs are given, ask the user which PRs to review before continuing. Do not invent a list.

## Steps

### 1. Verify clean working tree

Run `git status --porcelain`. If output is non-empty:

- Stop.
- Show the user what is dirty and ask whether to stash, commit, or abort.
- Do **not** discard uncommitted changes on your own.

### 2. Capture current branch and sync main

```bash
ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git checkout main
HEAD_BEFORE=$(git rev-parse HEAD)
git pull --ff-only
HEAD_AFTER=$(git rev-parse HEAD)
```

If `git pull --ff-only` fails (diverged history, conflicts, no upstream), stop and report. Do not force, rebase, or reset.

Remember `ORIGINAL_BRANCH` so it can be restored at the end if it is not `main`.

### 3. Update code-review-graph if main moved

If `HEAD_BEFORE != HEAD_AFTER`, run `code-review-graph update` and let it run to completion. This can take several minutes on a large repo — do **not** interrupt or assume hang.

Use `Bash` with `run_in_background: true` and a generous `timeout` (e.g. 600000ms / 10 min), then wait for the completion notification before continuing.

If `command -v code-review-graph` returns nothing, skip this step and note it in the final summary — do not fail the whole workflow.

If `HEAD_BEFORE == HEAD_AFTER`, skip the update.

### 4. Run deepreview per PR

For each PR in the input list, **sequentially** invoke the `deepreview` skill with just the PR number as args:

```
Skill(skill: "deepreview", args: "<pr_number>")
```

Run them one at a time — deepreview output is verbose and benefits from clean attention per PR. Do not parallelize.

### 5. Restore original branch (if needed)

If `ORIGINAL_BRANCH` was not `main`, offer to switch back. Do not switch automatically — the user may want to stay on fresh main.

### 6. Final summary

Output one line per PR with the verdict from each deepreview pass. Note whether the graph was refreshed or skipped.

## Failure modes to surface explicitly

- Dirty working tree → ask, do not auto-stash.
- `git pull --ff-only` rejected → stop, report, do not force.
- `code-review-graph` missing on PATH → skip + note.
- A single deepreview failing → continue with the rest, note the failure in the summary.
