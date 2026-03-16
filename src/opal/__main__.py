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


def _ensure_initialized() -> None:
    """Auto-run init_database() before serving."""
    from opal.config import get_active_settings
    from opal.db.base import get_engine, init_database

    settings = get_active_settings()
    settings.ensure_directories()
    engine = get_engine()
    init_database(engine)


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the OPAL web server."""
    _setup_project(args)

    from opal.config import get_active_settings, get_default_data_dir

    settings = get_active_settings()
    host = args.host or settings.host
    port = args.port or settings.port

    if args.daemon:
        from opal.daemon import start_daemon

        # Init database before daemon start
        _ensure_initialized()

        data_dir = get_default_data_dir()
        try:
            pid = start_daemon(host, port, data_dir)
            print(f"OPAL server running (PID {pid}) at http://{host}:{port}")
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        import uvicorn

        _ensure_initialized()

        print(f"Starting OPAL server at http://{host}:{port}")
        uvicorn.run(
            "opal.api.app:app",
            host=host,
            port=port,
            reload=settings.debug,
        )


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop the OPAL daemon."""
    from opal.config import get_default_data_dir
    from opal.daemon import get_daemon_status, stop_daemon

    data_dir = get_default_data_dir()
    status = get_daemon_status(data_dir)

    if not status.running:
        print("OPAL server is not running.")
        return

    print(f"Stopping OPAL server (PID {status.pid})...")
    stopped = stop_daemon(data_dir)
    if stopped:
        print("Server stopped.")
    else:
        print("Failed to stop server.", file=sys.stderr)
        sys.exit(1)


def cmd_restart(args: argparse.Namespace) -> None:
    """Restart the OPAL daemon."""
    from opal.config import get_active_settings, get_default_data_dir
    from opal.daemon import get_daemon_status, start_daemon, stop_daemon

    _setup_project(args)

    data_dir = get_default_data_dir()
    status = get_daemon_status(data_dir)

    if status.running:
        print(f"Stopping OPAL server (PID {status.pid})...")
        stop_daemon(data_dir)

    _ensure_initialized()

    settings = get_active_settings()
    host = args.host or settings.host
    port = args.port or settings.port

    try:
        pid = start_daemon(host, port, data_dir)
        print(f"OPAL server running (PID {pid}) at http://{host}:{port}")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_status(args: argparse.Namespace) -> None:
    """Show OPAL server status."""
    from opal import __version__
    from opal.config import get_active_settings, get_default_data_dir
    from opal.daemon import format_uptime, get_daemon_status, get_log_file

    data_dir = get_default_data_dir()
    status = get_daemon_status(data_dir)
    settings = get_active_settings()

    print("OPAL Server Status")
    print("==================")

    if status.running:
        print(f"  Status     RUNNING")
        print(f"  PID        {status.pid}")
        print(f"  URL        http://{settings.host}:{settings.port}")
        print(f"  Uptime     {format_uptime(status.uptime_seconds)}")
    else:
        print(f"  Status     STOPPED")

    print(f"  Data dir   {data_dir}")
    print(f"  Log file   {get_log_file(data_dir)}")
    print(f"  Version    {__version__}")


def cmd_logs(args: argparse.Namespace) -> None:
    """Tail the OPAL log file."""
    from opal.config import get_default_data_dir
    from opal.daemon import get_log_file, tail_logs

    data_dir = get_default_data_dir()
    log_file = get_log_file(data_dir)
    tail_logs(log_file, lines=args.lines, follow=args.follow)


def cmd_config(args: argparse.Namespace) -> None:
    """Manage OPAL configuration."""
    from opal.config import config_get, config_set, config_show, get_config_file

    if args.config_action == "show":
        settings = config_show()
        max_key = max(len(k) for k in settings)
        for key, value in settings.items():
            print(f"  {key:<{max_key}}  {value}")
    elif args.config_action == "get":
        value = config_get(args.key)
        if value is None:
            print(f"Unknown setting: {args.key}", file=sys.stderr)
            sys.exit(1)
        print(value)
    elif args.config_action == "set":
        config_set(args.key, args.value)
        print(f"Set {args.key} = {args.value}")
    elif args.config_action == "path":
        print(get_config_file())


