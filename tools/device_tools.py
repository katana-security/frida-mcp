"""Device discovery tools — stateless."""

from typing import Any

import frida
from fastmcp import FastMCP

from device import format_device_info


def register_device_tools(server: FastMCP) -> None:

    @server.tool
    def list_devices() -> list[dict[str, Any]]:
        """List all devices connected to the system.

        Returns:
            A list of device information dictionaries containing:
            - id: Device ID
            - name: Device name
            - type: Device type
        """
        devices = frida.enumerate_devices()
        return [format_device_info(d) for d in devices]
