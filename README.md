# Google Antigravity Pro & Hermes Bridge (`agy-cli`)

This repository provides tools and wrappers to integrate your official **Google Antigravity CLI** (`agy`) and active **Antigravity Pro subscription** (Google One AI Premium OAuth credentials) seamlessly with **Hermes Agent** and other developer environments.

No AI Studio API keys or developer registrations are needed; all requests are authenticated natively through your macOS Keychain token using the official CLI under the hood.

---

## Features

1. **Transparent TTY Wrapper (`agy_wrapper.py`)**:
   Prevents background/non-interactive calls (e.g. from Hermes) from hanging when the CLI expects standard input. Automatically redirects `stdin` to `/dev/null` in non-interactive sessions while preserving 100% of the interactive TUI.
2. **OpenAI-Compatible API Proxy (`agy_api.py`)**:
   Exposes a local FastAPI/Uvicorn server hosting the standard `/v1/chat/completions` endpoint. It translates chat completion requests into the official `agy` command executions.
3. **FastMCP Server (`agy_mcp.py`)**:
   Exposes the `ask_antigravity` tool to other agents via Model Context Protocol (MCP).
4. **Persistent LaunchAgent daemon**:
   A macOS plist template and setup script to run the API server persistently in the background.

---

## Installation & Setup

### 1. Install Dependencies
Clone this repository and set up a virtual environment:
```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### 2. Standalone Wrapper Setup
Rename your original `agy` binary to `agy.original` and link this wrapper script to your path:
```bash
mv ~/.local/bin/agy ~/.local/bin/agy.original
cp agy_wrapper.py ~/.local/bin/agy
chmod +x ~/.local/bin/agy
```

### 3. API Proxy Background Service (macOS)
Since the `Desktop` directory is sandboxed on macOS, it is recommended to place the background script inside a non-protected folder like `~/.hermes/agy-api`:

1. Copy the proxy code and setup a clean virtualenv:
   ```bash
   mkdir -p ~/.hermes/agy-api
   cp agy_api.py ~/.hermes/agy-api/
   uv venv ~/.hermes/agy-api/.venv
   ~/.hermes/bin/uv pip install fastapi uvicorn --python ~/.hermes/agy-api/.venv/bin/python
   ```
2. Create the launcher script:
   Write the following to `~/.hermes/agy-api/start_api.sh` and run `chmod +x`:
   ```bash
   #!/bin/bash
   cd ~/.hermes/agy-api
   export PATH="/Users/arielkurek/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
   export HOME="/Users/arielkurek"
   exec .venv/bin/python -u agy_api.py
   ```
3. Register the LaunchAgent:
   Place a plist file at `~/Library/LaunchAgents/com.antigravity.agy-api.plist`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.antigravity.agy-api</string>
       <key>ProgramArguments</key>
       <array>
           <string>/Users/arielkurek/.hermes/agy-api/start_api.sh</string>
       </array>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <true/>
       <key>StandardOutPath</key>
       <string>/Users/arielkurek/.hermes/logs/agy-api-stdout.log</string>
       <key>StandardErrorPath</key>
       <string>/Users/arielkurek/.hermes/logs/agy-api-stderr.log</string>
   </dict>
   </plist>
   ```
4. Load the daemon:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.antigravity.agy-api.plist
   ```

---

## Usage

### OpenAI API Proxy
Test the completions server locally:
```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Claude Sonnet 4.6 (Thinking)", "messages": [{"role": "user", "content": "Say Hello"}]}'
```

### Hermes Agent Config
Add this to your `~/.hermes/config.yaml`:
```yaml
model:
  default: "Claude Sonnet 4.6 (Thinking)"
  provider: "custom"
  base_url: "http://127.0.0.1:8000/v1"

providers:
  custom:
    api_key: "not-needed"
    base_url: "http://127.0.0.1:8000/v1"
```
