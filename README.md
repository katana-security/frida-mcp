# Frida MCP

A Model Context Protocol (MCP) server for Frida dynamic instrumentation toolkit. Built with [FastMCP](https://github.com/jlowin/fastmcp).

## Features

- Process management (list, spawn, resume, kill)
- Device management (USB, local, remote)
- Application enumeration (Android/iOS)
- Interactive JavaScript REPL with persistent hooks
- Thread-safe session management with detach detection

## Project Structure

```
frida-mcp/
├── server.py              # entry point: uv run server.py
├── state.py               # session/script/message state + thread locks
├── device.py              # resolve_device(), format_device_info()
├── tools/
│   ├── __init__.py
│   ├── device_tools.py    # list_devices
│   ├── process_tools.py   # list_processes, list_applications
│   ├── lifecycle_tools.py # attach, resume, kill
│   └── session_tools.py   # execute, get_messages, detach
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

No setup needed — `uv run` handles dependencies automatically:

```bash
uv run server.py
```

### Frida version

This server is pinned to **frida 16.1.4**. The frida-server on your device must match.

**iOS (jailbroken):**

```bash
wget https://github.com/frida/frida/releases/download/16.1.4/frida_16.1.4_iphoneos-arm64.deb
scp frida_16.1.4_iphoneos-arm64.deb root@<device-ip>:/tmp/
ssh root@<device-ip> "dpkg -i /tmp/frida_16.1.4_iphoneos-arm64.deb"
```

**Android (rooted):**

```bash
wget https://github.com/frida/frida/releases/download/16.1.4/frida-server-16.1.4-android-arm64.xz
unxz frida-server-16.1.4-android-arm64.xz
adb push frida-server-16.1.4-android-arm64 /data/local/tmp/frida-server
adb shell "chmod 755 /data/local/tmp/frida-server && /data/local/tmp/frida-server &"
```

## Configuration

### Claude Code

```bash
claude mcp add frida -- uv run /path/to/frida-mcp/server.py
```

### Claude Desktop / Cursor

```json
{
  "mcpServers": {
    "frida": {
      "command": "uv",
      "args": ["run", "/path/to/frida-mcp/server.py"]
    }
  }
}
```

## Tools (9)

### Device Discovery
| Tool | Description |
|------|-------------|
| `list_devices` | List all connected devices |

### Process Operations
| Tool | Description |
|------|-------------|
| `list_processes(name?)` | List running processes, optional name filter (case-insensitive substring) |
| `list_applications` | List installed apps with bundle IDs (mobile) |

### Process Lifecycle
| Tool | Description |
|------|-------------|
| `attach(target, script?, args?)` | String target → spawn + attach (suspended). PID string → attach to running process. Optional `script` injects JS and auto-resumes on spawn |
| `resume(pid)` | Resume a suspended process |
| `kill(pid)` | Kill a process by PID |

### Sessions
| Tool | Description |
|------|-------------|
| `execute(session_id, code, ...)` | Execute JavaScript in a session (`keep_alive`, `resume_after`) |
| `get_messages(session_id, duration?)` | Retrieve messages from persistent scripts. Optional `duration` to wait before draining |
| `detach(session_id, unload_only?)` | Close session entirely, or `unload_only=True` to just unload scripts |

## Typical Flows

### One-shot: spawn + hook + resume (single call)
```
attach("com.target.app", script="Interceptor.attach(...)")
  → get_messages(session_id, duration=5)
```

### One-shot: attach to running process + hook
```
attach("1234", script="Interceptor.attach(...)")
  → get_messages(session_id, duration=5)
```

### Multi-step (manual control)
```
attach("com.target.app")
  → execute(session_id, hook_code, keep_alive=True)
  → resume(pid)
  → get_messages(session_id, duration=5)
  → detach(session_id)
```

### Cleanup
```
detach(session_id)                      # close session entirely
detach(session_id, unload_only=True)    # unload scripts, session stays open
kill(pid)                               # terminate process
```

## License

MIT
