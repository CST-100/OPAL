# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OPAL (Operations, Procedures, Assets, Logistics)** is a local-first ERP system for small teams and hardware projects. Single SQLite database, runs on one machine, accessible over local network. No cloud dependencies.

- **Stack**: Python 3.11+, FastAPI, SQLAlchemy 2.0+, Alembic, HTMX + Jinja2 templates, SQLite
- **Package manager**: [uv](https://astral.sh/uv)

## Commands

```bash
# Setup & run
uv sync                                              # Install dependencies
uv sync --all-extras                                 # Install with dev/tui/app/e2e extras
uv run opal init                                     # Initialize database
uv run opal serve                                    # Start server at http://localhost:8080
uv run opal seed                                     # Seed demo data

# Testing
uv run pytest                                        # Run all tests (in-memory SQLite)
uv run pytest tests/unit/test_parts.py               # Run a single test file
uv run pytest tests/unit/test_parts.py::test_name -v # Run a single test

# Linting & formatting
uv run ruff check src/                               # Lint
uv run ruff format src/                              # Format

# Database migrations
uv run opal migrate generate --message "Description" # Autogenerate migration
uv run opal migrate upgrade                          # Apply migrations to head
uv run opal migrate downgrade                        # Rollback one migration

# Build standalone binary
uv run pyinstaller opal.spec                         # Output: dist/opal
```

## Architecture

### Routing layers
- `/api/*` — JSON API via FastAPI route modules in `src/opal/api/routes/`
- `/*` — HTMX web UI, all routes in single file `src/opal/web/routes.py`
- Templates in `src/opal/web/templates/` (Jinja2)

### Code organization
- `src/opal/api/routes/` — FastAPI JSON API endpoints
- `src/opal/core/` — Business logic (audit, inventory, designators, genealogy)
- `src/opal/db/models/` — SQLAlchemy ORM models (19 model files, re-exported from `__init__.py`)
- `src/opal/db/base.py` — `Base` declarative base, `IdMixin`, `TimestampMixin`, `SoftDeleteMixin`
- `src/opal/web/routes.py` — All HTMX web routes (~85KB single file)
- `src/opal/config.py` — Settings via pydantic-settings, all env vars use `OPAL_` prefix
- `src/opal/project.py` — `opal.project.yaml` loader (project-level config: tiers, part numbering, categories)
- `src/opal/integrations/onshape/` — Onshape CAD integration (client, sync engine, polling)
- `src/opal/mcp/server.py` — MCP server for Claude Code integration
- `src/opal/launcher.py` — Textual TUI desktop launcher
- `src/opal/__main__.py` — CLI entry point (`opal` command)

### Application factory
`opal.api.app:create_app()` builds the FastAPI app, mounts static files and web routes, configures middleware.

### Auth modes (`OPAL_AUTH_MODE`)
- `local` (default): Cookie-based user selection via `/login`
- `exe`: Trust proxy headers `X-ExeDev-UserID` / `X-ExeDev-Email`, auto-provision users

### Test infrastructure
- Fixtures in `tests/conftest.py`: in-memory SQLite engine, per-test rollback transactions
- `client` fixture provides `TestClient` with dependency overrides
- `auth_headers` fixture provides `{"X-User-Id": str(test_user.id)}`

## Critical Rules

1. **All schema changes via Alembic migrations** — never raw DDL, never `Base.metadata.create_all` in production code
2. **SQLAlchemy ORM exclusively** — no raw SQL strings
3. **ISO 8601 timestamps everywhere** — never relative times ("2 hours ago")
4. **Published procedure versions are immutable** — editing master never affects published snapshots
5. **Soft deletes** via `deleted_at` field on most entities — don't hard-delete
6. **AuditLog records every CUD** — use `log_create`/`log_update`/`log_delete` from `src/opal/core/audit.py`
7. **Part IDs are system-unique and never reused**

## UI/UX Philosophy (US Graphics Style)

Dense, explicit, functional. Expose state and inner workings. Data tables over cards. Monospace for data-heavy areas (part numbers, IDs, timestamps). No rounded corners, shadows, or gradients. No progressive disclosure — show all relevant information. High-contrast functional color palette (green=good, yellow=warning, red=error).

## Linting (Ruff)

Configured in `pyproject.toml`: line-length 100, target Python 3.11+, rules E/F/I/UP/B/SIM. Type hints required everywhere.
