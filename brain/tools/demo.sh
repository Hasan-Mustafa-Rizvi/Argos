#!/usr/bin/env bash
# The demo's start on the Pi: the brain, started again by itself if it ever exits unexpectedly
# (an abort, a crash). q or Ctrl+C in this window ends it for good.
#
#   cd ~/Argos/brain && bash tools/demo.sh
#   ARGOS_LIVE_VIEW=1 LIVE_VIEW_FPS=8 ARGOS_CALL_AGENT=1 bash tools/demo.sh
#
# Whatever brain/.env or the environment says:
# - The wheels are off (ARGOS_WHEELS=0). A loop that starts the brain again must never start
#   the wheels again.
# - Listening is off (ARGOS_LISTEN=off). The robot's microphones give nothing, and nothing in
#   the brain's own process may open the sound card: on the Pi it dropped off USB once when the
#   head was pressed, and opening it then aborted the brain. Sound plays in a process of its
#   own (argos/playback.py).
#
# A brain that starts again after a crash picks up an open alert from the backend and stays in
# alert, without escalating again; a check that was open is asked again.

cd "$(dirname "$0")/.." || exit 1
PYTHON="${ARGOS_DEMO_PYTHON:-.venv/bin/python}"  # tests only: a stand-in for the brain
if [ ! -x "$PYTHON" ]; then
  echo "no $PYTHON in $(pwd): see FIRST_RUN.md, section 1"
  exit 1
fi

starts=0
while true; do
  starts=$((starts + 1))
  began=$(date +%s)
  ARGOS_WHEELS=0 ARGOS_LISTEN=off "$PYTHON" -m argos "$@"
  code=$?
  if [ "$code" -eq 0 ]; then
    echo "$(date +%H:%M:%S) the brain stopped (q, Ctrl+C or a stop signal): not starting it again"
    exit 0
  fi
  wait_s=3
  if [ $(( $(date +%s) - began )) -lt 10 ]; then
    wait_s=10  # it died at once: do not spin
  fi
  wait_s="${ARGOS_DEMO_WAIT_S:-$wait_s}"  # tests only
  echo "$(date +%H:%M:%S) the brain exited unexpectedly (code $code, start $starts):" \
       "starting it again in $wait_s s. Ctrl+C now to stop."
  sleep "$wait_s" || exit 130
done
