"""Stateful REPL system — execute JS, retrieve messages, manage lifecycle."""

import threading
import time
from typing import Any

import frida
from fastmcp import FastMCP
from pydantic import Field

from device import resolve_device
import state

SCRIPT_TIMEOUT = 5.0  # seconds to wait for initial script result


def _execute_script(session_id: str, javascript_code: str, keep_alive: bool, resume_after: bool) -> dict[str, Any]:
    """Core script execution logic, reusable from multiple tools."""
    session = state.get_session(session_id)
    meta = state.get_session_meta(session_id)

    try:
        wrapped_code = f"""
    (function() {{
        var initialLogs = [];
        var originalLog = console.log;

        console.log = function() {{
            var args = Array.prototype.slice.call(arguments);
            var logMsg = args.map(function(arg) {{
                return typeof arg === 'object' ? JSON.stringify(arg) : String(arg);
            }}).join(' ');
            initialLogs.push(logMsg);
            originalLog.apply(console, arguments);
        }};

        var scriptResult;
        var scriptError;
        try {{
            scriptResult = eval({javascript_code!r});
        }} catch (e) {{
            scriptError = {{ message: e.toString(), stack: e.stack }};
        }}

        console.log = originalLog;

        send({{
            type: 'execution_receipt',
            result: scriptError ? undefined : (scriptResult !== undefined ? scriptResult.toString() : 'undefined'),
            error: scriptError,
            initial_logs: initialLogs
        }});
    }})();
    """

        script = session.create_script(wrapped_code)

        receipt_event = threading.Event()
        initial_execution_results: list[dict] = []
        results_lock = threading.Lock()

        def on_message(message, data):
            is_receipt = (
                message["type"] == "send"
                and isinstance(message.get("payload"), dict)
                and message["payload"].get("type") == "execution_receipt"
            )
            is_error = message["type"] == "error"

            if is_receipt or (is_error and not receipt_event.is_set()):
                with results_lock:
                    if is_receipt:
                        initial_execution_results.append(message["payload"])
                    else:
                        initial_execution_results.append(
                            {"script_error": message["description"], "details": message}
                        )
                receipt_event.set()
            elif keep_alive:
                state.append_message(
                    session_id,
                    {"type": message["type"], "payload": message.get("payload"), "data": data},
                )

        script.on("message", on_message)
        if keep_alive:
            state.add_persistent_script(session_id, script)

        script.load()
        receipt_event.wait(timeout=SCRIPT_TIMEOUT)

        final_result: dict[str, Any] = {}
        with results_lock:
            if initial_execution_results:
                receipt = initial_execution_results[0]
                if "script_error" in receipt:
                    final_result = {
                        "status": "error",
                        "error": "Script execution error",
                        "details": receipt["script_error"],
                    }
                elif receipt.get("error"):
                    final_result = {
                        "status": "error",
                        "error": receipt["error"]["message"],
                        "stack": receipt["error"]["stack"],
                        "initial_logs": receipt.get("initial_logs", []),
                    }
                else:
                    final_result = {
                        "status": "success",
                        "result": receipt["result"],
                        "initial_logs": receipt.get("initial_logs", []),
                    }
            else:
                final_result = {
                    "status": "timeout",
                    "message": f"Script sent no execution receipt within {SCRIPT_TIMEOUT}s.",
                    "initial_logs": [],
                }

        if not keep_alive:
            script.unload()
            final_result["script_unloaded"] = True
        else:
            final_result["script_unloaded"] = False

        if resume_after and final_result["status"] == "success":
            try:
                device = resolve_device(meta["device_id"])
                device.resume(meta["pid"])
                final_result["resumed"] = True
            except Exception as e:
                final_result["resumed"] = False
                final_result["resume_error"] = str(e)

        return final_result

    except frida.InvalidOperationError as e:
        return {
            "status": "error",
            "error": f"Frida operation error: {str(e)} (Session may be detached)",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def register_session_tools(server: FastMCP) -> None:

    @server.tool
    def execute(
        session_id: str = Field(
            description="The unique identifier of the active Frida session."
        ),
        javascript_code: str = Field(
            description="JavaScript code to execute in the target process's context. Can use Frida's JS API (Interceptor, Memory, Module, rpc)."
        ),
        keep_alive: bool = Field(
            default=False,
            description="If True, the script stays loaded for persistent hooks/RPC. Retrieve async messages with get_messages. If False (default), the script is unloaded after execution.",
        ),
        resume_after: bool = Field(
            default=False,
            description="If True, automatically resume the process after a successful injection. Useful after attach (spawn mode) to start the app with hooks active. Only resumes on success.",
        ),
    ) -> dict[str, Any]:
        """Execute JavaScript code within an existing interactive Frida session.

        Typical flow after attach:
          execute(session_id, hook_code, keep_alive=True, resume_after=True)
        """
        return _execute_script(session_id, javascript_code, keep_alive, resume_after)

    @server.tool
    def get_messages(
        session_id: str = Field(
            description="The ID of the session to retrieve messages from."
        ),
        duration: float | None = Field(
            default=None,
            description="Optional number of seconds to wait and collect messages before returning. "
                        "If not specified, returns immediately with whatever is in the queue.",
        ),
    ) -> dict[str, Any]:
        """Retrieve and clear messages sent by persistent scripts in a session.

        Returns messages captured since the last call.
        Use duration to wait and collect messages over a time window.
        """
        if not state.has_session(session_id):
            if state.has_persistent_scripts(session_id) and not state.get_persistent_scripts(session_id):
                return {
                    "status": "success",
                    "messages": [],
                    "info": "Session had persistent scripts that might be finished or detached.",
                }
            raise ValueError(
                f"Session with ID {session_id} not found or no persistent scripts active."
            )

        if not state.has_message_queue(session_id):
            return {
                "status": "error",
                "error": f"Message queue not found for session {session_id}.",
            }

        if duration and duration > 0:
            time.sleep(duration)

        messages = state.drain_messages(session_id)

        return {
            "status": "success",
            "session_id": session_id,
            "messages_retrieved": len(messages),
            "messages": messages,
        }

    @server.tool
    def detach(
        session_id: str = Field(
            description="Session ID to detach from."
        ),
        unload_only: bool = Field(
            default=False,
            description="If True, only unload scripts but keep session open. If False (default), close session entirely.",
        ),
    ) -> dict[str, Any]:
        """Detach from a session.

        Default: unload all scripts, detach from process, clean up state. Process keeps running.
        With unload_only=True: only unload persistent scripts, session stays open for new scripts.
        Use kill to also terminate the process.
        """
        if not state.has_session(session_id):
            raise ValueError(f"Session with ID {session_id} not found")

        if unload_only:
            count = state.unload_session_scripts(session_id)
            return {
                "status": "success",
                "session_id": session_id,
                "scripts_unloaded": count,
                "message": "Scripts unloaded. Session still open.",
            }

        meta = state.get_session_meta(session_id)
        state.remove_session(session_id)

        return {
            "status": "success",
            "session_id": session_id,
            "pid": meta["pid"],
            "message": "Session closed. Process is still running.",
        }
