#!/usr/bin/env bash
# Install code-review skills into ~/.claude/skills via symlink.
# Re-running is safe; existing correct symlinks are left alone.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="${REPO_DIR}/skills"
SKILLS_DEST="${HOME}/.claude/skills"

if [[ ! -d "${SKILLS_SRC}" ]]; then
  echo "error: ${SKILLS_SRC} not found" >&2
  exit 1
fi

mkdir -p "${SKILLS_DEST}"

installed=0
skipped=0

for skill_path in "${SKILLS_SRC}"/*/; do
  [[ -d "${skill_path}" ]] || continue
  skill_name="$(basename "${skill_path}")"
  src="${skill_path%/}"
  link="${SKILLS_DEST}/${skill_name}"

  if [[ -L "${link}" ]]; then
    existing="$(readlink "${link}")"
    if [[ "${existing}" == "${src}" ]]; then
      echo "  ok    ${skill_name}  (already linked)"
      skipped=$((skipped + 1))
      continue
    fi
    echo "  err   ${skill_name}  (symlink points elsewhere: ${existing})" >&2
    echo "        remove ${link} manually and re-run" >&2
    exit 1
  fi

  if [[ -e "${link}" ]]; then
    echo "  err   ${skill_name}  (path exists and is not a symlink: ${link})" >&2
    echo "        remove ${link} manually and re-run" >&2
    exit 1
  fi

  ln -s "${src}" "${link}"
  echo "  link  ${skill_name}  ->  ${src}"
  installed=$((installed + 1))
done

echo
echo "installed=${installed} already-linked=${skipped}"
echo "skills dir: ${SKILLS_DEST}"
echo
echo "Available:"
for skill_path in "${SKILLS_SRC}"/*/; do
  [[ -d "${skill_path}" ]] || continue
  echo "  /$(basename "${skill_path}")"
done
