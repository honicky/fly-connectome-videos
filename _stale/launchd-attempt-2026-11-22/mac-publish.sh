#!/bin/bash
# Mac-side publisher for fly-connectome-videos.
#
# Runs as RJ in macOS (launchd, hourly), NOT in the Cowork sandbox. The daily
# Cowork task writes the built site into the connected folder; this script
# copies an allowlist of files into a real git clone and pushes to GitHub,
# because Cowork's sandbox blocks git push.
#
# Installed by tools/install-mac-publisher.sh, which COPIES this file out of
# the connected folder. The launchd job runs the copy, so the sandboxed task
# can never change what runs on the Mac. Re-run the installer to update it.
#
# Written for macOS's bash 3.2. Idempotent: exits quietly when nothing changed.
set -u

SRC="${FLY_SRC:-/Users/rj/personal/fly-connectome-videos}"
WORK="${FLY_PUBLISH_WORK:-$HOME/.fly-connectome-publish}"
REMOTE="${FLY_REMOTE_URL:-https://github.com/honicky/fly-connectome-videos.git}"
BRANCH="main"
OWNER_REPO="honicky/fly-connectome-videos"
TOKEN_FILE="$SRC/.fly-connectome-gh-token"
STATUS_LOG="$SRC/publish.log"      # readable by the Cowork task
LOCK="${TMPDIR:-/tmp}/fly-connectome-publish.lock"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  echo "$(ts) $*"
  echo "$(ts) $*" >> "$STATUS_LOG" 2>/dev/null
  # keep the status log short
  if [ -f "$STATUS_LOG" ] && [ "$(wc -l < "$STATUS_LOG")" -gt 300 ]; then
    tail -n 200 "$STATUS_LOG" > "$STATUS_LOG.tmp" && cat "$STATUS_LOG.tmp" > "$STATUS_LOG" && rm -f "$STATUS_LOG.tmp"
  fi
}
die() { log "ERROR $*"; exit 1; }

if ! mkdir "$LOCK" 2>/dev/null; then
  # stale lock (older than 30 min) is cleared; otherwise another run is active
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0
  else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

command -v git >/dev/null || die "git not on PATH ($PATH)"
command -v python3 >/dev/null || die "python3 not on PATH ($PATH)"
[ -f "$SRC/data/items.json" ] || die "no $SRC/data/items.json (folder missing or not synced?)"

# git with the token if the token file exists, else the Mac's normal git credentials (gh / keychain)
g() {
  if [ -s "$TOKEN_FILE" ]; then
    git -c credential.helper= \
        -c credential.helper='!f(){ echo username=x-access-token; printf "password=%s\n" "$(tr -d "[:space:]" < "'"$TOKEN_FILE"'")"; };f' "$@"
  else
    git "$@"
  fi
}

# ---------------------------------------------------------------- working clone
if [ ! -d "$WORK/.git" ]; then
  rm -rf "$WORK"
  if g ls-remote --exit-code "$REMOTE" "refs/heads/$BRANCH" >/dev/null 2>&1; then
    g clone --quiet --branch "$BRANCH" "$REMOTE" "$WORK" || die "clone of $REMOTE failed"
  elif [ -f "$SRC/first-publish.bundle" ]; then
    git clone --quiet --branch "$BRANCH" "$SRC/first-publish.bundle" "$WORK" || die "clone of first-publish.bundle failed"
    git -C "$WORK" remote set-url origin "$REMOTE"
    git -C "$WORK" update-ref -d "refs/remotes/origin/$BRANCH" 2>/dev/null   # bundle's ref is not GitHub's
    log "seeded working clone from first-publish.bundle (remote $BRANCH does not exist yet)"
  else
    mkdir -p "$WORK" && git -C "$WORK" init --quiet -b "$BRANCH" && git -C "$WORK" remote add origin "$REMOTE"
    log "remote empty and no bundle; starting a fresh history"
  fi
else
  git -C "$WORK" remote set-url origin "$REMOTE"
  if g -C "$WORK" fetch --quiet origin "$BRANCH" 2>/dev/null; then
    # the remote is the source of truth for history; local unpushed commits are kept
    # only if they sit on top of it (e.g. a previous push failed)
    if ! git -C "$WORK" merge-base --is-ancestor "origin/$BRANCH" HEAD 2>/dev/null; then
      git -C "$WORK" reset --quiet --hard "origin/$BRANCH"
    fi
  fi
