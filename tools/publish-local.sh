#!/bin/bash
# Build, commit and push the site from RJ's Mac. Run from anywhere:
#   bash /Users/rj/personal/fly-connectome-videos/tools/publish-local.sh
# Used by the local Claude Code scheduled task (step 5 of TASK-PROMPT.md).
# Does NOT work inside a Cowork sandbox (git push is blocked there).
#
# - First run turns the folder into a git clone (from GitHub if main exists,
#   else from first-publish.bundle) without touching the working files.
# - Refuses to publish: invalid items.json, duplicate warnings from build.py,
#   fewer clusters than the last commit, or a remote that has moved on without us.
# - Pushes with the token file if present, else your normal git credentials (gh).
# - Enables GitHub Pages (main, /) if it is off.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$PWD"
REMOTE="https://github.com/honicky/fly-connectome-videos.git"
BRANCH="main"
OWNER_REPO="honicky/fly-connectome-videos"
TOKEN_FILE="$REPO/.fly-connectome-gh-token"
LOG="$REPO/publish.log"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$LOG"; }
die() { log "ERROR $*"; exit 1; }

g() {
  if [ -s "$TOKEN_FILE" ]; then
    git -c credential.helper= \
        -c credential.helper='!f(){ echo username=x-access-token; printf "password=%s\n" "$(tr -d "[:space:]" < "'"$TOKEN_FILE"'")"; };f' "$@"
  else
    git "$@"
  fi
}

command -v git >/dev/null || die "git not found"
command -v python3 >/dev/null || die "python3 not found"

# ---------------------------------------------------------------- one-time bootstrap
if [ ! -d .git ]; then
  git init -q -b "$BRANCH" && git remote add origin "$REMOTE" || die "git init failed"
  if g ls-remote --exit-code origin "refs/heads/$BRANCH" >/dev/null 2>&1; then
    g fetch -q origin "$BRANCH" && git reset -q "origin/$BRANCH" || die "could not adopt origin/$BRANCH"
    log "bootstrap: folder is now a clone of origin/$BRANCH (working files untouched)"
  elif [ -f first-publish.bundle ]; then
    git fetch -q first-publish.bundle "$BRANCH" && git reset -q FETCH_HEAD || die "could not adopt first-publish.bundle"
    log "bootstrap: folder adopted history from first-publish.bundle (GitHub $BRANCH is empty)"
  else
    log "bootstrap: fresh history (GitHub empty, no bundle)"
  fi
fi

# ---------------------------------------------------------------- remote check
if g fetch -q origin "$BRANCH" 2>/dev/null; then
  git merge-base --is-ancestor "origin/$BRANCH" HEAD 2>/dev/null \
    || die "origin/$BRANCH has commits this folder does not; not overwriting. Resolve by hand."
fi

# ---------------------------------------------------------------- build + guards
new_n=$(python3 -c 'import json;print(len(json.load(open("data/items.json"))["clusters"]))' 2>/dev/null) \
  || die "data/items.json is not valid JSON"
old_n=0
if git cat-file -e HEAD:data/items.json 2>/dev/null; then
  old_n=$(git show HEAD:data/items.json | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["clusters"]))' 2>/dev/null || echo 0)
fi
[ "$new_n" -ge "$old_n" ] || die "items.json has $new_n clusters, last commit has $old_n; refusing to shrink the site"

python3 -m unittest discover -s tests -q >/dev/null 2>&1 || die "unit tests failed (python3 -m unittest discover -s tests)"

# Resolve X/LinkedIn video for new posts into data/media.json. Never blocks a
# publish: without it those cards just fall back to text.
mout=$(python3 tools/fetch_media.py 2>&1) || log "WARN fetch_media.py failed: $(echo "$mout" | tail -n 1)"
echo "$mout" | tail -n 1

out=$(python3 build.py 2>&1); rc=$?
echo "$out" | tail -n 3
[ $rc -eq 0 ] || die "build.py failed (exit $rc)"
echo "$out" | grep -q "WARN duplicate" && die "build.py reported duplicates; fix data/items.json"

# ---------------------------------------------------------------- commit + push
git add -A
git diff --cached --name-only | grep -q 'gh-token' && die "token file staged; refusing to commit"
if ! git diff --cached --quiet; then
  name="$(git config user.name 2>/dev/null || true)"; email="$(git config user.email 2>/dev/null || true)"
  git -c user.name="${name:-fly-connectome publisher}" -c user.email="${email:-fly-publisher@users.noreply.github.com}" \
      commit -q -m "Publish $(date +%Y-%m-%d): $new_n entries" || die "commit failed"
fi
ahead=$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || git rev-list --count HEAD)
if [ "$ahead" != "0" ]; then
  perr=$(g push -q origin "HEAD:$BRANCH" 2>&1) || die "push failed: $(echo "$perr" | tr '\n' ' ')"
  g fetch -q origin "$BRANCH" 2>/dev/null
  log "OK pushed $ahead commit(s); site has $new_n entries"
else
  log "OK nothing new to publish; site has $new_n entries"
fi

# ---------------------------------------------------------------- Pages on?
pages() {  # $1 = GET|POST
  if [ -s "$TOKEN_FILE" ]; then
    curl -s -o /dev/null -w '%{http_code}' -X "$1" -H "Authorization: Bearer $(tr -d '[:space:]' < "$TOKEN_FILE")" \
      -H "Accept: application/vnd.github+json" "https://api.github.com/repos/$OWNER_REPO/pages" \
      ${2:+-d "$2"}
  elif command -v gh >/dev/null; then
    if [ "$1" = GET ]; then gh api "repos/$OWNER_REPO/pages" >/dev/null 2>&1 && echo 200 || echo 404
    else gh api -X POST "repos/$OWNER_REPO/pages" -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null 2>&1 && echo 201 || echo 000; fi
  else echo skip; fi
}
code=$(pages GET)
if [ "$code" = "404" ]; then
  rc=$(pages POST "{\"source\":{\"branch\":\"$BRANCH\",\"path\":\"/\"}}")
  case "$rc" in
    201|409) log "OK enabled GitHub Pages -> https://honicky.github.io/fly-connectome-videos/" ;;
    *) log "WARN could not enable GitHub Pages (HTTP $rc). Repo Settings > Pages > Deploy from a branch > main, / (root). Repo must be public on a free plan." ;;
  esac
fi
exit 0
