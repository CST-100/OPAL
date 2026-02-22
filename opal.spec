# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OPAL standalone binary.

Build with:
    pyinstaller opal.spec

Output: dist/opal (or dist/opal.exe on Windows)
"""

import os
from pathlib import Path

block_cipher = None

# Paths
src_dir = Path("src/opal")
migrations_dir = Path("migrations")

# Collect all data files that need to be bundled
datas = []

# Web templates and static files
datas.append((str(src_dir / "web" / "templates"), "opal/web/templates"))
datas.append((str(src_dir / "web" / "static"), "opal/web/static"))

# TUI styles
datas.append((str(src_dir / "tui" / "styles.tcss"), "opal/tui"))

# Launcher styles
datas.append((str(src_dir / "launcher.tcss"), "opal"))

# Alembic migrations (for programmatic upgrades)
datas.append((str(migrations_dir), "migrations"))

# Alembic config
datas.append(("alembic.ini", "."))

a = Analysis(
    [str(src_dir / "launcher.py")],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "opal",
        "opal.api",
        "opal.api.app",
        "opal.core",
        "opal.db",
        "opal.db.models",
        "opal.db.base",
        "opal.web",
        "opal.tui",
        "opal.mcp",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "textual",
        "textual.app",
        "textual.css",
        "sqlalchemy",
        "sqlalchemy.dialects.sqlite",
        "alembic",
        "jinja2",
        "httpx",
        "pydantic",
        "pydantic_settings",
        "aiofiles",
        "segno",
        "packaging",
        "packaging.version",
        "yaml",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="opal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
