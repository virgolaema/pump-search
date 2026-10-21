#!/usr/bin/env bash
# Runs collect every 10 min (weekdays 08:00-24:00 UTC) and evaluate once at 00:20 UTC (Tue-Sat),
# for up to LOOP_MINUTES, committing after each step. The workflow then re-dispatches itself.
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

mkdir -p logs
while [ $SECONDS -lt $end ]; do
  dow=$(date -u +%u); hour=$(date -u +%-H); min=$(date -u +%-M)
  if [ "$dow" -le 5 ] && [ "$hour" -ge 8 ]; then
    sync
    python -m pump.collect > logs/collect.log 2>&1; tail -1 logs/collect.log
    commit "data: collect $(date -u +%FT%TZ)"
  fi
  if [ "$dow" -ge 2 ] && [ "$dow" -le 6 ] && [ "$hour" -eq 0 ] && [ "$min" -ge 20 ] && [ "$min" -lt 30 ]; then
    sync
    python -m pump.evaluate > logs/evaluate.log 2>&1; tail -3 logs/evaluate.log
    commit "report: $(date -u +%F)"
  fi
  now=$(date -u +%s); left=$(( end - SECONDS ))
  wait=$(( 600 - now % 600 + 5 ))
  [ $wait -gt $left ] && break
  if [ "$dow" -le 5 ] && [ "$hour" -ge 8 ] && [ $wait -gt 150 ]; then
    # minute-by-minute watcher on the hot list until ~15 s before the next 10-minute scan
    python -m pump.watch --seconds $(( wait - 20 )) > logs/watch.log 2>&1; tail -2 logs/watch.log
    commit "watch: $(date -u +%FT%TZ)"
    now=$(date -u +%s); wait=$(( 600 - now % 600 + 5 ))
    [ $(( now % 600 )) -lt 120 ] && wait=0      # just past the boundary: scan right away, do not skip a slot
  fi
  sleep $wait
done
