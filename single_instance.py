"""
single_instance.py — Double-run guard (v5.0 Tier 1)

Problem: bot ek hi VPS pe 2 baar start ho jaye to DONO instances market
scan chalayenge = DOUBLE TRADING (sabse khatarnak ops bug).
Solution: PID lock file. Stale lock (dead PID) auto-recover hota hai.
"""

import os

from utils import append_log
from config import AUDIT_LOG_FILE, INSTANCE_LOCK_FILE


def acquire_instance_lock() -> tuple:
    """
    Returns (ok: bool, reason: str).
    ok=True → is process ko chalne do (lock acquired).
    ok=False → koi aur live instance chal raha hai — ise exit karna chahiye.
    """
    try:
        if os.path.exists(INSTANCE_LOCK_FILE):
            try:
                with open(INSTANCE_LOCK_FILE, "r") as f:
                    old_pid = int(f.read().strip() or "0")
                if old_pid > 0:
                    os.kill(old_pid, 0)  # process alive check
                    return False, f"Another bot instance is already running (pid={old_pid}). Exiting."
            except (ProcessLookupError, ValueError):
                pass  # stale/dead lock — recover
            except PermissionError:
                return False, "Lock file exists but pid cannot be checked. Exiting (safe)."
        with open(INSTANCE_LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        append_log(AUDIT_LOG_FILE, f"INSTANCE LOCK ACQUIRED: pid={os.getpid()}")
        return True, "OK"
    except OSError as e:
        return False, f"Lock acquisition failed: {type(e).__name__}: {e}"


def release_instance_lock():
    try:
        if os.path.exists(INSTANCE_LOCK_FILE):
            os.remove(INSTANCE_LOCK_FILE)
            append_log(AUDIT_LOG_FILE, "INSTANCE LOCK RELEASED")
    except OSError as e:
        append_log(AUDIT_LOG_FILE, f"INSTANCE LOCK RELEASE FAILED: {e}")
