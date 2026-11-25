#!/bin/bash
# Install (or update) the LaunchAgent that runs tools/daily-run.sh once a day.
#   bash tools/install-daily.sh            # daily at 07:17 local
#   bash tools/install-daily.sh 18 43      # daily at 18:43
# launchd, not cron: a run missed while the Mac sleeps happens on wake instead
# of being skipped. It still needs you logged in (it runs in your GUI session,
# which is also what lets it reach the Keychain and Chrome).
# Run now:    launchctl kickstart gui/$(id -u)/local.fly-connectome-daily
# Uninstall:  launchctl bootout gui/$(id -u)/local.fly-connectome-daily
#             rm ~/Library/LaunchAgents/local.fly-connectome-daily.plist
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="local.fly-connectome-daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HOUR="${1:-7}"; MIN="${2:-17}"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/fly-connectome"

cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$REPO/tools/daily-run.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer>
  </dict>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/fly-connectome/launchd.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/fly-connectome/launchd.log</string>
</dict></plist>
PL
plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" || {
  echo "bootstrap failed. Run this from Terminal.app in your own login session,"
  echo "not from a Claude Code shell (those run in launchd's Background session)."
  exit 1; }
printf 'installed %s: daily at %02d:%02d\n' "$LABEL" "$HOUR" "$MIN"

# Smoke test under launchd's own environment (PATH, Keychain, Chrome), via a
# throwaway agent so the real job's schedule is untouched. About a minute.
SL="local.fly-connectome-smoke"; SP="$HOME/Library/LaunchAgents/$SL.plist"
SLOG="$HOME/Library/Logs/fly-connectome/daily-$(date +%Y-%m-%d).log"
# grep -c prints nothing for a missing file and "0" once it exists, so normalise
# to a number; comparing "" to "0" ended the wait the moment the run started.
ends() { local n; n=$(grep -c "end, exit" "$SLOG" 2>/dev/null); echo "${n:-0}"; }
before=$(ends)
cat > "$SP" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$SL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$REPO/tools/daily-run.sh</string><string>--smoke</string>
  </array>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/fly-connectome/launchd.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/fly-connectome/launchd.log</string>
</dict></plist>
PL
launchctl bootstrap "gui/$(id -u)" "$SP" && launchctl kickstart "gui/$(id -u)/$SL"
echo "smoke test running under launchd (up to ~6 min)…"
# daily-run.sh may wait 20 s for Chrome, then its own watchdog stops claude at 300 s.
for _ in $(seq 1 72); do
  [ "$(ends)" -gt "$before" ] && break; sleep 5
done
launchctl bootout "gui/$(id -u)/$SL" 2>/dev/null || true; rm -f "$SP"
if tail -n 8 "$SLOG" 2>/dev/null | grep -q CHROME_OK; then
  echo "smoke test OK: claude runs under launchd and reaches Chrome."
else
  echo "smoke test FAILED. Last lines of $SLOG:"; tail -n 15 "$SLOG" 2>/dev/null
  tail -n 15 "$HOME/Library/Logs/fly-connectome/launchd.log" 2>/dev/null
  exit 1
fi
