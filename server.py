# /// script
# dependencies = ["frida==16.1.4", "fastmcp"]
# requires-python = ">=3.10"
# ///
"""Frida MCP server — entry point that wires all tools together."""

from fastmcp import FastMCP

from tools import (
    register_device_tools,
    register_process_tools,
    register_lifecycle_tools,
    register_session_tools,
)

mcp = FastMCP("Frida")

register_device_tools(mcp)
register_process_tools(mcp)
register_lifecycle_tools(mcp)
register_session_tools(mcp)


def main():
    """Run the Frida MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
