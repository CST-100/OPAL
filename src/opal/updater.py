"""OPAL auto-updater — download and replace binary from GitHub releases."""

from __future__ import annotations

import os
import platform
import stat
import sys
import tempfile
from pathlib import Path

import httpx

from opal import __version__

GITHUB_RELEASES_URL = "https://api.github.com/repos/CST-100/OPAL/releases/latest"
GITHUB_HEADERS = {"Accept": "application/vnd.github.v3+json"}


def is_frozen() -> bool:
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def get_current_binary() -> Path | None:
    """Get the path to the currently running binary, if frozen."""
    if is_frozen():
        return Path(sys.executable)
    return None


def _detect_asset_pattern() -> str:
    """Build a filename pattern to match the right release asset.

    Returns a lowercase substring that should appear in the asset filename.
    E.g. "opal-macos-arm64", "opal-linux-x86_64", "opal-windows-x86_64.exe"
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize OS names
    if system == "darwin":
        os_name = "macos"
    elif system == "windows":
        os_name = "windows"
    else:
        os_name = "linux"

    # Normalize architecture
    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine

    return f"opal-{os_name}-{arch}"


async def check_for_update() -> dict | None:
    """Check GitHub for a newer release.

    Returns:
        Dict with 'tag', 'current', 'body', 'asset_url', 'asset_name' if
        an update is available, or None if up to date.
    """
    from packaging.version import Version

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(GITHUB_RELEASES_URL, headers=GITHUB_HEADERS)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

    tag = data.get("tag_name", "").lstrip("v")
    if not tag:
        return None

    try:
        latest = Version(tag)
        current = Version(__version__)
    except Exception:
        return None

    if latest <= current:
        return None

    # Find the matching binary asset
    asset_pattern = _detect_asset_pattern()
    asset_url = None
    asset_name = None

    for asset in data.get("assets", []):
        name = asset.get("name", "").lower()
        if asset_pattern in name:
            asset_url = asset.get("browser_download_url")
            asset_name = asset.get("name")
            break

    return {
        "tag": tag,
        "current": __version__,
        "body": data.get("body", ""),
        "asset_url": asset_url,
        "asset_name": asset_name,
    }


async def download_update(
    asset_url: str,
    progress_callback=None,
) -> Path:
    """Download a release asset to a temporary file.

    Args:
        asset_url: Direct download URL for the binary asset.
        progress_callback: Optional callable(bytes_downloaded, total_bytes).

    Returns:
        Path to the downloaded temporary file.
    """
    tmp_fd = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp", prefix="opal-update-")  # noqa: SIM115
    tmp_path = Path(tmp_fd.name)
    tmp_fd.close()

    try:
        async with (
            httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client,
            client.stream("GET", asset_url) as resp,
        ):
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(tmp_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return tmp_path


def replace_binary(new_binary: Path) -> Path:
    """Replace the current binary with the downloaded one.

    Strategy: rename current → .bak, move new into place, chmod +x.

    Args:
        new_binary: Path to the downloaded replacement binary.

    Returns:
        Path to the installed binary.

    Raises:
        RuntimeError: If not running as a frozen binary.
    """
    current = get_current_binary()
    if current is None:
        raise RuntimeError("Cannot replace binary: not running as a frozen executable.")

    backup = current.with_suffix(current.suffix + ".bak")

    # Remove old backup if it exists
    backup.unlink(missing_ok=True)

    # Rename current → backup
    current.rename(backup)

    try:
        # Move new binary into place
        new_binary.rename(current)
    except Exception:
        # Restore from backup on failure
        if backup.exists() and not current.exists():
            backup.rename(current)
        raise

    # Make executable on Unix
    if sys.platform != "win32":
        current.chmod(current.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return current


def restart_process() -> None:
    """Replace the current process with a fresh invocation of the binary.

    Uses os.execv to seamlessly restart without spawning a child process.
    """
    os.execv(sys.executable, [sys.executable] + sys.argv[1:])
