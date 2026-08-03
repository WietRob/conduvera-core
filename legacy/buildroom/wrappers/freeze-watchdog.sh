#!/bin/bash
# TUXEDO Freeze Watchdog - prüft IO-Pressure, AER-Fehler, IOWait
# Nur Ausgabe bei Überschreitung der Schwellwerte (Silent-Watchdog-Pattern)

THRESHOLD_IO_FULL=90
THRESHOLD_AER_PER_MIN=100
THRESHOLD_IOWAIT=50
THRESHOLD_BLOCKED=20

NOW=$(date -Is)

# IO Pressure
IO_FULL=$(grep 'full' /proc/pressure/io 2>/dev/null | awk '{print $3}' | cut -d= -f2)
IO_FULL_VAL=$(echo "$IO_FULL" | cut -d. -f1)

# IOWait
IOWAIT=$(vmstat 1 2 2>/dev/null | tail -1 | awk '{print $16}')

# AER errors in last minute
AER_COUNT=$(journalctl --since -1m --no-pager -k 2>/dev/null | grep -c 'pcieport 0000:00:06.0')

# Blocked processes
BLOCKED=$(vmstat 1 2 2>/dev/null | tail -1 | awk '{print $2}')

# D-state processes
DSTATE=$(ps -eo stat --no-headers 2>/dev/null | grep -c '^D')

ALERT=""

[ -n "$IO_FULL_VAL" ] && [ "$IO_FULL_VAL" -ge "$THRESHOLD_IO_FULL" ] && \
  ALERT="${ALERT}IO-Pressure full=${IO_FULL} (threshold=${THRESHOLD_IO_FULL}%)\n"

[ "$AER_COUNT" -ge "$THRESHOLD_AER_PER_MIN" ] && \
  ALERT="${ALERT}PCIe AER errors=${AER_COUNT}/min (threshold=${THRESHOLD_AER_PER_MIN})\n"

[ -n "$IOWAIT" ] && [ "$IOWAIT" -ge "$THRESHOLD_IOWAIT" ] && \
  ALERT="${ALERT}IOWait=${IOWAIT}% (threshold=${THRESHOLD_IOWAIT}%)\n"

[ -n "$BLOCKED" ] && [ "$BLOCKED" -ge "$THRESHOLD_BLOCKED" ] && \
  ALERT="${ALERT}Blocked procs=${BLOCKED} (threshold=${THRESHOLD_BLOCKED})\n"

[ "$DSTATE" -ge 3 ] && \
  ALERT="${ALERT}D-state procs=${DSTATE}\n"

if [ -n "$ALERT" ]; then
  echo "[${NOW}] FREEZE-WATCHDOG ALERT:"
  echo -e "$ALERT"
  echo "---"
  echo "nvme1 util: $(iostat -x -k 1 2 /dev/nvme1n1 2>/dev/null | grep nvme1 | tail -1 | awk '{print $NF}')%"
  echo "load: $(uptime | awk -F'load average:' '{print $2}' | xargs)"
fi
