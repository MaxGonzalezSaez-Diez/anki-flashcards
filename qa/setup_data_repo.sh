#!/usr/bin/env bash
set -euo pipefail

DEFAULT_REMOTE="https://github.com/MaxGonzalezSaez-Diez/anki-cards.git"
DEFAULT_LOCAL="$HOME/Desktop/projects/anki-cards"

REMOTE="${1:-${BACKUP_REPO:-$DEFAULT_REMOTE}}"
LOCAL_DIR="${2:-${BACKUP_LOCAL_REPO:-$DEFAULT_LOCAL}}"

normalize_remote() {
  local u="$1"
  u="${u%/}"
  u="${u%.git}"
  printf "%s" "$u"
}

mkdir -p "$(dirname "$LOCAL_DIR")"

if [[ -d "$LOCAL_DIR/.git" ]]; then
  # "git -C <dir> ..." runs git as if we were in <dir>.
  CURRENT_REMOTE="$(git -C "$LOCAL_DIR" remote get-url origin)"
  if [[ "$(normalize_remote "$CURRENT_REMOTE")" != "$(normalize_remote "$REMOTE")" ]]; then
    echo "Error: backup remote mismatch." >&2
    echo "  expected: $REMOTE" >&2
    echo "  found:    $CURRENT_REMOTE" >&2
    exit 1
  fi

  # "fetch --all --prune" updates all remotes and removes deleted remote refs.
  git -C "$LOCAL_DIR" fetch --all --prune
  # "pull --ff-only" updates only when fast-forward is possible (no merge commit).
  git -C "$LOCAL_DIR" pull --ff-only
else
  if [[ -e "$LOCAL_DIR" ]]; then
    echo "Error: path exists but is not a git repo: $LOCAL_DIR" >&2
    exit 1
  fi

  # Initial clone of the backup repository.
  git clone "$REMOTE" "$LOCAL_DIR"
fi

echo "Backup repo ready: $LOCAL_DIR"
