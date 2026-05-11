#!/usr/bin/env bash
# Bootstrap ~/code-review and its dependencies on a clean machine.
#
# Idempotent. Re-run safely:
#   - existing correct symlinks are left alone
#   - already-installed CLIs are skipped
#   - already-cloned repos are skipped (no pull, no merge)
#
# What this installs:
#   1. ~/code-review/skills/* symlinked into Claude/Codex/Pi/shared skill roots
#   2. code-review-graph CLI                                       (via `uv tool install`)
#   3. ~/code-intelligence repo (cloned if missing)
#   4. code-intelligence skills + live hook symlinked into host skill/hook roots
#
# What this only CHECKS (no auto-install):
#   - gh CLI presence and auth status
#   - uv  (required to auto-install code-review-graph)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="${REPO_DIR}/skills"
SKILLS_DESTS=(
  "${HOME}/.agents/skills"
  "${HOME}/.claude/skills"
  "${HOME}/.codex/skills"
  "${HOME}/.pi/skills"
)
HOOKS_DESTS=(
  "${HOME}/.agents/hooks"
  "${HOME}/.claude/hooks"
  "${HOME}/.codex/hooks"
  "${HOME}/.pi/hooks"
)

CODE_INTEL_DIR="${HOME}/code-intelligence"
CODE_INTEL_REPO="https://github.com/sasha-s/code-intelligence.git"

# --- output helpers ---------------------------------------------------------

step()  { printf '\n=== %s ===\n' "$*"; }
ok()    { printf '  ok    %s\n' "$*"; }
fix()   { printf '  fix   %s\n' "$*"; }
warn()  { printf '  warn  %s\n' "$*" >&2; }
fail()  { printf '  err   %s\n' "$*" >&2; exit 1; }
note()  { printf '        %s\n' "$*"; }

# --- 1. symlink skills into assistant skill roots ---------------------------

canonical_path() {
  realpath "$1" 2>/dev/null || printf '%s\n' "$1"
}

link_skill_dir() {
  local src="$1"
  local link="$2"
  local name
  name="$(basename "${src}")"

  if [[ -L "${link}" ]]; then
    local existing
    existing="$(readlink "${link}")"
    if [[ "$(canonical_path "${link}")" == "$(canonical_path "${src}")" ]]; then
      ok  "${name}  (already linked)"
      return 0
    fi
    warn "${name}  (symlink points elsewhere: ${existing}); leaving ${link} untouched"
    return 0
  fi
  if [[ -e "${link}" ]]; then
    warn "${name}  (path exists and is not a symlink: ${link}); leaving it untouched"
    return 0
  fi
  ln -s "${src}" "${link}"
  fix "${name}  ->  ${src}"
}

link_file() {
  local src="$1"
  local link="$2"
  local name
  name="$(basename "${src}")"

  if [[ -L "${link}" ]]; then
    local existing
    existing="$(readlink "${link}")"
    if [[ "$(canonical_path "${link}")" == "$(canonical_path "${src}")" ]]; then
      ok  "${name}  (already linked)"
      return 0
    fi
    warn "${name}  (symlink points elsewhere: ${existing}); leaving ${link} untouched"
    return 0
  fi
  if [[ -e "${link}" ]]; then
    warn "${name}  (path exists and is not a symlink: ${link}); leaving it untouched"
    return 0
  fi
  ln -s "${src}" "${link}"
  fix "${name}  ->  ${src}"
}

install_local_skills() {
  step "Local skills"
  [[ -d "${SKILLS_SRC}" ]] || fail "${SKILLS_SRC} not found"
  for dest in "${SKILLS_DESTS[@]}"; do
    note "${SKILLS_SRC} -> ${dest}"
    mkdir -p "${dest}"
    for skill_path in "${SKILLS_SRC}"/*/; do
      [[ -d "${skill_path}" ]] || continue
      local src="${skill_path%/}"
      link_skill_dir "${src}" "${dest}/$(basename "${src}")"
    done
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
  for dest in "${SKILLS_DESTS[@]}"; do
    note "${ci_skills_dir} -> ${dest}"
    mkdir -p "${dest}"
    for skill_path in "${ci_skills_dir}"/*/; do
      [[ -d "${skill_path}" ]] || continue
      local src="${skill_path%/}"
      link_skill_dir "${src}" "${dest}/$(basename "${src}")"
    done

    # repo-intel-live lives one level up (under integrations/vap/skills/, not claude/skills/)
    local live_src="${CODE_INTEL_DIR}/integrations/vap/skills/repo-intel-live"
    if [[ -d "${live_src}" ]]; then
      link_skill_dir "${live_src}" "${dest}/repo-intel-live"
    fi
  done
}

install_code_intelligence_hook() {
  step "repo-intel live hook"
  local hook_src="${CODE_INTEL_DIR}/integrations/vap/scripts/repo_intel_live_hook.py"
  [[ -f "${hook_src}" ]] || fail "${hook_src} not found in clone"
  for dest in "${HOOKS_DESTS[@]}"; do
    mkdir -p "${dest}"
    link_file "${hook_src}" "${dest}/repo_intel_live_hook.py"
  done
  note "set REPO_INTEL_LIVE_HOOK=${HOME}/.agents/hooks/repo_intel_live_hook.py in hosts that need an explicit hook path"
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
echo "Done. Skill roots checked:"
for dest in "${SKILLS_DESTS[@]}"; do
  printf '  %s\n' "${dest}"
done
echo
echo "Next: run '/sync-and-review <pr#> [pr# ...]' from any repo you want to review."
echo "First time in a given Claude Code repo, the skill can register code-review-graph MCP in <repo>/.mcp.json."
echo "For Codex and Pi, configure code-review-graph in that host's MCP/tool settings, then restart or reload the host."
