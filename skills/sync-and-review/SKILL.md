---
name: sync-and-review
description: Sync local main, refresh code-review-graph and repo-intel, then run deepreview against a list of PR numbers. Use when given PR numbers to review. Handles multiple PRs sequentially.
---

# Sync and Review

Workflow: prepare a clean main + up-to-date code graph + fresh repo-intel, then run `deepreview` against each PR in the list.

Operates on the current git repository. Does **not** push, force-push, or modify branches other than `main`.

## Arguments

Space- or comma-separated list of PR numbers. Examples:
- `/sync-and-review 812 811 810`
- `/sync-and-review 812,811,810`

If no PRs are given, ask the user which PRs to review before continuing.

## Prerequisites

Before any other step, verify the review toolchain. Run checks in order. On any failure, print exactly what failed and what the user must do, then exit.

### P1. `gh` CLI authenticated
```bash
gh auth status >/dev/null 2>&1
```
- **Pass**: continue.
- **Fail**: stop. Tell user to run `gh auth login`. No auto-fix (interactive).

### P2. `code-review-graph` on PATH
```bash
export PATH="${HOME}/.local/bin:${HOME}/.local/share/uv/tools/code-review-graph/bin:${PATH}"
command -v code-review-graph >/dev/null 2>&1
```
- **Pass**: continue.
- **Fail**: stop. Tell user to install (`uv tool install code-review-graph`) or fix PATH. No auto-fix.

### P3. Check for repo-intel hook (optional enhancement)
```bash
REPO_INTEL_HOOK="${HOME}/.claude/hooks/repo_intel_live_hook.py"
if [ -f "${REPO_INTEL_HOOK}" ]; then
  echo "REPO_INTEL_HOOK=found"
else
  echo "REPO_INTEL_HOOK=missing"
fi
```
- **Found**: note in summary (enables enhanced deepreview context)
- **Not found**: continue without repo-intel enhancement

## Steps

### 1. Verify clean working tree
```bash
git status --porcelain
```
- **Empty**: continue.
- **Non-empty**: stop. Show what is dirty and ask: stash / commit / abort.

### 2. Capture current branch and sync main
```bash
ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git checkout main
HEAD_BEFORE=$(git rev-parse HEAD)
git pull --ff-only
HEAD_AFTER=$(git rev-parse HEAD)
```
- **Success**: continue.
- **ff-only rejected**: stop. Report diverged history. Do not force/rebase/reset.

Remember `ORIGINAL_BRANCH` for step 7.

### 3. Update code-review-graph if main moved
```bash
if [ "${HEAD_BEFORE}" != "${HEAD_AFTER}" ]; then
  echo "Updating code-review-graph..."
  code-review-graph update
fi
```
- **Skip** if `HEAD_BEFORE == HEAD_AFTER` (main unchanged).
- **Fail**: stop. Do not review against stale graph.

### 4. Refresh repo-intel indexes if main moved
```bash
if [ "${HEAD_BEFORE}" != "${HEAD_AFTER}" ]; then
  echo "Refreshing repo-intel..."
  python3 "${REPO_INTEL_HOOK:-${HOME}/.claude/hooks/repo_intel_live_hook.py}" tool \
    --action refresh \
    --repo "${PWD##*/}" \
    --repo-root "${PWD}" \
    --ensure-fresh true \
    --tracked-only true 2>/dev/null || true
fi
```
- **Skip** if `HEAD_BEFORE == HEAD_AFTER` (main unchanged).
- **Skip** if hook not available (non-blocking enhancement).
- Failures are non-fatal — continue with stale indexes.

### 5. Verify PR refs are reachable

For each OPEN PR in the list, verify the head branch/ref is fetchable. Do not
run `code-review-graph detect-changes` from `main`; `deepreview` creates a
detached per-PR worktree and runs graph analysis there so it inspects the PR
tree, not the synced base branch.

```bash
for PR in <PR_LIST>; do
  STATE=$(gh pr view "${PR}" --json state --jq '.state')
  if [ "${STATE}" = "OPEN" ]; then
    HEAD_BRANCH=$(gh pr view "${PR}" --json headRefName --jq '.headRefName')
    git fetch origin "${HEAD_BRANCH}" 2>/dev/null || true
  fi
done
```

If the fetch fails, log a warning and continue. `deepreview` can still use
`gh pr diff` and will report whether its own worktree preparation succeeds.

### 6. Run deepreview per PR

For each PR in the input list, **sequentially** invoke the `deepreview` skill with just the PR number as argument.

In Pi: use `/skill:deepreview <PR_NUMBER>` — this loads the deepreview SKILL.md and executes the full adversarial review workflow including Pass 0 (code-review-graph), Pass 1 (scope analysis), Pass 2 (adversarial review by lens), and Pass 3 (cross-scope synthesis).

Run one at a time — deepreview output is verbose and benefits from clean attention per PR.

### 7. Restore original branch (if needed)
```bash
if [ "${ORIGINAL_BRANCH}" != "main" ]; then
  echo "Original branch was: ${ORIGINAL_BRANCH}"
  echo "Run 'git checkout ${ORIGINAL_BRANCH}' to return."
fi
```
Do NOT auto-switch — user may want to stay on fresh main.

### 8. Final summary

Output one line per PR with:
- Verdict from deepreview pass
- Path to persisted review file (`~/reviews/<repo>/PR-<N>/<short-sha>.md`)
- Whether graph/repo-intel was refreshed

```
PR 812: ✅ LGTM — ~/reviews/TheEdge/PR-812/ab12cd3.md (graph refreshed, repo-intel refreshed)
PR 811: ✅ LGTM — ~/reviews/TheEdge/PR-811/ef45ab6.md (graph not refreshed)
PR 810: ✅ LGTM — ~/reviews/TheEdge/PR-810/cd78ef9.md (graph not refreshed)
```

`deepreview` is responsible for writing the review file under `~/reviews/<repo>/PR-<N>/`. If a deepreview invocation completes without producing the file, treat it as a failure and note it in the summary.

## Failure modes

| Condition | Auto-fix? | Action |
| --- | --- | --- |
| `gh` not authenticated | No | Stop; tell user to `gh auth login` |
| `code-review-graph` not on PATH | No | Stop; tell user to install |
| repo-intel hook not found | No | Continue without (enhancement only) |
| Dirty working tree | No | Ask user |
| `git pull --ff-only` rejected | No | Stop; report |
| `code-review-graph update` fails | No | Stop; stale graph |
| Single deepreview fails | No (continue) | Note failure, run remaining |
| detect-changes returns 0 functions | No | Log warning, continue |

## What this does NOT do

- Does NOT run deepreview as a bash command (deepreview is a skill, not a binary)
- Does NOT skip deepreview if graph is empty (deepreview works with diff-only analysis)
- Does NOT force-push or modify PR branches
