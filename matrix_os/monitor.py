from __future__ import annotations
import os
import sys
from typing import Dict, List
import psutil

SUSPICIOUS_PROCS = {
    "tcpdump", "wireshark", "dumpcap", "tshark", "strace", "ltrace", "frida-server", "gdb",
}

ENV_FLAGS = ["LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "LD_DEBUG", "LD_AUDIT"]


def check_debugger_attached() -> bool:
    if sys.gettrace() is not None:
        return True
    status_path = "/proc/self/status"
    try:
        with open(status_path, "r") as f:
            for line in f:
                if line.startswith("TracerPid:"):
                    tracer = int(line.split(":", 1)[1].strip())
                    return tracer != 0
    except Exception:
        pass
    return False


def check_env_flags() -> List[str]:
    present: List[str] = []
    for key in ENV_FLAGS:
        if os.environ.get(key):
            present.append(key)
    return present


def find_suspicious_processes() -> List[str]:
    found: List[str] = []
    for proc in psutil.process_iter(attrs=["name"]):
        name = (proc.info.get("name") or "").lower()
        if name in SUSPICIOUS_PROCS:
            found.append(name)
    return sorted(set(found))


def summary() -> Dict[str, object]:
    return {
        "debugger": check_debugger_attached(),
        "env_flags": check_env_flags(),
        "suspicious_processes": find_suspicious_processes(),
    }
