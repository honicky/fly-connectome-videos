#!/usr/bin/env bash
# Rebuild index.html and push to GitHub Pages.
#
# Usage:
#   ./publish.sh pull     clone GitHub -> $FLY_WORK (default $HOME/fly-work)
#   ./publish.sh push     build, commit, push, mirror index.html+items.json back
#   ./publish.sh          legacy in-place build+commit+push (works on RJ's real Mac,
#                         where git is not sandboxed; fails inside the task sandbox)
#
# Why pull/push exist: git cannot run inside the connected folder. The sandbox
# blocks file deletion there, so git's lock files survive and every commit after
# the first dies with "cannot lock ref 'HEAD': File exists". All git work happens
# in VM scratch space instead; GitHub is the source of truth.
#
# Token is read from a file OUTSIDE git and never written to git config, the
# remote URL, or the reflog.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_URL="${FLY_REMOTE_URL:-https://github.com/honicky/fly-connectome-videos.git}"
BRANCH="${FLY_BRANCH:-main}"
WORK="${FLY_WORK:-$HOME/fly-work}"

# Files mirrored from the working clone back into the connected folder.
# DELIBERATELY NARROW. The connected folder holds data/pending-merge.json, which
# is the only copy of the unpublished backlog and is in no git history yet. A
# wholesale mirror of a clone of an empty repo would destroy it in one run.
MIRROR_FILES=("index.html" "data/items.json")