def cmd_update(args: argparse.Namespace) -> None:
    """Self-update OPAL via pip/uv/pipx."""
    import shutil

    from opal import __version__
    from opal.config import get_default_data_dir
    from opal.daemon import get_daemon_status, stop_daemon

    data_dir = get_default_data_dir()
    was_running = get_daemon_status(data_dir).running
    old_version = __version__

    if was_running:
        print(f"Stopping OPAL server...")
        stop_daemon(data_dir)

    # Detect installer and upgrade
    installer = _detect_installer()
    print(f"Upgrading opal-erp via {installer}...")

    try:
        import subprocess

        if installer == "uv":
            subprocess.run(["uv", "tool", "upgrade", "opal-erp"], check=True)
        elif installer == "pipx":
            subprocess.run(["pipx", "upgrade", "opal-erp"], check=True)
        else:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "opal-erp"],
                check=True,
            )
    except subprocess.CalledProcessError as e:
        print(f"Upgrade failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Run migrations
    print("Running database migrations...")
    try:
        _ensure_initialized()
        print("Database up to date.")
    except Exception as e:
        print(f"Migration warning: {e}", file=sys.stderr)

    # Restart if was running
    if was_running:
        from opal.config import get_active_settings
        from opal.daemon import start_daemon

        settings = get_active_settings()
        try:
            pid = start_daemon(settings.host, settings.port, data_dir)
            print(f"OPAL server running (PID {pid}) at http://{settings.host}:{settings.port}")
        except RuntimeError as e:
            print(f"Restart failed: {e}", file=sys.stderr)

    # Try to read new version (may still be old in this process)
    print(f"Update complete (was {old_version}).")


def _detect_installer() -> str:
    """Detect how OPAL was installed (uv, pipx, or pip)."""
    import shutil

    opal_path = shutil.which("opal") or ""

    # Check for uv tool directory patterns
    if "/.local/share/uv/" in opal_path or "/uv/" in opal_path:
        if shutil.which("uv"):
            return "uv"

    # Check for pipx directory patterns
    if "/.local/pipx/" in opal_path or "/pipx/" in opal_path:
        if shutil.which("pipx"):
            return "pipx"

    # Check if uv is available (user might have installed via uv pip)
    if shutil.which("uv"):
        return "uv"

    if shutil.which("pipx"):
        return "pipx"

    return "pip"


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
    try:
        from opal.tui import run_tui
    except ImportError:
        print("TUI requires 'textual'. Install with: pip install opal-erp[tui]")
        sys.exit(1)

    from opal.config import get_active_settings

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
    serve_parser.add_argument(
        "--daemon", "-d", action="store_true", help="Run as background daemon"
    )
    add_project_args(serve_parser)
    serve_parser.set_defaults(func=cmd_serve)

    # stop command
    stop_parser = subparsers.add_parser("stop", help="Stop the background server")
    stop_parser.set_defaults(func=cmd_stop)

    # restart command
    restart_parser = subparsers.add_parser("restart", help="Restart the background server")
    restart_parser.add_argument("--host", type=str, help="Host to bind to")
    restart_parser.add_argument("--port", type=int, help="Port to bind to")
    add_project_args(restart_parser)
    restart_parser.set_defaults(func=cmd_restart)

    # status command
    status_parser = subparsers.add_parser("status", help="Show server status")
    status_parser.set_defaults(func=cmd_status)

    # logs command
    logs_parser = subparsers.add_parser("logs", help="Tail the server log file")
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="Follow log output"
    )
    logs_parser.add_argument(
        "-n", "--lines", type=int, default=50, help="Number of lines to show (default: 50)"
    )
    logs_parser.set_defaults(func=cmd_logs)

    # config command
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_action")

    config_subparsers.add_parser("show", help="Show all settings")

    config_get_parser = config_subparsers.add_parser("get", help="Get a setting")
    config_get_parser.add_argument("key", help="Setting name")

    config_set_parser = config_subparsers.add_parser("set", help="Set a setting")
    config_set_parser.add_argument("key", help="Setting name")
    config_set_parser.add_argument("value", help="Setting value")

    config_subparsers.add_parser("path", help="Show config file path")

    config_parser.set_defaults(func=cmd_config)

    # update command
    update_parser = subparsers.add_parser("update", help="Update OPAL to latest version")
    update_parser.set_defaults(func=cmd_update)

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

    # config command without subcommand -> show
    if args.command == "config" and not hasattr(args, "config_action"):
        args.config_action = "show"
    if args.command == "config" and args.config_action is None:
        args.config_action = "show"

    args.func(args)


if __name__ == "__main__":
    main()
