"""Shared device helpers to eliminate repeated if/else across tools."""

from typing import Any

import frida


def resolve_device(device_id: str | None = None) -> frida.core.Device:
    """Get device by ID, or USB device if None."""
    if device_id:
        return frida.get_device(device_id)
    return frida.get_usb_device()


def format_device_info(device: frida.core.Device) -> dict[str, Any]:
    """Serialize a Frida device to a {id, name, type} dict."""
    return {
        "id": device.id,
        "name": device.name,
        "type": device.type,
    }
