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

- Claude Code with the `deepreview` skill available globally (e.g. via `~/.agents/skills/deepreview`).
- `code-review-graph` on `PATH` — used for incremental graph updates after `main` advances. If missing, `sync-and-review` skips the update step and notes it in the summary rather than failing.
- `gh` CLI authenticated — `deepreview` uses it to fetch PR metadata.

## Adding a skill

1. `mkdir skills/<your-skill>`
2. Write `skills/<your-skill>/SKILL.md` with frontmatter (`name`, `description`).
3. `./install.sh`
4. Commit and push.
