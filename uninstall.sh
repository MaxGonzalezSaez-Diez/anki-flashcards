#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
	echo "uninstall.sh is macOS only." >&2
	exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
LA="$HOME/Library/LaunchAgents"
uid="$(id -u)"

for label in com.flashcard-qa.merge com.flashcard-qa.extract com.max.read-chat-gui.qa-merge com.max.read-chat-gui.qa-extract; do
	launchctl bootout "gui/${uid}/${label}" >/dev/null 2>&1 || true
	rm -f "$LA/${label}.plist"
	echo "Removed LaunchAgent: $label"
done

rm -rf "$ROOT/.venv"
echo "Removed: $ROOT/.venv"
echo "Uninstall done. Anki cards, chat logs, and Cursor skills were not deleted."
