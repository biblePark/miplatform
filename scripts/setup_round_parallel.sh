#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 [--dry-run] <round-id> <base-branch> <lane-name> [<lane-name> ...]"
  echo "Example: $0 --dry-run r04 main api-mapping ui-preview"
  exit 2
fi

ROUND_ID="$1"
BASE_BRANCH="$2"
shift 2

for LANE in "$@"; do
  BRANCH="codex/${ROUND_ID}-${LANE}"
  WORKTREE="/tmp/miflatform-${ROUND_ID}-${LANE}"

  if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
    echo "[skip] branch exists: ${BRANCH}"
  else
    echo "[create] branch: ${BRANCH}"
  fi

  if [[ -d "${WORKTREE}" ]]; then
    echo "[skip] worktree exists: ${WORKTREE}"
    continue
  fi

  echo "[create] worktree: ${WORKTREE}"
  if [[ "${DRY_RUN}" -eq 0 ]]; then
    git worktree add "${WORKTREE}" -b "${BRANCH}" "${BASE_BRANCH}"
  fi
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Dry-run complete."
else
  echo "Done."
fi
