#!/bin/bash
# Stability Watchdog — 60s read-only. Silent unless ALERT.
# Writes state file: ~/.hermes/state/stability-watchdog-last-run
export PATH=/usr/bin:/bin:/usr/sbin:/sbin

NOW=$(/usr/bin/date -Is)
REPORT=""
ROOT_STATUS="UNKNOWN"; ROOT_SOURCE="UNKNOWN"; ROOT_RW="UNKNOWN"

# --- ROOT ---
if ROOT_INFO=$(/usr/bin/findmnt -no SOURCE,OPTIONS / 2>/dev/null); then
    ROOT_SOURCE=$(/usr/bin/echo "$ROOT_INFO" | /usr/bin/awk '{print $1}')
    ROOT_OPTS=$(/usr/bin/echo "$ROOT_INFO" | /usr/bin/awk '{print $2}')
    RW_FOUND=0; RO_FOUND=0
    IFS=',' read -ra TOKS <<< "$ROOT_OPTS"
    for tok in "${TOKS[@]}"; do
        [ "$tok" = "rw" ] && RW_FOUND=1
        [ "$tok" = "ro" ] && RO_FOUND=1
    done
    [ "$RW_FOUND" = "1" ] && [ "$RO_FOUND" = "0" ] && ROOT_RW="rw"
    [ "$RO_FOUND" = "1" ] && [ "$RW_FOUND" = "0" ] && ROOT_RW="ro"
    if /usr/bin/findmnt -no SOURCE / 2>/dev/null | /usr/bin/grep -qF "$ROOT_SOURCE"; then
        ROOT_STATUS="OK"
    else
        ROOT_STATUS="ALERT"; REPORT="${REPORT}ROOT_SOURCE_GONE\n"
    fi
fi
[ "$ROOT_RW" = "ro" ] && { ROOT_STATUS="ALERT"; REPORT="${REPORT}ROOT_READ_ONLY\n"; }

# --- NVME ---
NVME_STATUS="UNKNOWN"; NVME_STATES=""
if /usr/bin/ls /sys/class/nvme/nvme*/state >/dev/null 2>&1; then
    NVME_STATUS="OK"
    for s in /sys/class/nvme/nvme*/state; do
        n=$(/usr/bin/basename "$(/usr/bin/dirname "$s")")
        v=$(/usr/bin/cat "$s" 2>/dev/null || /usr/bin/echo "?")
        NVME_STATES="${NVME_STATES}${n}=${v} "
    done
fi

# --- DSTATE ---
DSTATE_COUNT=$(/usr/bin/ps -eo stat --no-headers 2>/dev/null | /usr/bin/grep -c '^D')
DSTATE_VAL="${DSTATE_COUNT:-?}"

# --- PSI ---
PSI_FULL="?"; PSI_SOME="?"
if [ -r /proc/pressure/io ]; then
    PSI_FULL=$(/usr/bin/awk '/^full/{print $3}' /proc/pressure/io 2>/dev/null || /usr/bin/echo "?")
    PSI_SOME=$(/usr/bin/awk '/^some/{print $3}' /proc/pressure/io 2>/dev/null || /usr/bin/echo "?")
fi

# --- KERNEL ---
KERNEL_STATUS="UNKNOWN"
TS_FILE="/tmp/stability-watchdog-last-ts"
if /usr/bin/which journalctl >/dev/null 2>&1; then
    SINCE=""
    [ -f "$TS_FILE" ] && [ -s "$TS_FILE" ] && SINCE=$(/usr/bin/cat "$TS_FILE")
    [ -z "$SINCE" ] && SINCE="2 minutes ago"
    NEW_MSGS=$(/usr/bin/journalctl -k --since "$SINCE" --no-pager 2>/dev/null || true)
    if [ -n "$NEW_MSGS" ] && ! /usr/bin/echo "$NEW_MSGS" | /usr/bin/grep -q 'No entries'; then
        KERNEL_STATUS="OK"
        ALERTS=$(/usr/bin/echo "$NEW_MSGS" | /usr/bin/grep -iE 'I/O error|nvme.*down|reset fail|controller.*down|READ ONLY' 2>/dev/null || true)
        [ -n "$ALERTS" ] && { KERNEL_STATUS="ALERT"; REPORT="${REPORT}KERNEL: $ALERTS\n"; }
    elif /usr/bin/echo "$NEW_MSGS" | /usr/bin/grep -q 'No entries'; then
        KERNEL_STATUS="OK"
    fi
    /usr/bin/date -Is > "$TS_FILE"
fi

# --- STATE FILE ---
STATE_FILE="/tmp/stability-watchdog-state"
/usr/bin/cat > "$STATE_FILE" <<STATE_EOF
time=$NOW
root=$ROOT_STATUS($ROOT_SOURCE,$ROOT_RW)
nvme=$NVME_STATUS($NVME_STATES)
kernel=$KERNEL_STATUS
dstate=$DSTATE_VAL
psi_full=$PSI_FULL
psi_some=$PSI_SOME
STATE_EOF

# --- ALERT ONLY ---
if [ -n "$REPORT" ]; then
    /usr/bin/echo "[$NOW] STABILITY ALERT"
    /usr/bin/echo -e "$REPORT"
    /usr/bin/echo "NVME: $NVME_STATES DSTATE=$DSTATE_VAL PSI full=$PSI_FULL some=$PSI_SOME"
fi