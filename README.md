# code-review

Reusable PR review workflows for Claude Code, installed as global skills.

## Skills

- **`/sync-and-review <pr#> [pr# ...]`** — Checkout `main`, fast-forward pull, refresh `code-review-graph` if `main` moved, then run `/deepreview` sequentially against each PR number.

## Install

```bash
git clone git@github.com:sasha-s/code-review.git ~/code-review
cd ~/code-review
./install.sh
```

The installer symlinks each subdirectory under `skills/` into `~/.claude/skills/<name>`. Re-running is safe — existing correct symlinks are left alone; conflicting paths are reported and require manual resolution.

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
| Claude Code with `deepreview` skill globally available (e.g. via `~/.agents/skills/deepreview`) | No |
| `gh` CLI authenticated (`gh auth status` passes) | No — interactive login |
| `code-review-graph` on `PATH` | No — install choice (uv / pipx / etc.) |
| `<repo>/.mcp.json` has a `code-review-graph` entry | **Yes** — runs `code-review-graph install --platform claude-code`, reverts the installer's over-reach (CLAUDE.md patch, `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.windsurfrules`), appends `.mcp.json` + `.code-review-graph/` to `.gitignore` if missing. **Requires a Claude Code restart afterwards** — the skill stops at that point. |
| MCP tools (`mcp__code-review-graph__*`) visible in current session | No — Claude Code restart only |
| `repo-intel-*` skills in `~/.claude/skills/` (code-intel is skill-based, not MCP) | Yes if `~/code-intelligence/` exists — runs its installer |

Installer caveat worth knowing: `code-review-graph install --platform claude-code` is opinionated and writes `.cursorrules`, `.windsurfrules`, `AGENTS.md`, `GEMINI.md`, and patches `CLAUDE.md` even when only Claude Code is targeted. The auto-fix in this skill cleans those up. If you run the installer by hand, audit `git status` afterwards.

## Adding a skill

1. `mkdir skills/<your-skill>`
2. Write `skills/<your-skill>/SKILL.md` with frontmatter (`name`, `description`).
3. `./install.sh`
4. Commit and push.
