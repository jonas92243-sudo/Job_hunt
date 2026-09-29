#!/usr/bin/env bash
# Scans on every :00 and :30 for a little over five hours, then exits so the
# workflow can start its own replacement (GitHub stops any job after six hours).
set -u

INTERVAL=1800                          # seconds between scans
RUN_SECONDS=$(( 5 * 3600 + 10 * 60 ))  # how long one run keeps going
RECENT=900                             # a scan this fresh makes the first one wait
REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"

# The list of already-seen jobs lives on its own "state" branch, holding a single
# commit that is replaced after every scan. Prints the time of the last save.
restore_state() {
  mkdir -p state
  local code
  git ls-remote --exit-code --heads origin state > /dev/null
  code=$?
  if [ "$code" -eq 2 ]; then
    echo "No saved state yet: this is the first scan." >&2
    echo 0
    return 0
  fi
  [ "$code" -eq 0 ] || return 1
  git fetch --quiet --depth=1 origin state || return 1
  git show FETCH_HEAD:seen.json > state/seen.json.new || return 1
  mv state/seen.json.new state/seen.json
  git log -1 --format=%ct FETCH_HEAD
}

save_state() {
  [ -s state/seen.json ] || return 0
  local work
  work="$(mktemp -d)"
  cp state/seen.json "$work/seen.json"
  (
    cd "$work" || exit 1
    git init --quiet --initial-branch=state
    git config user.name "job-scanner"
    git config user.email "job-scanner@users.noreply.github.com"
    git add seen.json
    git commit --quiet -m "Scan state"
    git push --quiet --force "$REMOTE" state
  )
  local code=$?
  rm -rf "$work"
  return "$code"
}

# Pick up changes to the company list and settings without restarting.
update_code() {
  git fetch --quiet --depth=1 origin main && git reset --quiet --hard FETCH_HEAD \
    || echo "Could not fetch the latest code; scanning with the current copy."
}

# Sleeps until the next :00 or :30. Fails when that would pass the deadline.
wait_for_next_slot() {
  local now next
  now=$(date +%s)
  next=$(( (now / INTERVAL + 1) * INTERVAL ))
  [ "$next" -lt "$deadline" ] || return 1
  echo "Next scan at $(date -u -d "@$next" +%H:%M) UTC."
  sleep $(( next - now ))
}

main() {
  deadline=$(( $(date +%s) + RUN_SECONDS ))

  local last_saved="" attempt
  for attempt in 1 2 3; do
    last_saved=$(restore_state) && break
    last_saved=""
    echo "Could not restore the scan state (attempt $attempt)."
    sleep 60
  done
  if [ -z "$last_saved" ]; then
    # Scanning without the saved state would repeat every old alert.
    echo "Giving up: the scan state is unreachable."
    exit 1
  fi

  if [ $(( $(date +%s) - last_saved )) -lt "$RECENT" ]; then
    echo "The last scan was only minutes ago."
    wait_for_next_slot || exit 0
  fi

  while true; do
    update_code
    python3 -m scanner || echo "The scan reported a problem; carrying on."
    save_state || echo "Could not save the scan state; retrying after the next scan."
    wait_for_next_slot || break
  done
  echo "Handing over to the next run."
}

# Bash reads a script as it runs it, and update_code may replace this file, so
# everything is wrapped in functions that are fully loaded before main starts.
main "$@"
