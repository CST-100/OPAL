"""OPAL CLI entry point."""

import argparse
import sys
from pathlib import Path


def _setup_project(args: argparse.Namespace) -> None:
    """Configure project settings from CLI args."""
    from opal.config import configure_for_project
    from opal.project import get_project_config

    project = None
    database_path = None

    # Explicit database path takes precedence
    if hasattr(args, "database") and args.database:
        database_path = Path(args.database)
    elif hasattr(args, "project") and args.project:
        project = get_project_config(Path(args.project))
    else:
        # Auto-detect project from current directory
        project = get_project_config()

    if project or database_path:
        settings = configure_for_project(project=project, database_path=database_path)
        if project:
            print(f"Using project: {project.name} ({project.project_dir})")
        print(f"Database: {settings.database_url}")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the OPAL web server."""
    import uvicorn

    from opal.config import get_active_settings

    # Configure project first
    _setup_project(args)

    settings = get_active_settings()
    host = args.host or settings.host
    port = args.port or settings.port

    print(f"Starting OPAL server at http://{host}:{port}")

    uvicorn.run(
        "opal.api.app:app",
        host=host,
        port=port,
        reload=settings.debug,
    )


def cmd_migrate(args: argparse.Namespace) -> None:
    """Run database migrations."""
    import os
    import subprocess

    from opal.config import get_active_settings

    # Find project root by looking for alembic.ini
    opal_dir = Path(__file__).resolve().parent.parent.parent
    if not (opal_dir / "alembic.ini").exists():
        # Try one level up (installed package case)
        opal_dir = opal_dir.parent
    if not (opal_dir / "alembic.ini").exists():
        # Fall back to current working directory
        opal_dir = Path.cwd()

    # Pass database URL to alembic subprocess via environment
    settings = get_active_settings()
    env = os.environ.copy()
    env["OPAL_DATABASE_URL"] = settings.database_url

    if args.action == "upgrade":
        revision = args.revision or "head"
        subprocess.run(
            ["alembic", "upgrade", revision],
            cwd=opal_dir,
            env=env,
            check=True,
        )
    elif args.action == "downgrade":
        revision = args.revision or "-1"
        subprocess.run(
            ["alembic", "downgrade", revision],
            cwd=opal_dir,
            env=env,
            check=True,
        )
    elif args.action == "generate":
        if not args.message:
            print("Error: --message required for generate", file=sys.stderr)
            sys.exit(1)
        subprocess.run(
            ["alembic", "revision", "--autogenerate", "-m", args.message],
            cwd=opal_dir,
            env=env,
            check=True,
        )
    elif args.action == "current":
        subprocess.run(
            ["alembic", "current"],
            cwd=opal_dir,
            env=env,
            check=True,
        )
    elif args.action == "history":
        subprocess.run(
            ["alembic", "history"],
            cwd=opal_dir,
            env=env,
            check=True,
        )


def cmd_seed(args: argparse.Namespace) -> None:
    """Populate database with demo data."""
    # Configure project first
    _setup_project(args)

    from opal.db.base import SessionLocal
    from opal.db.models import User

    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(User).first():
            print("Database already has data. Skipping seed.")
            return

        # Create demo users
        users = [
            User(name="Alice", email="alice@example.com", is_admin=True),
            User(name="Bob", email="bob@example.com"),
            User(name="Charlie", email="charlie@example.com"),
        ]
        db.add_all(users)
        db.commit()

        print(f"Created {len(users)} demo users")

        # TODO: Add more seed data for parts, procedures, etc.

    finally:
        db.close()


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize OPAL (create directories, initialize/migrate database)."""
    from opal.config import get_active_settings
    from opal.db.base import get_engine, init_database

    # Configure project first
    _setup_project(args)

    settings = get_active_settings()
    settings.ensure_directories()

    print("Created data directories")

    try:
        engine = get_engine()
        init_database(engine)
        print("Database initialized")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        print("If developing, you can use: opal migrate upgrade")
        sys.exit(1)


def cmd_tui(args: argparse.Namespace) -> None:
    """Launch the TUI (Terminal User Interface)."""
    from opal.config import get_active_settings
    from opal.tui import run_tui

    # Configure project first
    _setup_project(args)

    settings = get_active_settings()
    api_url = args.api_url or f"http://{settings.host}:{settings.port}"

    print(f"Connecting to OPAL API at {api_url}")
    print("Press 'q' to quit, '?' for help")

    run_tui(api_url=api_url)


def cmd_mcp(args: argparse.Namespace) -> None:
    """Start the MCP server for Claude Code integration."""
    import asyncio

    # Configure project first
    _setup_project(args)

    from opal.mcp.server import run_server

    print("Starting OPAL MCP server...", file=sys.stderr)
    asyncio.run(run_server())


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="opal",
        description="OPAL - Operations, Procedures, Assets, Logistics",
    )
    from opal import __version__
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Common project arguments
    def add_project_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--project",
            type=str,
            help="Project directory (auto-detects opal.project.yaml)",
        )
        p.add_argument(
            "--database",
            type=str,
            help="Explicit database path (overrides project)",
        )

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the web server")
    serve_parser.add_argument("--host", type=str, help="Host to bind to")
    serve_parser.add_argument("--port", type=int, help="Port to bind to")
    add_project_args(serve_parser)
    serve_parser.set_defaults(func=cmd_serve)

    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Database migrations")
    migrate_parser.add_argument(
        "action",
        choices=["upgrade", "downgrade", "generate", "current", "history"],
        help="Migration action",
    )
    migrate_parser.add_argument("--revision", type=str, help="Target revision")
    migrate_parser.add_argument("--message", "-m", type=str, help="Migration message")
    migrate_parser.set_defaults(func=cmd_migrate)

    # seed command
    seed_parser = subparsers.add_parser("seed", help="Seed demo data")
    add_project_args(seed_parser)
    seed_parser.set_defaults(func=cmd_seed)

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize OPAL")
    add_project_args(init_parser)
    init_parser.set_defaults(func=cmd_init)

    # tui command
    tui_parser = subparsers.add_parser("tui", help="Launch the TUI")
    tui_parser.add_argument(
        "--api-url",
        type=str,
        help="OPAL API URL (default: http://127.0.0.1:8000)",
    )
    add_project_args(tui_parser)
    tui_parser.set_defaults(func=cmd_tui)

    # mcp command
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="Start MCP server for Claude Code integration",
    )
    add_project_args(mcp_parser)
    mcp_parser.set_defaults(func=cmd_mcp)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
