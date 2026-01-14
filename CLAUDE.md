# CLAUDE.MD - Project Context for AI Assistants

## Project Overview

**OPAL (Operations, Procedures, Assets, Logistics)** is an enterprise resource planning system optimized for small teams and hardware projects. It uses a local-first architecture that runs on a single laptop and is accessible to other machines on the network.

## Project Location

- Repository: `https://github.com/CST-100/OPAL`
- Main code: `./src/opal`
- Documentation: `../opal.md` (detailed requirements in parent directory)

## Core Architecture

### Stack
- **Database**: SQLite (single file at `./data/opal.db`)
- **Backend**: Python 3.11+ with FastAPI
- **Frontend Web**: HTMX + Jinja2 templates (no heavy JS framework)
- **Frontend TUI**: Textual (Python) - deferred for now
- **File Storage**: Local filesystem (`./data/attachments/`)

### Directory Structure
```
/
  /src
    /opal
      /api          # FastAPI routes
      /core         # business logic
      /db           # models, migrations
      /mcp          # Model Context Protocol server
      /tui          # Textual app (future)
      /web          # templates, static
  /tests
  /data             # .gitignored, runtime data
  /migrations       # alembic
  pyproject.toml
  CLAUDE.md
```

## Key Capabilities

### 1. Inventory & Procurement
- Parts database with system-unique auto-incrementing IDs (never reused)
- External part numbers (manufacturer PN, supplier PN)
- Inventory tracking by location with quantity and lot numbers
- Purchase order management: create → receive → update inventory
- Full traceability for any part instance

### 2. Procedures
- Master procedures with versioning (immutable snapshots)
- Kitting: define required parts and quantities
- Procedure instances ("cuts"): execution of specific version
- Step-by-step execution with data capture (measurements, checkboxes, text, file uploads)
- Work order numbers to group related instances

### 3. Execution & Non-Conformances
- Step-by-step procedure execution with data capture
- Image/file uploads per step
- Non-conformance (NC) logging at any step
- NCs auto-create linked Issues
- Contingency steps (optional until NC logged)
- Time tracking per step and total duration

### 4. Issues & Risks
- System-wide issue tracking (manual + auto-created from NCs)
- Issue types: non-conformance, bug, task, improvement
- Link issues to parts, procedures, procedure instances
- Risk tickets with probability × impact scoring
- Risks can create linked issues

### 5. Datasets & Graphing
- Define datasets with schemas
- Data points from: step execution, manual entry, CSV import
- Link datasets to procedures
- Basic graphing: time series, scatter, histogram
- CSV export

### 6. Search
- Full-text search across parts, procedures, issues, risks
- Filter by status, date range, linked entities
- Recent items / quick access

## Technical Principles

### Database & Migrations
- **CRITICAL**: All schema changes via Alembic migrations - NEVER raw SQL
- Use SQLAlchemy ORM exclusively (no raw string SQL)
- Parameterized queries only for security

### Security Foundations
- All endpoints accept optional `X-User-Id` header
- Input validation via Pydantic
- File uploads: validate MIME types, sanitize filenames, store with UUID names
- CORS: explicit allowed origins (default same-origin only)
- Rate limiting middleware present but disabled (easy to enable)

### Testing Requirements
- pytest for all backend code
- Test database: in-memory SQLite or temp file
- Playwright for e2e web UI tests
- Minimum 80% coverage on `/core` (business logic)
- GitHub Actions: lint (ruff) → test → build
- Seed data command: `opal seed` for demo data

### Audit & Versioning
- AuditLog table: every create/update/delete records old/new values as JSON
- Procedure versioning: editing master doesn't affect published versions
- "Publish" creates immutable ProcedureVersion snapshot
- Instances always reference specific version, not live master

## UI/UX Philosophy (US Graphics Style)

### Core Principles
- Emergent over prescribed aesthetics
- Expose state and inner workings
- Dense, not sparse - show all relevant data on screen
- Explicit is better than implicit
- No progressive disclosure - don't hide information
- Flat, not hierarchical
- As complex as it needs to be
- Don't infantilize users

