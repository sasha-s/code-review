#!/usr/bin/env bash
# Bootstrap ~/code-review and its dependencies on a clean machine.
#
# Idempotent. Re-run safely:
#   - existing correct symlinks are left alone
#   - already-installed CLIs are skipped
#   - already-cloned repos are skipped (no pull, no merge)
#
# What this installs:
#   1. ~/code-review/skills/* symlinked into ~/.claude/skills/    (sync-and-review, deepreview)
#   2. code-review-graph CLI                                       (via `uv tool install`)
#   3. ~/code-intelligence repo (cloned if missing)
#   4. code-intelligence skills + live hook symlinked into ~/.claude
#
# What this only CHECKS (no auto-install):
#   - gh CLI presence and auth status
#   - uv  (required to auto-install code-review-graph)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="${REPO_DIR}/skills"
SKILLS_DEST="${HOME}/.claude/skills"
HOOKS_DEST="${HOME}/.claude/hooks"

CODE_INTEL_DIR="${HOME}/code-intelligence"
CODE_INTEL_REPO="https://github.com/sasha-s/code-intelligence.git"

# --- output helpers ---------------------------------------------------------

step()  { printf '\n=== %s ===\n' "$*"; }
ok()    { printf '  ok    %s\n' "$*"; }
fix()   { printf '  fix   %s\n' "$*"; }
warn()  { printf '  warn  %s\n' "$*" >&2; }
fail()  { printf '  err   %s\n' "$*" >&2; exit 1; }
note()  { printf '        %s\n' "$*"; }

# --- 1. symlink ~/code-review/skills/* into ~/.claude/skills/ ---------------

link_skill_dir() {
  local src="$1"
  local link="$2"
  local name
  name="$(basename "${src}")"

  if [[ -L "${link}" ]]; then
    local existing
    existing="$(readlink "${link}")"
    if [[ "${existing}" == "${src}" ]]; then
      ok  "${name}  (already linked)"
      return 0
    fi
    fail "${name}  (symlink points elsewhere: ${existing}); remove ${link} manually and re-run"
  fi
  if [[ -e "${link}" ]]; then
    fail "${name}  (path exists and is not a symlink: ${link}); remove it manually and re-run"
  fi
  ln -s "${src}" "${link}"
  fix "${name}  ->  ${src}"
}

install_local_skills() {
  step "Local skills (${SKILLS_SRC} -> ${SKILLS_DEST})"
  [[ -d "${SKILLS_SRC}" ]] || fail "${SKILLS_SRC} not found"
  mkdir -p "${SKILLS_DEST}"
  for skill_path in "${SKILLS_SRC}"/*/; do
    [[ -d "${skill_path}" ]] || continue
    local src="${skill_path%/}"
    link_skill_dir "${src}" "${SKILLS_DEST}/$(basename "${src}")"
  done
}

# --- 2. code-review-graph CLI -----------------------------------------------

install_code_review_graph() {
  step "code-review-graph CLI"
  if command -v code-review-graph >/dev/null 2>&1; then
    ok "code-review-graph $(code-review-graph --version 2>/dev/null || echo '(present)')"
    return 0
  fi
  if ! command -v uv >/dev/null 2>&1; then
    fail "code-review-graph not on PATH and 'uv' not available; install uv (https://docs.astral.sh/uv/) or 'pipx install code-review-graph' yourself"
  fi
  fix "installing via 'uv tool install code-review-graph' ..."
  uv tool install code-review-graph
  command -v code-review-graph >/dev/null 2>&1 || fail "install reported success but binary still not on PATH; check ~/.local/bin in your PATH"
  ok "code-review-graph installed: $(code-review-graph --version)"
}

# --- 3. ~/code-intelligence repo + its integrations -------------------------

clone_code_intelligence() {
  step "~/code-intelligence repo"
  if [[ -d "${CODE_INTEL_DIR}/.git" ]]; then
    ok "${CODE_INTEL_DIR} (already cloned; not pulling — manage updates yourself)"
    return 0
  fi
  if [[ -e "${CODE_INTEL_DIR}" ]]; then
    fail "${CODE_INTEL_DIR} exists but is not a git repo; resolve manually"
  fi
  fix "cloning ${CODE_INTEL_REPO} -> ${CODE_INTEL_DIR}"
  git clone "${CODE_INTEL_REPO}" "${CODE_INTEL_DIR}"
}

install_code_intelligence_skills() {
  step "code-intelligence skills"
  local ci_skills_dir="${CODE_INTEL_DIR}/integrations/vap/claude/skills"
  if [[ ! -d "${ci_skills_dir}" ]]; then
    fail "${ci_skills_dir} not found; clone of ${CODE_INTEL_REPO} may be stale (missing integrations/vap)"
  fi
  for skill_path in "${ci_skills_dir}"/*/; do
    [[ -d "${skill_path}" ]] || continue
    local src="${skill_path%/}"
    link_skill_dir "${src}" "${SKILLS_DEST}/$(basename "${src}")"
  done

  # repo-intel-live lives one level up (under integrations/vap/skills/, not claude/skills/)
  local live_src="${CODE_INTEL_DIR}/integrations/vap/skills/repo-intel-live"
  if [[ -d "${live_src}" ]]; then
    link_skill_dir "${live_src}" "${SKILLS_DEST}/repo-intel-live"
  fi
}

install_code_intelligence_hook() {
  step "repo-intel live hook"
  local hook_src="${CODE_INTEL_DIR}/integrations/vap/scripts/repo_intel_live_hook.py"
  local hook_link="${HOOKS_DEST}/repo_intel_live_hook.py"
  [[ -f "${hook_src}" ]] || fail "${hook_src} not found in clone"
  mkdir -p "${HOOKS_DEST}"
  if [[ -L "${hook_link}" ]]; then
    local existing
    existing="$(readlink "${hook_link}")"
    if [[ "${existing}" == "${hook_src}" ]]; then
      ok "repo_intel_live_hook.py  (already linked)"
      return 0
    fi
    fail "repo_intel_live_hook.py symlink points elsewhere (${existing}); remove ${hook_link} and re-run"
  fi
  [[ -e "${hook_link}" ]] && fail "${hook_link} exists and is not a symlink"
  ln -s "${hook_src}" "${hook_link}"
  fix "repo_intel_live_hook.py  ->  ${hook_src}"
  note "remember to set REPO_INTEL_LIVE_HOOK=${hook_link} in ~/.claude/settings.json env"
}

# --- 4. gh CLI presence (check only) ----------------------------------------

check_gh() {
  step "gh CLI"
  if ! command -v gh >/dev/null 2>&1; then
    warn "gh not on PATH; install with 'brew install gh' (or your package manager) and run 'gh auth login'"
    return 0
  fi
  if ! gh auth status >/dev/null 2>&1; then
    warn "gh is installed but not authenticated; run 'gh auth login'"
    return 0
  fi
  ok "gh authenticated"
}

# --- run --------------------------------------------------------------------

install_local_skills
install_code_review_graph
clone_code_intelligence
install_code_intelligence_skills
install_code_intelligence_hook
check_gh

echo
echo "Done. Available skills under ${SKILLS_DEST}:"
for d in "${SKILLS_DEST}"/*/; do
  [[ -L "${d%/}" ]] || continue
  printf '  /%s\n' "$(basename "${d%/}")"
done
echo
echo "Next: run '/sync-and-review <pr#> [pr# ...]' from any repo you want to review."
echo "First time in a given repo, the skill will register code-review-graph MCP in <repo>/.mcp.json"
echo "and ask you to restart Claude Code so the MCP tools become available."
