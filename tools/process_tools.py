"""Process read operations — list processes, list applications."""

from typing import Any

from fastmcp import FastMCP
from pydantic import Field

from device import resolve_device


def register_process_tools(server: FastMCP) -> None:

    @server.tool
    def list_processes(
        name: str | None = Field(
            default=None,
            description="Optional name filter (case-insensitive substring match). Returns all processes if not specified.",
        ),
        device_id: str | None = Field(
            default=None,
            description="Optional device ID. Uses USB device if not specified.",
        ),
    ) -> dict[str, Any]:
        """List processes on the device. Use name to filter by substring match."""
        device = resolve_device(device_id)
        processes = device.enumerate_processes()
        results = [{"pid": p.pid, "name": p.name} for p in processes]
        if name:
            results = [p for p in results if name.lower() in p["name"].lower()]
        return {"count": len(results), "processes": results}

    @server.tool
    def list_applications(
        device_id: str | None = Field(
            default=None,
            description="Optional device ID. Uses USB device if not specified.",
        ),
    ) -> list[dict[str, Any]]:
        """List all installed applications on the device.

        Essential for mobile analysis (Android/iOS) where apps have bundle identifiers
        different from process names.

        Returns:
            A list of application info dictionaries containing:
            - identifier: Application bundle ID (e.g. com.example.app)
            - name: Human-readable application name
            - pid: Process ID if running, 0 if not running
        """
        device = resolve_device(device_id)
        apps = device.enumerate_applications()
        return [
            {"identifier": app.identifier, "name": app.name, "pid": app.pid}
            for app in apps
        ]