fi

# ---------------------------------------------------------------- shrink guard
# Refuse to publish an items.json with fewer clusters than what is committed:
# a broken run must never wipe the site.
new_n=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["clusters"]))' "$SRC/data/items.json" 2>/dev/null) \
  || die "data/items.json in the folder is not valid JSON; not publishing"
old_n=0
if git -C "$WORK" cat-file -e HEAD:data/items.json 2>/dev/null; then
  old_n=$(git -C "$WORK" show HEAD:data/items.json | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["clusters"]))' 2>/dev/null || echo 0)
fi
[ "$new_n" -ge "$old_n" ] || die "folder has $new_n clusters but the published site has $old_n; refusing to shrink the site"

# ---------------------------------------------------------------- copy allowlist
mkdir -p "$WORK/data" "$WORK/tools"
for f in index.html build.py publish.sh COLLECTING.md README.md PIPELINE-BLOCKED.md .gitignore .nojekyll; do
  [ -f "$SRC/$f" ] && cp "$SRC/$f" "$WORK/$f"
done
for f in "$SRC"/data/*.json; do [ -f "$f" ] && cp "$f" "$WORK/data/"; done
for f in "$SRC"/tools/*.sh; do [ -f "$f" ] && cp "$f" "$WORK/tools/"; done

git -C "$WORK" add -A
if git -C "$WORK" ls-files | grep -q 'gh-token'; then die "a token file is staged; refusing to commit"; fi

if ! git -C "$WORK" diff --cached --quiet; then
  name="$(git config --global user.name 2>/dev/null || true)"; email="$(git config --global user.email 2>/dev/null || true)"
  git -C "$WORK" -c user.name="${name:-fly-connectome publisher}" -c user.email="${email:-fly-publisher@users.noreply.github.com}" \
      commit --quiet -m "Publish $(date +%Y-%m-%d): $new_n entries" || die "commit failed"
fi

# ---------------------------------------------------------------- push (also retries earlier failed pushes)
ahead=$(git -C "$WORK" rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || git -C "$WORK" rev-list --count HEAD)
if [ "$ahead" != "0" ]; then
  out=$(g -C "$WORK" push --quiet origin "HEAD:$BRANCH" 2>&1) || die "push failed: $(echo "$out" | tr '\n' ' ' | sed 's/x-access-token:[^@]*@/x-access-token:***@/g')"
  g -C "$WORK" fetch --quiet origin "$BRANCH" 2>/dev/null
  log "OK pushed $ahead commit(s); site has $new_n entries"
fi

# ---------------------------------------------------------------- make sure Pages is on
if [ -s "$TOKEN_FILE" ]; then
  tok="$(tr -d '[:space:]' < "$TOKEN_FILE")"
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $tok" -H "Accept: application/vnd.github+json" \
         "https://api.github.com/repos/$OWNER_REPO/pages")
  if [ "$code" = "404" ]; then
    resp=$(curl -s -w '\n%{http_code}' -X POST -H "Authorization: Bearer $tok" -H "Accept: application/vnd.github+json" \
           "https://api.github.com/repos/$OWNER_REPO/pages" -d "{\"source\":{\"branch\":\"$BRANCH\",\"path\":\"/\"}}")
    rc=$(echo "$resp" | tail -n1)
    case "$rc" in
      201|409) log "OK enabled GitHub Pages on $BRANCH (/) -- https://honicky.github.io/fly-connectome-videos/" ;;
      *) log "WARN could not enable GitHub Pages automatically (HTTP $rc): $(echo "$resp" | head -n1 | cut -c1-200). Enable it once in repo Settings > Pages > Deploy from a branch > main, / (root)." ;;
    esac
  fi
elif command -v gh >/dev/null && ! gh api "repos/$OWNER_REPO/pages" >/dev/null 2>&1; then
  if gh api -X POST "repos/$OWNER_REPO/pages" -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null 2>&1; then
    log "OK enabled GitHub Pages on $BRANCH (/)"
  else
    log "WARN could not enable GitHub Pages automatically; enable it in repo Settings > Pages"
  fi
fi
exit 0
