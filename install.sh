#!/usr/bin/env bash
set -euo pipefail

# macOS. Edit PYTHON3 if needed, then re-run.
PYTHON3="/usr/bin/python3"

if [[ "$(uname -s)" != "Darwin" ]]; then
	echo "install.sh is macOS only." >&2
	exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON3:-$(command -v python3)}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
	echo "PYTHON3 must be an executable python3." >&2
	exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
	cp "$ROOT/.env.example" "$ROOT/.env"
	echo "Created $ROOT/.env — put OPENROUTER_API_KEY in it."
fi

echo "== venv + deps =="
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
	"$PY" -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install -U pip
"$ROOT/.venv/bin/pip" install -r "$ROOT/qa/requirements-apy.txt"
VENV_PY="$ROOT/.venv/bin/python"

LOG_ROOT="$("$VENV_PY" "$ROOT/qa/read_settings.py" log_root)"
GIT_REPO="$("$VENV_PY" "$ROOT/qa/read_settings.py" git_repo)"
DATA_REPO="$("$VENV_PY" "$ROOT/qa/read_settings.py" data_repo)"
EXPORT_DIR="$("$VENV_PY" "$ROOT/qa/read_settings.py" export_dir)"
MERGE_HOUR="$("$VENV_PY" "$ROOT/qa/read_settings.py" merge_hour)"
MERGE_MINUTE="$("$VENV_PY" "$ROOT/qa/read_settings.py" merge_minute)"
EXTRACT_POLL="$("$VENV_PY" "$ROOT/qa/read_settings.py" extract_poll_seconds)"
EXTRACT_PLIST="$("$VENV_PY" "$ROOT/qa/read_settings.py" extract_plist)"

mkdir -p "$LOG_ROOT" "$EXPORT_DIR"

if [[ -n "$DATA_REPO" && -n "$GIT_REPO" ]]; then
	echo "== cards git repo =="
	bash "$ROOT/qa/setup_data_repo.sh" "$DATA_REPO" "$GIT_REPO"
fi

