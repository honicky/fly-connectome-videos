#!/bin/bash
# One-time install of the Mac-side publisher (run in Terminal on the Mac, not in Cowork).
#   bash /Users/rj/personal/fly-connectome-videos/tools/install-mac-publisher.sh
# Safe to re-run: it updates the installed copy and reloads the job.
# Uninstall:
#   launchctl bootout gui/$(id -u)/local.fly-connectome-publish; rm ~/Library/LaunchAgents/local.fly-connectome-publish.plist
set -euo pipefail
SRC="/Users/rj/personal/fly-connectome-videos"
LABEL="local.fly-connectome-publish"
BIN_DIR="$HOME/Library/Application Support/fly-connectome-publish"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGF="$HOME/Library/Logs/fly-connectome-publish.log"

for c in git python3 curl; do command -v "$c" >/dev/null || { echo "missing: $c"; exit 1; }; done

mkdir -p "$BIN_DIR" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
# Copy, don't link: the sandboxed Cowork task can edit files in $SRC, and it must
# not be able to change code that runs on the Mac with your GitHub credentials.
cp "$SRC/tools/mac-publish.sh" "$BIN_DIR/mac-publish.sh"
chmod 700 "$BIN_DIR/mac-publish.sh"

cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$BIN_DIR/mac-publish.sh</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$PATH</string>
    <key>FLY_SRC</key><string>$SRC</string>
  </dict>
  <key>StartInterval</key><integer>3600</integer>
  <key>StandardOutPath</key><string>$LOGF</string>
  <key>StandardErrorPath</key><string>$LOGF</string>
</dict></plist>
PL
plutil -lint "$PLIST" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed: runs hourly; log at $LOGF and $SRC/publish.log"
echo "first run now:"
FLY_SRC="$SRC" /bin/bash "$BIN_DIR/mac-publish.sh"
