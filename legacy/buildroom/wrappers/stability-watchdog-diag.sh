#!/bin/bash
# DIAGNOSTIC RUN — outputs all internal status values
set -o pipefail 2>/dev/null || true
NOW=$(date -Is)
echo "=== STABILITY WATCHDOG DIAGNOSTIC $NOW ==="

# --- ROOT ---
echo "--- ROOT ---"
if ROOT_INFO=$(findmnt -no SOURCE,OPTIONS / 2>/dev/null); then
    ROOT_SOURCE=$(echo "$ROOT_INFO" | awk '{print $1}')
    ROOT_OPTS=$(echo "$ROOT_INFO" | awk '{print $2}')
    echo "SOURCE=$ROOT_SOURCE"
    echo "OPTIONS=$ROOT_OPTS"
    RW_FOUND=0; RO_FOUND=0
    IFS=',' read -ra TOKS <<< "$ROOT_OPTS"
    for tok in "${TOKS[@]}"; do
        [ "$tok" = "rw" ] && RW_FOUND=1
        [ "$tok" = "ro" ] && RO_FOUND=1
    done
    if [ "$RW_FOUND" = "1" ] && [ "$RO_FOUND" = "0" ]; then
        echo "STATUS=rw OK"
    elif [ "$RO_FOUND" = "1" ] && [ "$RW_FOUND" = "0" ]; then
        echo "STATUS=ro ALERT"
    else
        echo "STATUS=UNKNOWN"
    fi
    if findmnt -no SOURCE / 2>/dev/null | grep -qF "$ROOT_SOURCE"; then
        echo "MOUNTED=yes"
    else
        echo "MOUNTED=no ALERT"
    fi
else
    echo "SOURCE=UNKNOWN"
    echo "STATUS=UNKNOWN (findmnt failed)"
fi

# --- NVME ---
echo "--- NVME ---"
if ls /sys/class/nvme/nvme*/state >/dev/null 2>&1; then
    for s in /sys/class/nvme/nvme*/state; do
        nvme_name=$(basename "$(dirname "$s")")
        nvme_val=$(cat "$s" 2>/dev/null || echo "unreadable")
        echo "$nvme_name state=$nvme_val"
    done
    echo "NVME_STATUS=OK"
else
    echo "NVME_STATUS=UNKNOWN (no /sys/class/nvme/*/state)"
fi

# --- DSTATE ---
echo "--- DSTATE ---"
DSTATE_COUNT=$(ps -eo stat --no-headers 2>/dev/null | grep -c '^D')
echo "COUNT=${DSTATE_COUNT:-UNKNOWN}"
echo "DSTATE_STATUS=OK"

# --- PSI ---
echo "--- PSI ---"
if [ -r /proc/pressure/io ]; then
    cat /proc/pressure/io
    echo "PSI_STATUS=OK"
else
    echo "PSI_STATUS=UNKNOWN"
fi

# --- KERNEL ---
echo "--- KERNEL ---"
TS_FILE="/tmp/stability-watchdog-last-ts"
if command -v journalctl >/dev/null 2>&1; then
    SINCE=""
    if [ -f "$TS_FILE" ] && [ -s "$TS_FILE" ]; then
        SINCE=$(cat "$TS_FILE")
    fi
    if [ -z "$SINCE" ]; then
        SINCE="2 minutes ago"
    fi
    echo "SINCE=$SINCE"
    NEW_MSGS=$(journalctl -k --since "$SINCE" --no-pager 2>&1 || true)
    JOURNAL_EXIT=$?
    echo "journalctl exit=$JOURNAL_EXIT"
    if [ "$JOURNAL_EXIT" = "0" ]; then
        if [ -z "$NEW_MSGS" ] || echo "$NEW_MSGS" | grep -q 'No entries'; then
            echo "KERNEL_STATUS=OK (no new messages)"
        else
            ALERTS=$(echo "$NEW_MSGS" | grep -iE 'I/O error|nvme.*down|reset fail|controller.*down|READ ONLY' 2>/dev/null || true)
            if [ -n "$ALERTS" ]; then
                echo "KERNEL_STATUS=ALERT"
                echo "ALERTS=$ALERTS"
            else
                echo "KERNEL_STATUS=OK (new messages, no alerts)"
            fi
        fi
    else
        echo "KERNEL_STATUS=UNKNOWN (journalctl exit=$JOURNAL_EXIT)"
    fi
    date -Is > "$TS_FILE"
else
    echo "KERNEL_STATUS=UNKNOWN (no journalctl)"
fi

# --- DF ---
echo "--- DF ---"
df -P / 2>/dev/null
df -Pi / 2>/dev/null
echo "DF_STATUS=OK"

# --- PROCS (info only) ---
echo "--- PROCS ---"
echo "ghostty=$(pgrep -c ghostty 2>/dev/null || echo '?')"
echo "codex=$(pgrep -c codex 2>/dev/null || echo '?')"
echo "hermes=$(pgrep -cf hermes 2>/dev/null || echo '?')"

echo "=== DIAGNOSTIC END ==="
