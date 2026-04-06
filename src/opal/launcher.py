"""OPAL Launcher — Textual TUI for server lifecycle management."""

from __future__ import annotations

import signal
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Label, RichLog, Static

from opal import __version__
from opal.config import get_active_settings, get_default_data_dir


class ServerPanel(Static):
    """Displays server status information."""

    def compose(self) -> ComposeResult:
        yield Label("OPAL Server", id="server-panel-title")
        with Horizontal(classes="info-row"):
            yield Label("Status:", classes="info-label")
            yield Label("STOPPED", id="status-value", classes="stopped")
        with Horizontal(classes="info-row"):
            yield Label("Port:", classes="info-label")
            yield Label("8080", id="port-value", classes="info-value")
        with Horizontal(classes="info-row"):
            yield Label("URL:", classes="info-label")
            yield Label("http://localhost:8080", id="url-value", classes="info-value")
        with Horizontal(classes="info-row"):
            yield Label("Data:", classes="info-label")
            yield Label(str(get_default_data_dir()), id="data-value", classes="info-value")


class OpalLauncher(App):
    """TUI launcher for managing the OPAL server."""

    TITLE = "OPAL"
    SUB_TITLE = "Operations, Procedures, Assets, Logistics"
    CSS_PATH = (
        Path(getattr(sys, "_MEIPASS", ""), "opal", "launcher.tcss")
        if getattr(sys, "frozen", False)
        else "launcher.tcss"
    )

    BINDINGS = [
        Binding("s", "start_server", "Start", show=True),
        Binding("x", "stop_server", "Stop", show=True),
        Binding("r", "restart_server", "Restart", show=True),
        Binding("o", "open_browser", "Open Browser", show=True),
        Binding("u", "check_updates", "Check Updates", show=True),
        Binding("q", "quit_app", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._server_process: subprocess.Popen | None = None
        self._log_thread: Thread | None = None
        self._stopping = False
        self._pending_update: dict | None = None

    def compose(self) -> ComposeResult:
        yield ServerPanel(id="server-panel")
        with Horizontal(id="controls"):
            yield Button("Start", id="btn-start", variant="success")
            yield Button("Stop", id="btn-stop", variant="error", disabled=True)
            yield Button("Restart", id="btn-restart", disabled=True)
            yield Button("Open in Browser", id="btn-browser", disabled=True)
        with Vertical(id="log-panel"):
            yield Label("Log", id="log-panel-title")
            yield RichLog(id="log-view", wrap=True, markup=False)
        with Horizontal(id="footer-bar"):
            yield Label(f"v{__version__}", id="version-label")
            yield Button("Check for Updates", id="btn-update")
            yield Button("Quit", id="btn-quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._log(f"OPAL Launcher v{__version__}")
        self._log(f"Data directory: {get_default_data_dir()}")
        settings = get_active_settings()
        self._update_port_display(settings.port)

    def _log(self, message: str) -> None:
        """Write a timestamped message to the log widget."""
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            log_view = self.query_one("#log-view", RichLog)
            log_view.write(f"{ts} {message}")
        except Exception:
            pass

    def _update_status(self, status: str) -> None:
        """Update the status display."""
        label = self.query_one("#status-value", Label)
        label.remove_class("running", "stopped", "starting")
        if status == "running":
            label.update("\u25cf RUNNING")
            label.add_class("running")
        elif status == "starting":
            label.update("\u25cf STARTING")
            label.add_class("starting")
        else:
            label.update("\u25cf STOPPED")
            label.add_class("stopped")

    def _update_port_display(self, port: int) -> None:
        """Update the port and URL display."""
        self.query_one("#port-value", Label).update(str(port))
        self.query_one("#url-value", Label).update(f"http://localhost:{port}")

    def _set_button_states(self, running: bool) -> None:
        """Toggle button enabled/disabled based on server state."""
        self.query_one("#btn-start", Button).disabled = running
        self.query_one("#btn-stop", Button).disabled = not running
        self.query_one("#btn-restart", Button).disabled = not running
        self.query_one("#btn-browser", Button).disabled = not running

    def _ensure_initialized(self) -> bool:
        """Ensure data directory and database exist. Returns True if ready."""
        data_dir = get_default_data_dir()

        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            self._log(f"Data directory ready: {data_dir}")
        except OSError as e:
            self._log(f"ERROR: Cannot create data directory: {e}")
            return False

        # Check if database exists; if not, initialize
        settings = get_active_settings()
        db_path = settings.database_url.replace("sqlite:///", "")
        if not Path(db_path).exists():
            self._log("Initializing database (first run)...")
            try:
                settings.ensure_directories()
                from opal.db.base import get_engine, init_database

                engine = get_engine()
                init_database(engine)
                self._log("Database initialized successfully.")
            except Exception as e:
                self._log(f"ERROR: Database initialization failed: {e}")
                return False
        else:
            # Run migrations on existing DB in case of upgrade
            self._log("Checking for database migrations...")
            try:
                from opal.db.base import get_engine, init_database

                engine = get_engine()
                init_database(engine)
                self._log("Database up to date.")
            except Exception as e:
                self._log(f"WARNING: Migration check failed: {e}")

        return True

    def _start_server(self) -> None:
        """Start the uvicorn server as a subprocess."""
        if self._server_process is not None:
            self._log("Server is already running.")
            return

        if not self._ensure_initialized():
            return

        self._update_status("starting")
        self._set_button_states(True)
        self._stopping = False

        settings = get_active_settings()
        port = settings.port
        host = settings.host

        self._log(f"Starting server on {host}:{port}...")

        if getattr(sys, "frozen", False):
            # Running as PyInstaller bundle — start uvicorn in-process on a thread
            self._log_thread = Thread(
                target=self._run_uvicorn_inprocess,
                args=(host, port),
                daemon=True,
            )
            self._log_thread.start()
        else:
            try:
                self._server_process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "opal.api.app:app",
                        "--host",
                        host,
                        "--port",
                        str(port),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except FileNotFoundError:
                self._log("ERROR: Could not find Python executable to start server.")
                self._update_status("stopped")
                self._set_button_states(False)
                return
            except Exception as e:
                self._log(f"ERROR: Failed to start server: {e}")
                self._update_status("stopped")
                self._set_button_states(False)
                return

            # Stream output in a background thread
            self._log_thread = Thread(target=self._stream_output, daemon=True)
            self._log_thread.start()

    def _run_uvicorn_inprocess(self, host: str, port: int) -> None:
        """Run uvicorn in the current process (for PyInstaller bundles)."""
        import uvicorn

        self._uvicorn_server: uvicorn.Server | None = None
        try:
            config = uvicorn.Config(
                "opal.api.app:create_app",
                factory=True,
                host=host,
                port=port,
                log_level="info",
            )
            server = uvicorn.Server(config)
            self._uvicorn_server = server
            self.call_from_thread(self._log, f"Server starting on http://{host}:{port}")
            self.call_from_thread(self._update_status, "running")
            server.run()
        except Exception as e:
            self.call_from_thread(self._log, f"ERROR: Server failed: {e}")
        finally:
            self._uvicorn_server = None
            self.call_from_thread(self._on_server_exited, 0)

    def _stream_output(self) -> None:
        """Read server stdout/stderr and post to the log widget."""
        proc = self._server_process
        if proc is None or proc.stdout is None:
            return

        startup_detected = False
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line:
                    self.call_from_thread(self._log, line)
                    if not startup_detected and "Application startup complete" in line:
                        startup_detected = True
                        self.call_from_thread(self._update_status, "running")
        except ValueError:
            # stdout closed
            pass

        # Process exited
        exit_code = proc.wait()
        self.call_from_thread(self._on_server_exited, exit_code)

    def _on_server_exited(self, exit_code: int) -> None:
        """Handle the server process exiting."""
        self._server_process = None
        self._update_status("stopped")
        self._set_button_states(False)
        if self._stopping:
            self._log("Server stopped.")
        elif exit_code != 0:
            self._log(f"Server exited with code {exit_code}.")
        else:
            self._log("Server exited.")

    def _stop_server(self) -> None:
        """Stop the running server process."""
        self._stopping = True

        # In-process uvicorn (frozen mode)
        uvicorn_server = getattr(self, "_uvicorn_server", None)
        if uvicorn_server is not None:
            self._log("Stopping server...")
            uvicorn_server.should_exit = True
            return

        # Subprocess mode
        if self._server_process is None:
            self._log("Server is not running.")
            return

        self._log("Stopping server...")

        try:
            if sys.platform == "win32":
                self._server_process.terminate()
            else:
                self._server_process.send_signal(signal.SIGTERM)

            # Wait up to 5 seconds for graceful shutdown
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log("Server did not stop gracefully, forcing...")
                self._server_process.kill()
                self._server_process.wait(timeout=3)
        except Exception as e:
            self._log(f"Error stopping server: {e}")

    # --- Actions (key bindings) ---

    def action_start_server(self) -> None:
        self._start_server()

    def action_stop_server(self) -> None:
        self._stop_server()

    def action_restart_server(self) -> None:
        self._log("Restarting server...")
        self._stop_server()
        # Wait for process cleanup then start again
        self.set_timer(1.0, self._start_server)

    def action_open_browser(self) -> None:
        if self._server_process is None:
            self._log("Server is not running.")
            return
        settings = get_active_settings()
        url = f"http://localhost:{settings.port}"
        self._log(f"Opening {url} in browser...")
        webbrowser.open(url)

    def action_check_updates(self) -> None:
        if self._pending_update:
            self._log("Applying pending update...")
            self.run_worker(self._apply_update())
        else:
            self._log("Checking for updates...")
            self.run_worker(self._check_updates_async())

    async def _check_updates_async(self) -> None:
        """Check GitHub releases for a newer version."""
        from opal.updater import check_for_update, is_frozen

        try:
            result = await check_for_update()
        except Exception as e:
            self._log(f"Update check failed: {e}")
            return

        if result is None:
            self._log(f"Up to date (v{__version__}).")
            return

        tag = result["tag"]
        self._log(f"Update available: v{tag} (current: v{__version__})")
        body = result.get("body", "")
        if body:
            for line in body.splitlines()[:5]:
                self._log(f"  {line}")

        if is_frozen() and result.get("asset_url"):
            self._log("Binary update available. Press 'U' to install.")
            self._pending_update = result
            self.notify(
                f"Update available: v{tag} — press U to install",
                title="OPAL Update",
                severity="information",
            )
        else:
            self._log("Download from: https://github.com/CST-100/OPAL/releases/latest")
            self.notify(
                f"Update available: v{tag}",
                title="OPAL Update",
                severity="information",
            )

    async def _apply_update(self) -> None:
        """Download and install a pending binary update."""
        from opal.updater import download_update, replace_binary

        update = self._pending_update
        if not update or not update.get("asset_url"):
            self._log("No pending update to apply.")
            return

        self._pending_update = None
        asset_url = update["asset_url"]
        tag = update["tag"]

        # Stop server first
        if self._server_process is not None:
            self._log("Stopping server for update...")
            self._stop_server()

        self._log(f"Downloading v{tag}...")

        def on_progress(downloaded: int, total: int) -> None:
            if total > 0:
                pct = int(downloaded / total * 100)
                self.call_from_thread(self._log, f"  Download: {pct}% ({downloaded}/{total} bytes)")

        try:
            tmp_path = await download_update(asset_url, progress_callback=on_progress)
        except Exception as e:
            self._log(f"Download failed: {e}")
            return

        self._log("Installing update...")
        try:
            replace_binary(tmp_path)
        except Exception as e:
            self._log(f"Install failed: {e}")
            tmp_path.unlink(missing_ok=True)
            return

        self._log(f"Update to v{tag} installed. Restart to apply.")
        self.notify(
            "Update installed. Restart to apply.",
            title="OPAL Update",
            severity="information",
        )

    def action_quit_app(self) -> None:
        if self._server_process is not None:
            self._log("Shutting down server before exit...")
            self._stop_server()
        self.exit()

    # --- Button handlers ---

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-start":
            self._start_server()
        elif button_id == "btn-stop":
            self._stop_server()
        elif button_id == "btn-restart":
            self.action_restart_server()
        elif button_id == "btn-browser":
            self.action_open_browser()
        elif button_id == "btn-update":
            self.action_check_updates()
        elif button_id == "btn-quit":
            self.action_quit_app()


def main() -> None:
    """Entry point for the OPAL launcher."""
    app = OpalLauncher()
    app.run()


if __name__ == "__main__":
    main()
