---
name: sync-and-review
description: Sync local main, refresh code-review-graph if main moved, then run deepreview against a list of PR numbers. Use in Claude Code, Codex, or Pi when reviewing one or more PRs and you want fresh main + fresh graph context before each review.
---

# Sync and Review

Workflow: prepare a clean main + up-to-date code graph, then run the `deepreview` skill against each PR in the list.

Operates on the current git repository (whatever directory the session is running in). Does **not** push, force-push, or modify branches other than `main`.

This skill is host-aware. It works in Claude Code, Codex, Pi, or another assistant host as long as that host can load skills and expose the `code-review-graph` tools. When a step mentions host-specific behavior, use the branch for the current host.

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

### P3. `code-review-graph` MCP configured for the current host

First identify the current assistant host:

- **Claude Code**: repo-local `.mcp.json` is expected.
- **Codex**: MCP is usually configured globally in `~/.codex/config.toml`.
- **Pi**: use Pi's configured MCP/extension tool surface; skill roots are commonly declared in `~/.pi/agent/settings.json`.
- **Other host**: use that host's MCP/tool configuration.

For **Claude Code only**, verify the repo-local MCP entry:

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

For **Codex, Pi, and other hosts**, do not require repo-local `.mcp.json` and do not run the Claude Code installer. Continue to P4; live tool visibility is the source of truth. If P4 fails, report that the current host needs a loaded `code-review-graph` MCP/tool integration and point the user to the relevant host config file (`~/.codex/config.toml` for Codex, `~/.pi/agent/settings.json` or Pi's MCP configuration for Pi).

### P4. MCP tools visible in this session
MCP configuration on disk does not prove the tools are loaded in the current session. Verify that a representative `code-review-graph` tool is callable before doing any review work.

Host-specific discovery:

- **Claude Code**: run `ToolSearch(query: "code-review-graph", max_results: 5)`.
- **Codex**: if `code-review-graph` tools are not already visible, use `tool_search` with query `code-review-graph` and surface the matching tools.
- **Pi**: use Pi's tool or extension discovery and verify that the `code-review-graph` tools are callable.
- **Other host**: use that host's tool discovery.

This passes if at least one graph tool is callable, preferably one of:

```
detect_changes, get_affected_flows, get_impact_radius, query_graph
```
- **Pass**: continue.
- **Fail**: stop. Tell the user to restart or reload the current assistant host after enabling `code-review-graph`. No auto-fix is possible from inside the session.

### P5. code-intel / repo-intel skills present
`code-intel` is **skill-based, not MCP** — lives in `~/code-intelligence/` and surfaces as `repo-intel-*` skills. Check the skill roots for the current host. Common roots:

- Claude Code: `~/.claude/skills`
- Codex: `~/.codex/skills`, `~/.agents/skills`
- Pi: `~/.pi/skills`, `~/.agents/skills`, and any roots listed in `~/.pi/agent/settings.json`

A portable fallback check for the common roots:

```bash
for root in \
  "${HOME}/.claude/skills" \
  "${HOME}/.codex/skills" \
  "${HOME}/.pi/skills" \
  "${HOME}/.agents/skills"
do
  for skill in "${root}"/repo-intel-*; do
    test -e "${skill}/SKILL.md" && exit 0
  done
done
exit 1
```
- **Pass**: continue.
- **Fail → AUTO-FIX**: if `~/code-review/install.sh` exists, run it once; it symlinks this repo's skills and repo-intel skills into the supported host skill roots. Re-verify.
  - **Still fail or `~/code-intelligence/` missing**: stop. Tell the user to clone/install `code-intelligence`, run the `code-review` installer, restart or reload the current host, and re-run.

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

Use the current host's background shell support, if available, with a generous timeout (e.g. 600000ms / 10 min), then wait for completion before continuing. If the host only supports foreground shell execution, run the command in the foreground and wait.

`code-review-graph` is a prerequisite (P2) — by this step it is guaranteed present. If the update command fails, **stop** and report the error; do not proceed to reviews against a stale graph.

If `HEAD_BEFORE == HEAD_AFTER`, skip the update.

### 4. Run deepreview per PR

For each PR in the input list, **sequentially** invoke the `deepreview` skill with just the PR number as args.

Host-specific invocation:

- **Claude Code**: `Skill(skill: "deepreview", args: "<pr_number>")`
- **Codex**: use the loaded `deepreview` skill instructions with `<pr_number>` as the input; if there is no explicit skill invocation tool, read/apply the `deepreview` skill inline.
- **Pi**: trigger the loaded `deepreview` skill with `<pr_number>` as the input; if Pi exposes skills as prompt commands, use that command form.

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
| Claude Code `.mcp.json` missing graph entry | Yes — run installer, revert side-effects | Stop after fix; tell user to restart Claude Code |
| Codex/Pi graph integration missing | No generic auto-fix | Stop; tell user to configure the current host and restart/reload |
| MCP/tools not visible in session | No (session restart/reload) | Stop; tell user to restart/reload the current host |
| `repo-intel-*` skills missing | Yes — run `~/code-review/install.sh` if present | Stop if auto-fix fails |
| Dirty working tree | No (data safety) | Ask user: stash / commit / abort |
| `git pull --ff-only` rejected | No (data safety) | Stop, report; do not force/rebase/reset |
| `code-review-graph update` fails | No | Stop; do not review against a stale graph |
| A single `deepreview` invocation fails | No (continue) | Note failure in summary, run remaining PRs |
