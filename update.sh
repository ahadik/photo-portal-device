#!/bin/bash
# Pre-start update check for the Photo Portal GPIO service.
# Runs as systemd ExecStartPre. Best-effort: a failure here MUST NOT prevent
# the GPIO service from starting, so this script always exits 0.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 0

log() { echo "[photoportal-update] $*"; }

if ! command -v git &> /dev/null; then
    log "git not found, skipping update check"
    exit 0
fi

if [ ! -d "$SCRIPT_DIR/.git" ]; then
    log "not a git repository, skipping update check"
    exit 0
fi

log "checking for updates in $SCRIPT_DIR"

BEFORE_REQ_HASH=$(sha256sum requirements.txt 2>/dev/null | cut -d' ' -f1)

if ! git fetch --quiet origin; then
    log "git fetch failed (network/auth?), continuing with existing code"
    exit 0
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -z "$CURRENT_BRANCH" ] || [ "$CURRENT_BRANCH" = "HEAD" ]; then
    log "not on a branch (detached HEAD), skipping pull"
    exit 0
fi

LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse "origin/$CURRENT_BRANCH" 2>/dev/null)

if [ -z "$REMOTE" ]; then
    log "no upstream origin/$CURRENT_BRANCH, skipping"
    exit 0
fi

if [ "$LOCAL" = "$REMOTE" ]; then
    log "already up to date ($LOCAL)"
    exit 0
fi

log "new changes on origin/$CURRENT_BRANCH ($LOCAL -> $REMOTE), pulling"
if ! git pull --ff-only --quiet origin "$CURRENT_BRANCH"; then
    log "git pull failed (non-fast-forward or local changes?), continuing with existing code"
    exit 0
fi

AFTER_REQ_HASH=$(sha256sum requirements.txt 2>/dev/null | cut -d' ' -f1)
log "updated to $(git rev-parse HEAD)"

if [ "$BEFORE_REQ_HASH" != "$AFTER_REQ_HASH" ]; then
    log "requirements.txt changed, reinstalling dependencies"
    if [ -x "$SCRIPT_DIR/venv/bin/pip" ]; then
        "$SCRIPT_DIR/venv/bin/pip" install --quiet -r requirements.txt \
            && log "dependencies reinstalled" \
            || log "pip install failed, service may start with stale deps"
    else
        python3 -m pip install --quiet -r requirements.txt \
            && log "dependencies reinstalled" \
            || log "pip install failed, service may start with stale deps"
    fi
fi

exit 0
