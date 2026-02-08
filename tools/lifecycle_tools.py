"""Process lifecycle — attach (spawn or PID), resume, kill."""

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from device import resolve_device
from tools.session_tools import _execute_script
import state


def _register_detach_handler(session_id: str, frida_session: Any) -> None:
    """Attach a detach handler that marks the session as dead in state."""
    def on_detached(reason, crash):
        state.mark_detached(session_id, reason)
    frida_session.on("detached", on_detached)


def register_lifecycle_tools(server: FastMCP) -> None:

    @server.tool
    def attach(
        target: str = Field(
            description=(
                "What to attach to. Two modes:\n"
                "• Package/bundle name (e.g. 'com.example.app') → SPAWNS the app in suspended state, then attaches. "
                "Use this when the app is NOT running yet or you need hooks active from the very start.\n"
                "• PID as string (e.g. '1234') → ATTACHES to an already running process. "
                "Use this when the app is already running (you found the PID via list_processes).\n"
                "How to decide: use list_applications to find bundle IDs, use list_processes to find PIDs."
            )
        ),
        script: str | None = Field(
            default=None,
            description=(
                "Optional JavaScript code to inject immediately. Script stays loaded (keep_alive=True). "
                "If target is a package name (spawn mode), the process is auto-resumed after successful injection. "
                "If target is a PID (attach mode), no resume needed (process already running)."
            ),
        ),
        args: list[str] | None = Field(
            default=None,
            description="Optional spawn arguments. Ignored when attaching to a PID.",
        ),
        device_id: str | None = Field(
            default=None,
            description="Optional device ID. Uses USB device if not specified.",
        ),
    ) -> dict[str, Any]:
        """Attach to a process and create a Frida session.

        Pass a package name to SPAWN a new process (starts suspended).
        Pass a PID string to ATTACH to an already running process.
        Optionally inject a script in the same call.

        Returns session_id for use with execute, get_messages, detach.
        """
        try:
            device = resolve_device(device_id)

            try:
                pid_target = int(target)
                frida_session = device.attach(pid_target)
                pid = pid_target
                is_spawn = False
            except ValueError:
                if args:
                    pid = device.spawn(target, argv=args)
                else:
                    pid = device.spawn(target)
                frida_session = device.attach(pid)
                is_spawn = True

            session_id = state.generate_session_id(pid)
            state.create_session(session_id, frida_session, pid=pid, device_id=device_id)
            _register_detach_handler(session_id, frida_session)

            if script:
                script_result = _execute_script(session_id, script, keep_alive=True, resume_after=is_spawn)
                return {
                    "status": script_result["status"],
                    "pid": pid,
                    "session_id": session_id,
                    "suspended": is_spawn and script_result["status"] != "success",
                    "script_result": script_result,
                }

            if is_spawn:
                return {
                    "status": "success",
                    "pid": pid,
                    "session_id": session_id,
                    "suspended": True,
                    "message": f"Spawned {target} (PID {pid}) in suspended state. "
                               f"Inject hooks with execute, then call resume.",
                }

            return {
                "status": "success",
                "pid": pid,
                "session_id": session_id,
                "suspended": False,
                "message": f"Attached to PID {pid}. Session ready for execute.",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @server.tool
    def resume(
        pid: int = Field(description="The ID of the process to resume."),
        device_id: str | None = Field(
            default=None,
            description="Optional device ID. Uses USB device if not specified.",
        ),
    ) -> dict[str, Any]:
        """Resume a suspended process.

        Call this after attach + execute to let the app continue with hooks active.
        """
        try:
            device = resolve_device(device_id)
            device.resume(pid)
            return {"success": True, "pid": pid}
        except Exception as e:
            raise ValueError(f"Failed to resume process {pid}: {str(e)}")

    @server.tool
    def kill(
        pid: int = Field(description="The ID of the process to kill."),
        device_id: str | None = Field(
            default=None,
            description="Optional device ID. Uses USB device if not specified.",
        ),
    ) -> dict[str, Any]:
        """Kill a process by PID.

        Use this to terminate a process and start fresh.
        """
        try:
            device = resolve_device(device_id)
            device.kill(pid)
            return {"success": True, "pid": pid}
        except Exception as e:
            raise ValueError(f"Failed to kill process {pid}: {str(e)}")
