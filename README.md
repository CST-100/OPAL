# OPAL

**Operations, Procedures, Assets, Logistics**

An enterprise resource planning system optimized for small teams and hardware projects.

## Features

- **Inventory & Procurement**: Parts database, inventory tracking, purchase order management
- **Procedures**: Versioned procedure templates with step-by-step execution
- **Issues**: Manual and auto-created issue tracking
- **Local-first**: Runs on a single laptop, accessible to network

## Quick Start

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
- **TUI**: Textual (deferred)
