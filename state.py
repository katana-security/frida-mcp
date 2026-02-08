"""Centralized session/script/message state with thread-safe accessors."""

import threading
import time
import uuid
from typing import Any

MAX_MESSAGES = 1000

# Internal storage
_sessions: dict[str, Any] = {}
_session_meta: dict[str, dict[str, Any]] = {}
_script_messages: dict[str, list[dict]] = {}
_message_locks: dict[str, threading.Lock] = {}
_persistent_scripts: dict[str, list] = {}


def generate_session_id(pid: int) -> str:
    """Generate a unique session ID using uuid4."""
    return f"session_{pid}_{uuid.uuid4().hex[:8]}"


def create_session(session_id: str, session: Any, pid: int, device_id: str | None = None) -> None:
    """Register a new session with its message queue, lock, and metadata."""
    _sessions[session_id] = session
    _session_meta[session_id] = {
        "pid": pid,
        "device_id": device_id,
        "created_at": time.time(),
        "detached": False,
        "detach_reason": None,
    }
    _script_messages[session_id] = []
    _message_locks[session_id] = threading.Lock()


def get_session(session_id: str) -> Any:
    """Retrieve a session by ID. Raises ValueError if not found or detached."""
    if session_id not in _sessions:
        raise ValueError(f"Session with ID {session_id} not found")
    meta = _session_meta[session_id]
    if meta["detached"]:
        raise ValueError(
            f"Session {session_id} is detached (reason: {meta['detach_reason']}). "
            f"Close it with detach and create a new one."
        )
    return _sessions[session_id]


def get_session_meta(session_id: str) -> dict[str, Any]:
    """Get metadata (pid, device_id, created_at, detached) for a session."""
    return _session_meta[session_id]


def has_session(session_id: str) -> bool:
    """Check whether a session ID exists."""
    return session_id in _sessions


def mark_detached(session_id: str, reason: str | None = None) -> None:
    """Mark a session as detached (process crashed, user detached, etc)."""
    if session_id in _session_meta:
        _session_meta[session_id]["detached"] = True
        _session_meta[session_id]["detach_reason"] = reason


def is_detached(session_id: str) -> bool:
    """Check whether a session has been detached."""
    if session_id in _session_meta:
        return _session_meta[session_id]["detached"]
    return True


def get_lock(session_id: str) -> threading.Lock:
    """Get the message lock for a session."""
    return _message_locks[session_id]


def append_message(session_id: str, msg: dict) -> None:
    """Thread-safe append of a message to a session's queue. Drops oldest if over cap."""
    lock = _message_locks[session_id]
    with lock:
        queue = _script_messages[session_id]
        queue.append(msg)
        if len(queue) > MAX_MESSAGES:
            overflow = len(queue) - MAX_MESSAGES
            del queue[:overflow]


def drain_messages(session_id: str) -> list[dict]:
    """Atomically copy and clear the message queue for a session."""
    lock = _message_locks[session_id]
    with lock:
        messages = list(_script_messages[session_id])
        _script_messages[session_id].clear()
    return messages


def has_message_queue(session_id: str) -> bool:
    """Check whether a session has a message queue and lock."""
    return session_id in _message_locks and session_id in _script_messages


def add_persistent_script(session_id: str, script: Any) -> None:
    """Track a keep_alive script for a session."""
    if session_id not in _persistent_scripts:
        _persistent_scripts[session_id] = []
    _persistent_scripts[session_id].append(script)


def has_persistent_scripts(session_id: str) -> bool:
    """Check whether a session has any persistent scripts registered."""
    return session_id in _persistent_scripts


def get_persistent_scripts(session_id: str) -> list:
    """Get the persistent scripts for a session."""
    return _persistent_scripts.get(session_id, [])


def unload_session_scripts(session_id: str) -> int:
    """Unload all persistent scripts for a session. Returns count of unloaded scripts."""
    scripts = _persistent_scripts.pop(session_id, [])
    count = 0
    for script in scripts:
        try:
            script.unload()
            count += 1
        except Exception:
            pass
    return count


def remove_session(session_id: str) -> None:
    """Full cleanup: unload scripts, detach session, remove all state."""
    unload_session_scripts(session_id)

    session = _sessions.pop(session_id, None)
    if session is not None:
        try:
            session.detach()
        except Exception:
            pass

    _session_meta.pop(session_id, None)
    _script_messages.pop(session_id, None)
    _message_locks.pop(session_id, None)


def list_all_sessions() -> list[dict[str, Any]]:
    """Return a summary of all active sessions."""
    result = []
    for sid, meta in _session_meta.items():
        result.append({
            "session_id": sid,
            "pid": meta["pid"],
            "device_id": meta["device_id"],
            "created_at": meta["created_at"],
            "detached": meta["detached"],
            "persistent_scripts": len(_persistent_scripts.get(sid, [])),
            "pending_messages": len(_script_messages.get(sid, [])),
        })
    return result
