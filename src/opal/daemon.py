"""OPAL daemon lifecycle management — start, stop, status, logs."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DaemonStatus:
    """Current state of the OPAL daemon."""

    running: bool
    pid: int | None = None
    port: int | None = None
    uptime_seconds: float | None = None


def get_pid_file(data_dir: Path) -> Path:
    return data_dir / "opal.pid"


def get_log_file(data_dir: Path) -> Path:
    return data_dir / "opal.log"


def read_pid_file(pid_file: Path) -> int | None:
    """Read and validate a PID file. Returns PID or None if invalid/missing."""
    try:
        text = pid_file.read_text().strip()
        return int(text)
    except (FileNotFoundError, ValueError):
        return None


def is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # process exists but we can't signal it


def start_daemon(host: str, port: int, data_dir: Path) -> int:
    """Spawn uvicorn as a detached background process.

    Returns the PID of the spawned process.
    """
    pid_file = get_pid_file(data_dir)
    log_file = get_log_file(data_dir)

    # Check if already running
    existing_pid = read_pid_file(pid_file)
    if existing_pid is not None and is_process_alive(existing_pid):
        raise RuntimeError(f"OPAL is already running (PID {existing_pid})")

    # Ensure data dir exists
    data_dir.mkdir(parents=True, exist_ok=True)

    log_fh = open(log_file, "a")  # noqa: SIM115

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "opal.api.app:app",
        "--host",
        host,
        "--port",
        str(port),
    ]

    kwargs: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        kwargs["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)

    # Write PID file
    pid_file.write_text(str(proc.pid))

    # Brief poll to confirm process is alive
    time.sleep(0.5)
    if proc.poll() is not None:
        pid_file.unlink(missing_ok=True)
        raise RuntimeError(
            f"Server exited immediately (code {proc.returncode}). Check {log_file}"
        )

    return proc.pid


def stop_daemon(data_dir: Path) -> bool:
    """Stop the running daemon. Returns True if a process was stopped."""
    pid_file = get_pid_file(data_dir)
    pid = read_pid_file(pid_file)

    if pid is None:
        return False

    if not is_process_alive(pid):
        pid_file.unlink(missing_ok=True)
        return False

    # Send termination signal
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_TERMINATE = 0x0001
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            kernel32.TerminateProcess(handle, 1)
            kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGTERM)

    # Wait up to 5 seconds for graceful shutdown
    for _ in range(50):
        if not is_process_alive(pid):
            break
        time.sleep(0.1)
    else:
        # Force kill
        if sys.platform != "win32":
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    pid_file.unlink(missing_ok=True)
    return True


def get_daemon_status(data_dir: Path) -> DaemonStatus:
    """Get the current daemon status, cleaning up stale PID files."""
    pid_file = get_pid_file(data_dir)
    pid = read_pid_file(pid_file)

    if pid is None:
        return DaemonStatus(running=False)

    if not is_process_alive(pid):
        # Stale PID file
        pid_file.unlink(missing_ok=True)
        return DaemonStatus(running=False)

    # Calculate uptime from PID file mtime
    try:
        mtime = pid_file.stat().st_mtime
        uptime = time.time() - mtime
    except OSError:
        uptime = None

    return DaemonStatus(running=True, pid=pid, uptime_seconds=uptime)


def tail_logs(log_file: Path, lines: int = 50, follow: bool = False) -> None:
    """Print last N lines of the log file, optionally following new output."""
    if not log_file.exists():
        print(f"No log file found at {log_file}")
        return

    # Read last N lines
    with open(log_file) as f:
        all_lines = f.readlines()

    for line in all_lines[-lines:]:
        print(line, end="")

    if not follow:
        return

    # Follow mode: poll for new content
    try:
        with open(log_file) as f:
            # Seek to end
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line, end="", flush=True)
                else:
                    time.sleep(0.3)
    except KeyboardInterrupt:
        pass


def format_uptime(seconds: float | None) -> str:
    """Format seconds into a human-readable uptime string."""
    if seconds is None:
        return "unknown"
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    elif m > 0:
        return f"{m}m {s:02d}s"
    else:
        return f"{s}s"
