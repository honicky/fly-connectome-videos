#!/bin/bash
# Daily unattended run of TASK-PROMPT.md via headless Claude Code, started by
# the LaunchAgent that tools/install-daily.sh installs. Run by hand any time:
#   bash tools/daily-run.sh            # full run: collect, merge, publish
#   bash tools/daily-run.sh --smoke    # 1-minute check that claude + Chrome work
#
# Log: ~/Library/Logs/fly-connectome/daily-YYYY-MM-DD.log (kept outside the repo,
# because publish-local.sh commits everything not in .gitignore).
#
# Permissions: --permission-mode dontAsk with an allowlist, so nothing ever waits
# for a human. Anything not on the list is denied and the run works around it or
# reports it. Note python3 is allowed, which is effectively arbitrary code: the
# allowlist stops accidents (rm, git push --force), not a determined prompt
# injection from scraped post text.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$PWD"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
CLAUDE="$(command -v claude)" || { echo "claude not on PATH"; exit 1; }
LOGDIR="$HOME/Library/Logs/fly-connectome"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/daily-$(date +%Y-%m-%d).log"
LOCK="$LOGDIR/.run.lock"
MAX_SECONDS=5400   # kill a run that hangs (stuck browser, stalled tool) after 90 min

notify() { osascript -e "display notification \"$1\" with title \"Fly connectome\"" >/dev/null 2>&1 || true; }

if ! mkdir "$LOCK" 2>/dev/null; then
  # A lock older than MAX_SECONDS is left over from a crash: take it over.
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +$((MAX_SECONDS / 60 + 5)) 2>/dev/null)" ]; then
    rm -rf "$LOCK"; mkdir "$LOCK"
  else
    echo "$(date) another run is in progress; exiting" >> "$LOG"; exit 0
  fi
fi
trap 'rm -rf "$LOCK"' EXIT

ALLOWED="Read,Edit,Write,Glob,Grep,ToolSearch,WebSearch,mcp__claude-in-chrome"
for c in "python3" "bash tools/publish-local.sh" "tail" "head" "cat" "ls" "grep" "wc" "date" \
         "mkdir" "cd" "echo" "sed" "sort" "uniq" "jq" "git status" "git log" "git diff" "git show"; do
  ALLOWED="$ALLOWED,Bash($c:*)"
done

if [ "${1:-}" = "--smoke" ]; then
  PROMPT="Smoke test, do nothing else: load the Claude in Chrome tools with ToolSearch, call mcp__claude-in-chrome__tabs_context_mcp with createIfEmpty=false, and reply with one line: CHROME_OK or CHROME_FAIL <error>."
  MAX_SECONDS=300
else
  PROMPT="Run TASK-PROMPT.md in this folder exactly as written. This is an unattended scheduled run: nobody will answer questions, and any tool not pre-approved is denied, so work around a denial or report it."
fi

# Chrome must be running for the extension to connect; start it in the background if not.
if ! pgrep -xq "Google Chrome"; then
  open -ga "Google Chrome" && sleep 20
fi

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') start ${1:-full} ($("$CLAUDE" --version 2>/dev/null))"
  # caffeinate -i: no idle sleep mid-run. Watchdog kills a hung run.
  caffeinate -i "$CLAUDE" -p "$PROMPT" --chrome --permission-mode dontAsk \
      --allowedTools "$ALLOWED" --add-dir /tmp < /dev/null &
  pid=$!
  ( sleep "$MAX_SECONDS"; kill -TERM "$pid" 2>/dev/null && echo "WATCHDOG: killed after ${MAX_SECONDS}s" ) &
  wd=$!
  wait "$pid"; rc=$?
  kill "$wd" 2>/dev/null; wait "$wd" 2>/dev/null
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') end, exit $rc"
  echo "publish.log tail:"; tail -n 3 "$REPO/publish.log" 2>/dev/null
  exit $rc
} >> "$LOG" 2>&1
rc=$?

if [ "${1:-}" = "--smoke" ]; then
  grep -q CHROME_OK "$LOG" && notify "Smoke test OK" || notify "Smoke test FAILED, see $LOG"
elif [ $rc -ne 0 ] || tail -n 3 "$REPO/publish.log" 2>/dev/null | grep -q "^.*ERROR"; then
  notify "Daily run had problems (exit $rc). See $LOG"
else
  notify "Daily run finished. $(tail -n 1 "$REPO/publish.log" 2>/dev/null | cut -c22-90)"
fi
find "$LOGDIR" -name 'daily-*.log' -mtime +45 -delete 2>/dev/null
exit $rc