echo "== Cursor skills =="
SKILLS_DEST="$HOME/.cursor/skills"
mkdir -p "$SKILLS_DEST" "$HOME/.cursor/rules" "$HOME/.cursor/flashcard-qa"
for d in "$ROOT/skills"/*; do
	[[ -d "$d" ]] || continue
	name="$(basename "$d")"
	rm -rf "$SKILLS_DEST/$name"
	cp -R "$d" "$SKILLS_DEST/$name"
done
cp "$ROOT/rules/flashcard-qa.mdc" "$HOME/.cursor/rules/flashcard-qa.mdc"
printf "%s\n" "$EXPORT_DIR" > "$HOME/.cursor/flashcard-qa/EXPORT_DIR"
printf "%s\n" "$EXPORT_DIR" > "$SKILLS_DEST/flashcard-qa-json-export/EXPORT_DIR"
printf "%s\n" "$EXPORT_DIR" > "$ROOT/EXPORT_DIR"

echo "== Hammerspoon flashcard shortcuts =="
HS="$HOME/.hammerspoon"
mkdir -p "$HS"
cp "$ROOT/hammerspoon/flashcard.lua" "$HS/flashcard.lua"
if [[ ! -f "$HS/init.lua" ]]; then
	printf '%s\n' 'dofile(hs.configdir .. "/flashcard.lua")' > "$HS/init.lua"
elif ! grep -q 'flashcard.lua' "$HS/init.lua"; then
	printf '\n%s\n' 'dofile(hs.configdir .. "/flashcard.lua")' >> "$HS/init.lua"
fi
if command -v hs >/dev/null 2>&1; then
	hs -c 'hs.reload()' >/dev/null 2>&1 || true
fi

echo "== point read_chat_gui log_root at this pipeline =="
for cand in "${READ_CHAT_GUI_DIR:-}" "$HOME/read_chat_gui" "$ROOT/../read_chat_gui"; do
	[[ -n "$cand" && -f "$cand/settings.yaml" ]] || continue
	"$VENV_PY" - "$cand/settings.yaml" "$LOG_ROOT" <<'PY'
import sys
from pathlib import Path
path, log_root = Path(sys.argv[1]), sys.argv[2]
text = path.read_text(encoding="utf-8")
out = []
done = False
for line in text.splitlines(True):
    if line.lstrip().startswith("log_root:") and not done:
        nl = "\n" if line.endswith("\n") else ""
        out.append(f"log_root: {log_root}{nl}")
        done = True
    else:
        out.append(line)
if not done:
    out.append(f"\nlog_root: {log_root}\n")
path.write_text("".join(out), encoding="utf-8")
print(f"set {path} log_root={log_root}")
PY
	break
done

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
STD_LOG="$HOME/Library/Logs/flashcard-qa"
PATH_LAUNCHD="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LABEL_MERGE="com.flashcard-qa.merge"
LABEL_EXTRACT="com.flashcard-qa.extract"
uid="$(id -u)"
mkdir -p "$LAUNCH_AGENTS" "$STD_LOG"

for old in com.max.read-chat-gui.qa-merge com.max.read-chat-gui.qa-extract "$LABEL_MERGE" "$LABEL_EXTRACT"; do
	launchctl bootout "gui/${uid}/${old}" >/dev/null 2>&1 || true
	rm -f "$LAUNCH_AGENTS/${old}.plist"
done

PLIST_MERGE="$LAUNCH_AGENTS/${LABEL_MERGE}.plist"
cat >"$PLIST_MERGE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL_MERGE}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_PY}</string>
    <string>${ROOT}/qa/merge.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${PATH_LAUNCHD}</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>${ROOT}/qa</string>
  <key>RunAtLoad</key>
  <false/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${MERGE_HOUR}</integer>
    <key>Minute</key>
    <integer>${MERGE_MINUTE}</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${STD_LOG}/qa-merge.out.log</string>
  <key>StandardErrorPath</key>
  <string>${STD_LOG}/qa-merge.err.log</string>
</dict>
</plist>
EOF

PLIST_EXTRACT="$LAUNCH_AGENTS/${LABEL_EXTRACT}.plist"
cat >"$PLIST_EXTRACT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL_EXTRACT}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_PY}</string>
    <string>${ROOT}/qa/extract_todo_launcher.py</string>
    <string>--root</string>
    <string>${LOG_ROOT}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${PATH_LAUNCHD}</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>${ROOT}/qa</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>${EXTRACT_POLL}</integer>
  <key>StartCalendarInterval</key>
  <array>
${EXTRACT_PLIST}
  </array>
  <key>StandardOutPath</key>
  <string>${STD_LOG}/qa-extract.out.log</string>
  <key>StandardErrorPath</key>
  <string>${STD_LOG}/qa-extract.err.log</string>
</dict>
</plist>
EOF

chmod 644 "$PLIST_MERGE" "$PLIST_EXTRACT"
launchctl bootstrap "gui/${uid}" "$PLIST_MERGE"
launchctl enable "gui/${uid}/${LABEL_MERGE}"
launchctl bootstrap "gui/${uid}" "$PLIST_EXTRACT"
launchctl enable "gui/${uid}/${LABEL_EXTRACT}"

echo ""
echo "Install finished."
echo "settings: $ROOT/settings.yaml"
echo "secret:   $ROOT/.env"
echo "chats:    $LOG_ROOT"
echo "export:   $EXPORT_DIR"
echo "merge:    ${MERGE_HOUR}:$(printf '%02d' "$MERGE_MINUTE") local"
echo "Re-run ./install.sh after editing settings.yaml."
echo "Test merge: $VENV_PY $ROOT/qa/merge.py"
echo "Logs: $STD_LOG"
