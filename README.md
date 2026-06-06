# xboxctl

Control an Xbox from the command line.

`xboxctl` can list consoles, read console state, launch apps, send controller
buttons, type text, control media, power a console on or off, and capture the
screen through Remote Play. It is built for scripts and agents, but it is still
comfortable to use by hand.

## Install

```bash
git clone https://github.com/KJdotIO/xboxctl.git
cd xboxcli
uv sync
uv run xboxctl --help
```

Install the Xbox command dependencies:

```bash
uv sync --extra real
```

Observation mode also needs the Node dependencies used by the Remote Play
helper:

```bash
npm install
npx playwright install chromium
```

## Quick Start

```bash
uv run xboxctl auth login
uv run xboxctl auth validate
uv run xboxctl consoles
uv run xboxctl status --json
uv run xboxctl apps
uv run xboxctl launch Halo --confirm
```

Read-only commands run straight away. Commands that change console state require
`--confirm`, which makes them safer to use in scripts.

## Xbox Setup

Sign in once before sending commands:

```bash
uv run xboxctl auth login
uv run xboxctl auth validate
uv run xboxctl auth whoami
```

If your browser keeps choosing the wrong Microsoft account, force a fresh login:

```bash
uv run xboxctl auth login --prompt login
```

Then use the CLI:

```bash
uv run xboxctl consoles
uv run xboxctl status --json
uv run xboxctl apps --json
uv run xboxctl press dpad-right --confirm
uv run xboxctl launch YouTube --confirm
uv run xboxctl power off --confirm
uv run xboxctl power on --confirm
```

For local development and CI, use the fake provider explicitly with
`--provider fake` or `XBOXCTL_PROVIDER=fake`. It returns stable sample data and
does not contact Xbox services.

## Observe

Use `observe screenshot` when you want one frame from the console:

```bash
uv run xboxctl observe screenshot \
  --output /tmp/xbox-frame.jpg \
  --format jpeg \
  --width 960 \
  --quality 72
```

Use `observe flow` for short capture-and-control runs in one Remote Play
session:

```bash
uv run xboxctl observe flow \
  --output-dir /tmp/xbox-flow \
  --step capture:before \
  --step press:right:2 \
  --step capture:after \
  --format jpeg \
  --width 960 \
  --quality 72
```

Use a persistent observe session for longer agent workflows:

```bash
uv run xboxctl observe start \
  --session-file /tmp/xbox-session.json \
  --format jpeg \
  --width 960 \
  --quality 72

uv run xboxctl observe capture \
  --session-file /tmp/xbox-session.json \
  --output /tmp/before.jpg

uv run xboxctl observe press \
  --session-file /tmp/xbox-session.json \
  right \
  --repeat 2

uv run xboxctl observe capture \
  --session-file /tmp/xbox-session.json \
  --output /tmp/after.jpg

uv run xboxctl observe status --session-file /tmp/xbox-session.json
uv run xboxctl observe stop --session-file /tmp/xbox-session.json
```

If a previous observe process has already gone away, clean up the stale local
session file:

```bash
uv run xboxctl observe cleanup --session-file /tmp/xbox-session.json
```

## MCP

`xboxctl` includes a local MCP server for agents:

```bash
uv run xboxctl-mcp
```

For local development, add it to an MCP client with:

```json
{
  "mcpServers": {
    "xboxctl": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/dot/xboxcli",
        "run",
        "xboxctl-mcp"
      ]
    }
  }
}
```

Once the package is published, the config can use `uvx` instead:

```json
{
  "mcpServers": {
    "xboxctl": {
      "command": "uvx",
      "args": ["xboxctl-mcp"]
    }
  }
}
```

The MCP exposes the normal Xbox tools directly: status, apps, storage, launch,
button presses, text, media, power, and observe session controls.

Some clients need an HTTP MCP endpoint instead of stdio:

```bash
uv run xboxctl-mcp --http
```

That starts the local server at `http://127.0.0.1:3000/mcp`.

For local tests, run:

```bash
uv run xboxctl-mcp --provider fake
```

## Development

```bash
uv run ruff check .
uv run basedpyright
uv run pytest -q
```

The project uses Python 3.13, Typer, Rich, Pydantic, pytest, ruff, basedpyright,
Playwright, and the Xbox Remote Play helper packages listed in `package.json`.

## Acknowledgements

`xboxctl` builds on work from the Xbox community:

- [`python-xbox`](https://pypi.org/project/python-xbox/) for Xbox auth and web
  API access.
- [`xal-node`](https://www.npmjs.com/package/xal-node) for xHome streaming
  authentication.
- [`xbox-xcloud-player`](https://www.npmjs.com/package/xbox-xcloud-player) for
  the browser Remote Play player used by observe mode.
- The OpenXbox SmartGlass projects and documentation, which helped shape the
  local-control fallback.

This project is unofficial and is not affiliated with Microsoft or Xbox.

## Licence

MIT. See [LICENSE](LICENSE).
