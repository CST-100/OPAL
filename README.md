# OPAL

**Operations, Procedures, Assets, Logistics**

An enterprise resource planning system optimized for small teams and hardware projects.

## Download

Install with a single command:

```bash
# macOS / Linux
curl -LsSf https://raw.githubusercontent.com/CST-100/OPAL/master/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/CST-100/OPAL/master/install.ps1 | iex
```

Or download manually from [GitHub Releases](https://github.com/CST-100/OPAL/releases/latest):

| Platform | File |
|----------|------|
| macOS (Apple Silicon) | `opal-macos-arm64` |
| macOS (Intel) | `opal-macos-x86_64` |
| Linux (x86_64) | `opal-linux-x86_64` |
| Windows (x86_64) | `opal-windows-x86_64.exe` |

Run it. The launcher initializes the database on first launch, starts the server, and opens the web UI. No Python or dependencies required.

## Features

- **Inventory & Procurement**: Parts database, inventory tracking, purchase order management
- **Procedures**: Versioned procedure templates with step-by-step execution
- **Issues**: Manual and auto-created issue tracking
- **Local-first**: Runs on a single laptop, accessible to network

## Development Setup

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Initialize database
uv run opal init

# Start server
uv run opal serve
```

Access the web UI at http://localhost:8080

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Generate migration
uv run opal migrate generate --message "Description"

# Apply migrations
uv run opal migrate upgrade
```

## Stack

- **Database**: SQLite
- **Backend**: Python 3.11+ with FastAPI
- **Frontend**: HTMX + Jinja2 templates
- **Desktop App**: Textual TUI launcher with auto-updater
