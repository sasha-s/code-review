# code-review

Reusable PR review workflows for Claude Code, Codex, and Pi, installed as global skills.

## Skills

- **`/sync-and-review <pr#> [pr# ...]`** — Checkout `main`, fast-forward pull, refresh `code-review-graph` if `main` moved, then run `deepreview` sequentially against each PR number.
- **`/deepreview <pr#>`** — Adversarial three-pass PR review: scope analysis, design summary, then reviewer-challenger dialogs through dev / security / sre / research lenses with graph-backed reconnaissance (Pass 0).

## Install

```bash
git clone https://github.com/sasha-s/code-review.git ~/code-review
cd ~/code-review
./install.sh
```

The installer is idempotent and bootstraps everything needed:

1. Symlinks `skills/*` into shared and host skill roots: `~/.agents/skills/`, `~/.claude/skills/`, `~/.codex/skills/`, and `~/.pi/skills/`
2. `uv tool install code-review-graph` if the CLI is not on `PATH` (requires `uv` — see https://docs.astral.sh/uv/)
3. Clones `github.com/sasha-s/code-intelligence` into `~/code-intelligence/` if missing
4. Symlinks code-intelligence's `repo-intel-*` skills into the same skill roots
5. Symlinks `repo_intel_live_hook.py` into shared and host hook roots: `~/.agents/hooks/`, `~/.claude/hooks/`, `~/.codex/hooks/`, and `~/.pi/hooks/`
6. Checks (does NOT auto-install) `gh` CLI presence and auth

Re-run safely — existing correct symlinks are left alone, already-installed CLIs skipped, already-cloned repos are not pulled, and pre-existing non-symlink skills are left untouched with a warning.

After install, hosts that need an explicit repo-intel hook path should set:

```bash
REPO_INTEL_LIVE_HOOK=/Users/<you>/.agents/hooks/repo_intel_live_hook.py
```

## Update

```bash
cd ~/code-review
git pull
```

Symlinked skills track the repo, so no re-install is needed after a pull (unless a new skill directory was added — then re-run `./install.sh`).

## Requirements

`/sync-and-review` is **fail-fast** — it will not proceed with a degraded toolchain. Each requirement below is checked at the start; where an auto-fix is safe, the skill attempts it once.

| Requirement | Auto-fix on miss? |
| --- | --- |
| Current host (Claude Code, Codex, or Pi) can load `sync-and-review` and `deepreview` skills | Run `./install.sh` |
| `gh` CLI authenticated (`gh auth status` passes) | No — interactive login |
| `code-review-graph` on `PATH` | No — install choice (uv / pipx / etc.) |
| Claude Code `<repo>/.mcp.json` has a `code-review-graph` entry | **Yes** — runs `code-review-graph install --platform claude-code`, reverts the installer's over-reach (CLAUDE.md patch, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.windsurfrules`), appends `.mcp.json` + `.code-review-graph/` to `.gitignore` if missing. **Requires a Claude Code restart afterwards** — the skill stops at that point. |
| Codex/Pi has a loaded `code-review-graph` MCP/tool integration | No generic auto-fix — configure the host, then restart or reload it |
| MCP/tools visible in current session | No — host restart/reload only |
| `repo-intel-*` skills visible in the current host's skill roots (code-intel is skill-based, not MCP) | Yes if `~/code-review/install.sh` is present |

Installer caveat worth knowing: `code-review-graph install --platform claude-code` is opinionated and writes `.cursorrules`, `.windsurfrules`, `AGENTS.md`, `GEMINI.md`, and patches `CLAUDE.md` even when only Claude Code is targeted. The auto-fix in this skill cleans those up. Codex and Pi setup does not use that Claude installer path; configure their MCP/tool integration in the host's own settings.

## Adding a skill

1. `mkdir skills/<your-skill>`
2. Write `skills/<your-skill>/SKILL.md` with frontmatter (`name`, `description`).
3. `./install.sh`
4. Commit and push.
