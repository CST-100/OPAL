# OPAL installer for Windows — installs opal-erp Python package via uv, pipx, or pip.
# Usage: irm https://raw.githubusercontent.com/CST-100/OPAL/master/install.ps1 | iex
$ErrorActionPreference = "Stop"

$Package = "opal-erp"
$MinPython = "3.11"

# --- Output helpers ---

function Write-Info {
    param([string]$Message)
    Write-Host "info: " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warn {
    param([string]$Message)
    Write-Host "warn: " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Err {
    param([string]$Message)
    Write-Host "error: " -ForegroundColor Red -NoNewline
    Write-Host $Message
    exit 1
}

# --- Python version check ---

function Test-Python {
    foreach ($candidate in @("python3", "python")) {
        try {
            $output = & $candidate --version 2>&1
            if ($output -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 11) {
                    Write-Info "Found $output ($candidate)"
                    return $candidate
                }
            }
        } catch {
            continue
        }
    }
    Write-Err "Python ${MinPython}+ is required but not found. Install from https://www.python.org/downloads/"
}

# --- Installer detection ---

function Get-Installer {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Info "Using uv"
        return "uv"
    }
    if (Get-Command pipx -ErrorAction SilentlyContinue) {
        Write-Info "Using pipx"
        return "pipx"
    }
    if (Get-Command pip -ErrorAction SilentlyContinue) {
        Write-Info "Using pip"
        return "pip"
    }

    # No installer found — try to install uv
    Write-Info "No package installer found. Installing uv..."
    try {
        irm https://astral.sh/uv/install.ps1 | iex
    } catch {
        Write-Err "Failed to install uv. Please install uv, pipx, or pip manually."
    }

    # Refresh PATH
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Info "uv installed successfully"
        return "uv"
    }

    Write-Err "Failed to install uv. Please install uv, pipx, or pip manually."
}

# --- Install package ---

function Install-Package {
    param([string]$Installer)

    Write-Info "Installing ${Package}..."

    switch ($Installer) {
        "uv" {
            try {
                uv tool install $Package
            } catch {
                uv tool upgrade $Package
            }
        }
        "pipx" {
            try {
                pipx install $Package
            } catch {
                pipx upgrade $Package
            }
        }
        "pip" {
            pip install --user $Package
        }
    }
}

# --- PATH check ---

function Test-OpalPath {
    if (Get-Command opal -ErrorAction SilentlyContinue) {
        Write-Info "opal is on PATH"
        return
    }

    Write-Warn "opal command not found on PATH"
    Write-Host ""
    Write-Host "  Restart your terminal, or check that the install directory is in your PATH."
    Write-Host ""
}

# --- Main ---

function Install-Opal {
    Write-Host ""
    Write-Host "OPAL Installer" -ForegroundColor White
    Write-Host ""

    $python = Test-Python
    $installer = Get-Installer
    Install-Package -Installer $installer
    Test-OpalPath

    Write-Host ""
    Write-Host "OPAL installed successfully." -ForegroundColor White
    Write-Host "  Get started:"
    Write-Host ""
    Write-Host "    opal init            " -ForegroundColor Green -NoNewline
    Write-Host "# initialize database"
    Write-Host "    opal serve           " -ForegroundColor Green -NoNewline
    Write-Host "# start server (foreground)"
    Write-Host "    opal serve --daemon  " -ForegroundColor Green -NoNewline
    Write-Host "# start server (background)"
    Write-Host ""
}

Install-Opal
