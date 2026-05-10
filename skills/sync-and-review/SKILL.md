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

## Prerequisites — fail-fast, auto-fix where safe

Before any other step, verify the review toolchain. **Every check is hard-fail.** No "skip + warn" path — degraded review is the failure mode we are explicitly preventing. Where an auto-fix is safe and cheap, attempt it once; if it doesn't resolve the check, stop.

Run the checks in order. On any failure, print exactly what failed, what (if anything) was auto-fixed, and what the user must do. Then exit the skill.

### P1. `gh` CLI authenticated
```bash
gh auth status >/dev/null 2>&1
```
- **Pass**: continue.
- **Fail**: stop. Tell the user to run `gh auth login`. No auto-fix (interactive).

### P2. `code-review-graph` on PATH
```bash
command -v code-review-graph >/dev/null 2>&1
```
- **Pass**: continue.
- **Fail**: stop. Tell the user to install it (`uv tool install code-review-graph` or follow project README). No auto-fix — package installation requires user choice (uv vs pipx vs system Python, version pin, etc.).

### P3. `code-review-graph` MCP registered in the current repo
```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
test -f "${REPO_ROOT}/.mcp.json" && \
  grep -q '"code-review-graph"' "${REPO_ROOT}/.mcp.json"
```
- **Pass**: continue to P4.
- **Fail → AUTO-FIX**:
  1. Snapshot pre-state: `git -C "${REPO_ROOT}" status --porcelain > /tmp/sar-pre.txt`.
  2. Run `code-review-graph install --platform claude-code` from `${REPO_ROOT}`.
  3. Clean up installer over-reach — these files are written even with `--platform claude-code`:
     ```bash
     cd "${REPO_ROOT}"
     # Revert CLAUDE.md if the installer patched it.
     git diff --quiet -- CLAUDE.md || git checkout -- CLAUDE.md
     # Delete other-tool configs the installer creates uninvited.
     rm -f AGENTS.md GEMINI.md .cursorrules .windsurfrules
     ```
  4. If `.mcp.json` and `.code-review-graph/` are not in `.gitignore`, append them (per-dev MCP setup is the standard for this org).
  5. Re-verify P3.
  - **Still fail after auto-fix**: stop, show the user the install output, and tell them to investigate.
  - **Pass after auto-fix**: continue, but the MCP tools will NOT be visible in this session — Claude Code must restart to pick up a newly-written `.mcp.json`. **Stop and tell the user to restart Claude Code and re-run `/sync-and-review`.** Do not proceed into reviews with no MCP available.

### P4. MCP tools visible in this session
The presence of `.mcp.json` does not prove the MCP is loaded — Claude Code only registers MCPs at session start. Verify a representative tool is callable:
```
ToolSearch(query: "code-review-graph", max_results: 5)
```
- **Pass** (at least one `mcp__code-review-graph__*` tool returned): continue.
- **Fail**: stop. Tell the user to restart Claude Code. No auto-fix possible (session restart cannot be done from inside the session).

### P5. code-intel / repo-intel skills present
`code-intel` is **skill-based, not MCP** — lives in `~/code-intelligence/` and surfaces as `repo-intel-*` skills.
```bash
ls ~/.claude/skills/ | grep -q '^repo-intel-'
```
- **Pass**: continue.
- **Fail → AUTO-FIX**: if `~/code-intelligence/` exists, run its install script (typically `~/code-intelligence/integrations/vap/scripts/install.sh` or similar). Re-verify.
  - **Still fail or `~/code-intelligence/` missing**: stop. Tell the user to clone/install `code-intelligence` and re-run.

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

`code-review-graph` is a prerequisite (P2) — by this step it is guaranteed present. If the update command fails, **stop** and report the error; do not proceed to reviews against a stale graph.

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

Output one line per PR with the verdict from each deepreview pass. Note whether the graph was refreshed.

## Failure modes — fail-fast policy

This skill **never proceeds with a degraded toolchain**. Every prerequisite is hard-fail. Auto-fix is attempted only where it is safe and non-interactive; if auto-fix succeeds but requires a session restart (e.g. new MCP registration), the skill stops and tells the user to restart.

| Condition | Auto-fix? | Action |
| --- | --- | --- |
| `gh` not authenticated | No (interactive) | Stop; tell user to `gh auth login` |
| `code-review-graph` not on PATH | No (install choice) | Stop; tell user to install |
| `.mcp.json` missing graph entry | Yes — run installer, revert side-effects | Stop after fix; tell user to restart Claude Code |
| MCP tools not visible in session | No (session restart) | Stop; tell user to restart Claude Code |
| `repo-intel-*` skills missing | Yes — run code-intelligence installer if repo present | Stop if auto-fix fails |
| Dirty working tree | No (data safety) | Ask user: stash / commit / abort |
| `git pull --ff-only` rejected | No (data safety) | Stop, report; do not force/rebase/reset |
| `code-review-graph update` fails | No | Stop; do not review against a stale graph |
| A single `deepreview` invocation fails | No (continue) | Note failure in summary, run remaining PRs |