# ---------------------------------------------------------------- locate mount
# The connected folder: where the token and the mirror live. When this script
# runs from the clone, SELF_DIR is the clone, so fall back to discovery.
find_mount() {
  if [ -f "$SELF_DIR/COLLECTING.md" ] && [ ! -d "$SELF_DIR/.git" ]; then
    echo "$SELF_DIR"; return 0
  fi
  if [ -f "$WORK/.git/fly-origin" ]; then
    local m; m="$(cat "$WORK/.git/fly-origin")"
    if [ -d "$m" ]; then echo "$m"; return 0; fi
  fi
  local c
  for c in "$HOME"/mnt/*/COLLECTING.md; do
    [ -f "$c" ] && { dirname "$c"; return 0; }
  done
  return 1
}
MOUNT_DIR="$(find_mount || true)"

# ---------------------------------------------------------------- locate token
resolve_token_file() {
  local tried=() p
  if [ -n "${FLY_TOKEN_FILE:-}" ]; then
    [ -f "$FLY_TOKEN_FILE" ] && { echo "$FLY_TOKEN_FILE"; return 0; }
    tried+=("$FLY_TOKEN_FILE")
  fi
  # Preferred: inside the connected folder (already covered by .gitignore), so
  # it is reachable from the sandbox.
  for p in "${MOUNT_DIR:+$MOUNT_DIR/.fly-connectome-gh-token}" \
           "$SELF_DIR/.fly-connectome-gh-token" \
           "${MOUNT_DIR:+$(dirname "${MOUNT_DIR:-/}")/.fly-connectome-gh-token}"; do
    [ -n "$p" ] || continue
    [ -f "$p" ] && { echo "$p"; return 0; }
    tried+=("$p")
  done
  printf 'ERROR: no GitHub token found. Tried:\n' >&2
  printf '  %s\n' "${tried[@]}" | sort -u >&2
  cat >&2 <<'MSG'
Create a fine-grained PAT (Contents + Pages: read/write on this repo) and save it
in the connected folder itself:
  /Users/rj/personal/fly-connectome-videos/.fly-connectome-gh-token
That path is already in .gitignore and, unlike the parent directory, is reachable
from the task sandbox.
MSG
  return 1
}

read_token() {
  local tf; tf="$(resolve_token_file)" || return 1
  local t; t="$(tr -d '[:space:]' < "$tf")"
  if [ -z "$t" ]; then echo "ERROR: token file $tf is empty" >&2; return 1; fi
  printf '%s' "$t"
}

git_authed() {
  local token="$1"; shift
  GH_TOKEN="$token" git \
    -c credential.helper= \
    -c credential.helper='!f(){ echo username=x-access-token; echo "password=${GH_TOKEN}"; };f' \
    "$@"
}

# ------------------------------------------------------------------ seeding
# Copy the connected folder into the working clone so the FIRST push puts the
# unpublished backlog into git history. Excludes:
#   .git / __pycache__        - build noise
#   _stale/git-abandoned      - the dead 09-15 repo, 50 files of git internals
#   .fly-connectome-gh-token  - never copy a credential into scratch space
#                               (.gitignore also covers it; belt and braces)
seed_from_mount() {
  ( cd "$MOUNT_DIR" && tar \
      --exclude='.git' \
      --exclude='__pycache__' \
      --exclude='_stale/git-abandoned' \
      --exclude='.fly-connectome-gh-token' \
      -cf - . ) | ( cd "$WORK" && tar -xf - )
}

# ----------------------------------------------------------------------- pull
cmd_pull() {
  local token; token="$(read_token)" || exit 1
  [ -n "$MOUNT_DIR" ] || { echo "ERROR: cannot locate the connected folder" >&2; exit 1; }

  if [ -d "$WORK/.git" ]; then
    echo "working copy exists at $WORK; fetching"
    git -C "$WORK" remote set-url origin "$REMOTE_URL"
    if git_authed "$token" -C "$WORK" fetch --quiet origin "$BRANCH" 2>/dev/null; then
      git -C "$WORK" reset --hard "origin/$BRANCH" --quiet
      echo "updated $WORK to origin/$BRANCH"
    else
      echo "NOTE: origin/$BRANCH not fetchable (empty or new repo); keeping local state"
    fi
    printf '%s' "$MOUNT_DIR" > "$WORK/.git/fly-origin"
    return 0
  fi

  rm -rf "$WORK"
  if git_authed "$token" clone --quiet --branch "$BRANCH" "$REMOTE_URL" "$WORK" 2>/dev/null; then
    echo "cloned $REMOTE_URL -> $WORK"
  elif git_authed "$token" clone --quiet "$REMOTE_URL" "$WORK" 2>/dev/null; then
    echo "cloned $REMOTE_URL -> $WORK (default branch; will push to $BRANCH)"
  else
    # Distinguish "repo is empty / has no $BRANCH yet" from "cannot authenticate".
    local probe rc
    set +e
    probe="$(git_authed "$token" ls-remote "$REMOTE_URL" 2>&1)"; rc=$?
    set -e
    if [ $rc -ne 0 ]; then
      echo "ERROR: cannot reach $REMOTE_URL with this token." >&2
      echo "$probe" | sed 's/^/  /' >&2
      echo "Create the repo on GitHub and give the PAT Contents+Pages read/write on it." >&2
      exit 1
    fi
    echo "repo is reachable but empty; seeding $WORK from the connected folder"
    mkdir -p "$WORK"
    # Seed EVERYTHING so the first push puts the backlog into git history.
    seed_from_mount
    git -C "$WORK" init --quiet -b "$BRANCH"
    git -C "$WORK" remote add origin "$REMOTE_URL"
  fi

  git -C "$WORK" symbolic-ref -q HEAD >/dev/null 2>&1 || true
  printf '%s' "$MOUNT_DIR" > "$WORK/.git/fly-origin"

  # A clone of an empty repo has no files: seed it, or the first push would
  # commit nothing and mirror-back would have nothing to copy.
  if [ ! -f "$WORK/build.py" ]; then
    echo "clone has no build.py; seeding from the connected folder"
    seed_from_mount
  fi
  echo "ready: $WORK"
}

# ----------------------------------------------------------------------- push
cmd_push() {
  local token; token="$(read_token)" || exit 1
  [ -d "$WORK/.git" ] || { echo "ERROR: no working copy at $WORK; run './publish.sh pull' first" >&2; exit 1; }
  cd "$WORK"

  python3 build.py

  local dups
  dups="$(python3 build.py 2>&1 | grep -c 'WARN duplicate' || true)"
  if [ "${dups:-0}" -gt 0 ]; then
    echo "ERROR: build reports $dups duplicate warnings; fix data/items.json before publishing" >&2
    exit 1
  fi

  if [ -z "$(git status --porcelain)" ]; then
    echo "nothing changed; not pushing"
  else
    local count
    count="$(python3 -c "import json;print(len(json.load(open('data/items.json'))['clusters']))")"
    git add -A
    git -c user.name="fly-connectome-bot" -c user.email="rj@honicky.ai" \
      commit -q -m "Daily update $(date -u +%Y-%m-%d): ${count} entries"
    git_authed "$token" push --quiet "$REMOTE_URL" "HEAD:${BRANCH}"
    echo "pushed ${count} entries to ${BRANCH}"
  fi

  # ------------------------------------------------- mirror back (narrow, additive)
  if [ -n "$MOUNT_DIR" ] && [ -d "$MOUNT_DIR" ]; then
    local f
    for f in "${MIRROR_FILES[@]}"; do
      if [ -f "$WORK/$f" ]; then
        mkdir -p "$MOUNT_DIR/$(dirname "$f")"
        # plain cp truncates in place: no unlink, so it works where the sandbox
        # blocks deletion. Never use --remove-destination here.
        cp "$WORK/$f" "$MOUNT_DIR/$f"
        echo "mirrored $f -> connected folder"
      fi
    done
  else
    echo "NOTE: connected folder not found; skipped mirror-back"
  fi
}

# --------------------------------------------------------------------- legacy
cmd_legacy() {
  local token; token="$(read_token)" || exit 1
  cd "$SELF_DIR"
  [ -d .git ] || { cat >&2 <<'MSG'
ERROR: no .git here, so there is nothing to commit in place.
Inside the task sandbox git cannot run in the connected folder at all; use:
  ./publish.sh pull   then   $HOME/fly-work/publish.sh push
MSG
    exit 1; }
  python3 build.py
  if [ -z "$(git status --porcelain)" ]; then echo "nothing changed; not pushing"; exit 0; fi
  local count
  count="$(python3 -c "import json;print(len(json.load(open('data/items.json'))['clusters']))")"
  git add -A
  git -c user.name="fly-connectome-bot" -c user.email="rj@honicky.ai" \
    commit -q -m "Daily update $(date -u +%Y-%m-%d): ${count} entries"
  git_authed "$token" push "$REMOTE_URL" "HEAD:${BRANCH}"
  echo "pushed ${count} entries to ${BRANCH}"
}

case "${1:-}" in
  pull) cmd_pull ;;
  push) cmd_push ;;
  "")   cmd_legacy ;;
  -h|--help|help)
        sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *)    echo "unknown command: $1 (expected 'pull', 'push', or no argument)" >&2; exit 2 ;;
esac