### Design Specifics
- Data tables over cards
- Monospace font for data-heavy areas (part numbers, IDs, timestamps)
- All timestamps as ISO 8601 (2024-01-15T14:30:00), never relative
- Status indicators visible inline
- Keyboard shortcuts for common actions (documented in UI)
- No loading spinners that hide content
- Breadcrumbs showing full context path
- Color palette: high contrast, functional (green=good, yellow=warning, red=error)
- No rounded corners, shadows, or gradients
- Visible grid/structure lines where they aid comprehension

## Data Model Summary

### Parts & Inventory
- **Part**: id (unique, never reused), external_pn, name, description, category, unit_of_measure, metadata (JSON)
- **InventoryRecord**: part_id, quantity, location, lot_number
- **Purchase**: supplier, status (draft/ordered/partial/received/cancelled)
- **PurchaseLine**: purchase_id, part_id, qty_ordered, qty_received, unit_cost

### Procedures
- **MasterProcedure**: name, description, current_version_id, status (draft/active/deprecated)
- **ProcedureStep**: procedure_id, order, title, instructions (markdown), required_data_schema (JSON), is_contingency
- **ProcedureVersion**: immutable snapshot of procedure + steps at publish time
- **Kit**: procedure_id, part_id, quantity_required

### Execution
- **ProcedureInstance**: version_id (locked at start), work_order_number, status, timestamps
- **StepExecution**: instance_id, step_number, status, data_captured (JSON), timestamps

### Issues & Risks
- **Issue**: type, status, linked entities (part/procedure/instance), auto-created from NCs
- **Risk**: probability, impact, mitigation plan, can create linked issues

## Development Sequence

1. Foundation (database, migrations, basic CRUD API)
2. Parts & Inventory
3. Procedures (master, versioning, steps, kitting)
4. Execution (instances, step execution, data capture)
5. Issues (manual + NC auto-creation)
6. Risks
7. Datasets & Graphing
8. TUI (full feature parity)
9. Polish (keyboard shortcuts, search, export)

## Non-Goals (For Now)
- User authentication (prep for it, don't implement)
- Multi-instance sync (manual file copy is fine)
- Mobile-specific UI
- Real-time collaboration (refresh to see changes)
- Notifications/alerts

## Commands Reference

```bash
# Setup
uv sync                    # Install dependencies
uv run opal init          # Initialize database

# Development
uv run opal serve         # Start server (http://localhost:8080)
uv run pytest             # Run tests
uv run opal seed          # Populate demo data

# Database
uv run alembic revision --autogenerate -m "message"  # Generate migration
uv run alembic upgrade head                           # Apply migrations
uv run alembic downgrade -1                          # Rollback one migration
```

## Important Context for AI Assistants


### When Working on This Project

1. **Always use Alembic** for database schema changes
2. **Follow US Graphics UI principles** - dense, explicit, functional
3. **Maintain immutability** of published procedure versions
4. **Preserve traceability** - every part movement must be traceable
5. **Use ISO 8601 timestamps** everywhere (never relative times)
6. **Prioritize data tables** over other UI patterns
7. **Test coverage is mandatory** for business logic
8. **No authentication yet** but prepare for it (user_id in all audit trails)

### Code Style
- Use FastAPI for all API routes
- Pydantic models for validation
- SQLAlchemy ORM (never raw SQL)
- Type hints everywhere
- Ruff for linting

### File Organization
- Business logic goes in `/core`
- API routes in `/api`
- Database models in `/db`
- Templates in `/web/templates`
- Tests mirror source structure

### Testing Strategy
- Unit tests for core business logic
- Integration tests for API endpoints
- E2E tests for critical user flows
- Use test fixtures for common data setups
- In-memory SQLite for fast test execution

## Current Status

The project is in active development. Check `./opal/README.md` for quick start instructions and the latest development status. See `./opal.md` for the complete requirements specification.
