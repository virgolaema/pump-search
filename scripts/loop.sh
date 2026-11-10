#!/usr/bin/env bash
# Runs collect every 10 min during the US extended session (Mon-Fri 04:00-20:00 New York time) and evaluate once
# at 20:20 New York time, for up to LOOP_MINUTES, committing after each step. The workflow then re-dispatches itself.
# All schedule decisions use New York time, so they do not shift when US daylight saving starts or ends.
set -u
LOOP_MINUTES=${LOOP_MINUTES:-340}
end=$((SECONDS + LOOP_MINUTES * 60))

sync() { git pull --rebase -q || { git rebase --abort 2>/dev/null; git fetch -q origin main; git reset -q --hard origin/main; }; }

commit() {
  git add -A
  git diff --cached --quiet && return 0
  git commit -qm "$1"
  for i in 1 2 3 4; do
    if git pull --rebase -q; then git push -q && return 0; else git rebase --abort 2>/dev/null; fi
    sleep $((i * 5))
  done
  echo "push failed; dropping local commit"; git fetch -q origin main; git reset -q --hard origin/main
}

# weekday (1=Mon), hour and minute in New York
ny_now() { python -c "from datetime import datetime; from zoneinfo import ZoneInfo; t = datetime.now(ZoneInfo('America/New_York')); print(t.isoweekday(), t.hour, t.minute)"; }

mkdir -p logs
while [ $SECONDS -lt $end ]; do
  read -r dow hour min <<< "$(ny_now)"
  # if the Python call fails, fall back to UTC-5 so collection never stops silently
  [ -z "${min:-}" ] && read -r dow hour min <<< "$(date -u -d '5 hours ago' +'%u %-H %-M')"
  session=0; [ "$dow" -le 5 ] && [ "$hour" -ge 4 ] && [ "$hour" -lt 20 ] && session=1
  if [ $session -eq 1 ]; then
    sync
    python -m pump.collect > logs/collect.log 2>&1; tail -1 logs/collect.log
    commit "data: collect $(date -u +%FT%TZ)"
  fi
  if [ "$dow" -le 5 ] && [ "$hour" -eq 20 ] && [ "$min" -ge 20 ] && [ "$min" -lt 30 ]; then
    sync
    python -m pump.evaluate > logs/evaluate.log 2>&1; tail -3 logs/evaluate.log
    commit "report: $(date -u +%F)"
  fi
  now=$(date -u +%s); left=$(( end - SECONDS ))
  wait=$(( 600 - now % 600 + 5 ))
  [ $wait -gt $left ] && break
  if [ $session -eq 1 ] && [ $wait -gt 150 ]; then
    # minute-by-minute watcher on the hot list until ~15 s before the next 10-minute scan
    python -m pump.watch --seconds $(( wait - 20 )) > logs/watch.log 2>&1; tail -2 logs/watch.log
    commit "watch: $(date -u +%FT%TZ)"
    now=$(date -u +%s); wait=$(( 600 - now % 600 + 5 ))
    [ $(( now % 600 )) -lt 120 ] && wait=0      # just past the boundary: scan right away, do not skip a slot
  fi
  sleep $wait
done
