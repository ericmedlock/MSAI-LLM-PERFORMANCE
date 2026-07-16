#!/bin/bash
# Battery-aware run supervisor (macOS). Wraps a long benchmark run and
# pauses/resumes it based on battery level AND charge direction, because a
# sustained M5 Max inference load can out-draw the charger (observed
# 2026-07-15/16: 96 W negotiated adapter vs full-load draw -> slow drain
# while "plugged in").
#
#   bash scripts/run_with_battery_guard.sh                 # default: local new-epoch run
#   bash scripts/run_with_battery_guard.sh <command...>    # guard any command
#   PAUSE_PCT=40 RESUME_PCT=90 bash scripts/run_with_battery_guard.sh ...
#
# Policy (hysteresis; env-overridable):
#   PAUSE when net-DISCHARGING (InstantAmperage < -50 mA) and battery <= PAUSE_PCT (30)
#         or unconditionally at HARD_FLOOR (15) — belt and suspenders.
#   RESUME when battery >= RESUME_PCT (80).
#   Poll every POLL_S (60) seconds.
#
# Pause = clean kill of the child's process group. The trial runner is
# row-level resumable, so a pause costs at most the in-flight row. SIGSTOP is
# deliberately NOT used: a frozen client trips read-timeouts on resume (bug
# B6 class). The supervisor holds `caffeinate -is` for its whole lifetime so
# the system never sleeps through a pause (display may sleep; idle charging
# at ~10 W draw refills fast); the child runs bare — no nested caffeinate.
#
# Telemetry: one CSV line per poll -> logs/battery_guard.csv (gitignored):
#   timestamp,state,pct,instant_mA,adapter_W,event
set -euo pipefail
cd "$(dirname "$0")/.."

# hold the system awake for the supervisor's entire lifetime (incl. pauses)
if [ -z "${_GUARD_CAFF:-}" ]; then
  exec env _GUARD_CAFF=1 caffeinate -is "$0" "$@"
fi

PAUSE_PCT="${PAUSE_PCT:-30}"
RESUME_PCT="${RESUME_PCT:-80}"
HARD_FLOOR="${HARD_FLOOR:-15}"
POLL_S="${POLL_S:-60}"
LOG="${GUARD_LOG:-logs/battery_guard.csv}"
mkdir -p "$(dirname "$LOG")"
[ -s "$LOG" ] || echo "timestamp,state,pct,instant_mA,adapter_W,event" >> "$LOG"

if [ "$#" -gt 0 ]; then
  CMD=("$@")
else
  # canonical local new-epoch run (lenient verdict per Amendment 2026-07-14)
  CMD=(env AGENTIC_VERDICT=lenient LLM_PROVIDER=ollama
       LLM_BASE_URL=http://localhost:11434 LLM_MODEL=deepseek-r1:14b
       bash scripts/run_trials.sh local)
fi

batt_pct() { pmset -g batt | grep -Eo '[0-9]+%' | head -1 | tr -d '%'; }

instant_ma() {
  # signed mA: negative = net discharge. ioreg prints negatives as unsigned
  # 64-bit; sign-correct in awk (double precision is fine for sign/magnitude).
  ioreg -rn AppleSmartBattery | awk '/"InstantAmperage"/ {
    a = $3 + 0; if (a > 9223372036854775807) a -= 18446744073709551616;
    printf "%d", a }'
}

adapter_w() { pmset -g adapter 2>/dev/null | awk '/Wattage/ {gsub(/W/,"",$3); print $3; exit}'; }

log_line() { echo "$(date '+%Y-%m-%dT%H:%M:%S'),$1,$2,$3,$4,$5" >> "$LOG"; }

CHILD_PID=""
set -m  # job control: child gets its own process group (pgid == pid)

start_child() {
  "${CMD[@]}" &
  CHILD_PID=$!
  echo "[guard] child started pid=$CHILD_PID: ${CMD[*]}"
}

stop_child() {
  if [ -n "$CHILD_PID" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
    /bin/kill -TERM -- "-$CHILD_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$CHILD_PID" 2>/dev/null || break
      sleep 1
    done
    /bin/kill -KILL -- "-$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi
  CHILD_PID=""
}

cleanup() { stop_child; exit 130; }
trap cleanup INT TERM

start_child
STATE=RUN
echo "[guard] policy: pause at <=${PAUSE_PCT}% discharging (hard ${HARD_FLOOR}%), resume at >=${RESUME_PCT}%, poll ${POLL_S}s"

while true; do
  sleep "$POLL_S"
  PCT="$(batt_pct)"; MA="$(instant_ma)"; AW="$(adapter_w)"
  PCT="${PCT:-0}"; MA="${MA:-0}"; AW="${AW:-0}"

  if [ "$STATE" = RUN ] && ! kill -0 "$CHILD_PID" 2>/dev/null; then
    set +e; wait "$CHILD_PID"; RC=$?; set -e
    log_line RUN "$PCT" "$MA" "$AW" "child_exited_rc=$RC"
    echo "[guard] run finished (rc=$RC)"
    exit "$RC"
  fi

  EVENT=""
  if [ "$STATE" = RUN ]; then
    if { [ "$MA" -lt -50 ] && [ "$PCT" -le "$PAUSE_PCT" ]; } || [ "$PCT" -le "$HARD_FLOOR" ]; then
      EVENT="pause"
      echo "[guard] PAUSING: ${PCT}% at ${MA} mA (adapter ${AW} W)"
      stop_child
      STATE=PAUSED
    fi
  else
    if [ "$PCT" -ge "$RESUME_PCT" ]; then
      EVENT="resume"
      echo "[guard] RESUMING: ${PCT}%"
      start_child
      STATE=RUN
    fi
  fi
  log_line "$STATE" "$PCT" "$MA" "$AW" "$EVENT"
done
