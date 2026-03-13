#!/usr/bin/env bash
# =============================================================================
#  watch-skills.sh  –  File-watcher that auto-triggers redteam on new skills
#
#  Watches the SKILLS_ROOT directory for:
#    • New SKILL.md files created (new skill added)
#    • Existing SKILL.md files modified (skill updated)
#
#  Works on:
#    macOS  – uses fswatch  (brew install fswatch)
#    Linux  – uses inotifywait  (apt install inotify-tools)
#    Both   – falls back to a 30-second polling loop if neither is available
#
#  Usage:
#    ./watch-skills.sh
#    ./watch-skills.sh --poll-interval 60
#
#  Env vars:
#    SKILLS_ROOT      path to skills dir
#    COOLDOWN_SECS    seconds to debounce rapid changes (default: 10)
#    RUN_SCRIPT       path to run-redteam.sh (default: auto-detected)
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
SKILLS_ROOT="${SKILLS_ROOT:-$HOME/.skills/skills}"
COOLDOWN_SECS="${COOLDOWN_SECS:-10}"
RUN_SCRIPT="${RUN_SCRIPT:-$SCRIPT_DIR/run-redteam.sh}"
POLL_INTERVAL=30

while [[ $# -gt 0 ]]; do
  case "$1" in
    --poll-interval)
      if [[ $# -lt 2 ]]; then
        echo "[ERROR] --poll-interval requires a value."
        exit 1
      fi
      POLL_INTERVAL="$2"
      shift 2
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      echo "Usage: ./watch-skills.sh [--poll-interval SECONDS]"
      exit 1
      ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "$(date '+%H:%M:%S')  ${CYAN}[WATCH]${RESET}  $*"; }
ok()   { echo -e "$(date '+%H:%M:%S')  ${GREEN}[OK]${RESET}     $*"; }
warn() { echo -e "$(date '+%H:%M:%S')  ${YELLOW}[WARN]${RESET}   $*"; }

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ ! -d "$SKILLS_ROOT" ]]; then
  echo "[ERROR] Skills root not found: $SKILLS_ROOT"
  exit 1
fi
if [[ ! -f "$RUN_SCRIPT" ]]; then
  echo "[ERROR] run-redteam.sh not found: $RUN_SCRIPT"
  exit 1
fi
chmod +x "$RUN_SCRIPT"

# ── Snapshot helper (for polling) ─────────────────────────────────────────────
snapshot_skills() {
  find "$SKILLS_ROOT" -name "SKILL.md" -exec stat -c '%Y %n' {} \; 2>/dev/null \
    || find "$SKILLS_ROOT" -name "SKILL.md" -exec stat -f '%m %N' {} \; 2>/dev/null \
    || find "$SKILLS_ROOT" -name "SKILL.md" | sort
}

# ── Trigger redteam (with cooldown debounce) ──────────────────────────────────
LAST_RUN=0
trigger_redteam() {
  local changed_file="${1:-unknown}"
  local now
  now=$(date +%s)
  local since=$(( now - LAST_RUN ))

  if (( since < COOLDOWN_SECS )); then
    warn "Change detected in $changed_file – cooldown active (${since}s < ${COOLDOWN_SECS}s), skipping."
    return
  fi

  LAST_RUN=$now
  log "Change detected: ${BOLD}$changed_file${RESET}"
  log "Triggering redteam run..."
  echo ""

  SKILLS_ROOT="$SKILLS_ROOT" bash "$RUN_SCRIPT" && \
    ok "Redteam run completed." || \
    warn "Redteam run finished with non-zero exit (check results)."
  echo ""
}

# ── macOS fswatch mode ────────────────────────────────────────────────────────
run_fswatch() {
  log "Using ${BOLD}fswatch${RESET} (macOS)"
  log "Watching: ${CYAN}$SKILLS_ROOT${RESET}"
  log "Press Ctrl-C to stop.\n"

  fswatch -0 --event Created --event Updated --event Renamed \
    --include "SKILL\\.md$" --recursive "$SKILLS_ROOT" | \
  while IFS= read -r -d '' changed_file; do
    trigger_redteam "$changed_file"
  done
}

# ── Linux inotifywait mode ────────────────────────────────────────────────────
run_inotify() {
  log "Using ${BOLD}inotifywait${RESET} (Linux)"
  log "Watching: ${CYAN}$SKILLS_ROOT${RESET}"
  log "Press Ctrl-C to stop.\n"

  inotifywait --monitor --recursive \
    --event create --event modify --event moved_to \
    --include "SKILL\\.md$" \
    --format "%w%f" \
    "$SKILLS_ROOT" | \
  while read -r changed_file; do
    trigger_redteam "$changed_file"
  done
}

# ── Polling fallback ──────────────────────────────────────────────────────────
run_polling() {
  local interval="${POLL_INTERVAL:-30}"
  warn "Neither fswatch nor inotifywait found. Falling back to ${BOLD}polling every ${interval}s${RESET}."
  log  "Watching: ${CYAN}$SKILLS_ROOT${RESET}"
  log  "Press Ctrl-C to stop.\n"

  local prev_snapshot
  prev_snapshot="$(snapshot_skills)"

  while true; do
    sleep "$interval"
    local curr_snapshot
    curr_snapshot="$(snapshot_skills)"

    if [[ "$curr_snapshot" != "$prev_snapshot" ]]; then
      # Find what changed
      local changed
      changed="$(diff <(echo "$prev_snapshot") <(echo "$curr_snapshot") | grep '^>' | head -3 | awk '{print $NF}' || echo "unknown")"
      prev_snapshot="$curr_snapshot"
      trigger_redteam "$changed"
    else
      log "No changes detected (${#prev_snapshot} bytes snapshot). Next check in ${interval}s..."
    fi
  done
}

# ── Main: pick watcher ────────────────────────────────────────────────────────
echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e " ${BOLD}Skills Watcher  ·  Auto-trigger redteam on skill changes${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"

if command -v fswatch &>/dev/null; then
  run_fswatch
elif command -v inotifywait &>/dev/null; then
  run_inotify
else
  run_polling
fi
