# OPAL installer for Windows — downloads the latest release binary.
# Usage: irm https://raw.githubusercontent.com/CST-100/OPAL/master/install.ps1 | iex
$ErrorActionPreference = "Stop"

$Repo = "CST-100/OPAL"
$ApiUrl = "https://api.github.com/repos/$Repo/releases/latest"
$InstallDir = Join-Path $env:LOCALAPPDATA "OPAL"
$InstallPath = Join-Path $InstallDir "opal.exe"

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

# --- Platform detection ---

function Get-Platform {
    $Arch = $env:PROCESSOR_ARCHITECTURE
    switch ($Arch) {
        "AMD64"  { return "x86_64" }
        "x86"    { Write-Err "32-bit Windows is not supported" }
        "ARM64"  { Write-Err "ARM64 Windows is not currently supported" }
        default  { Write-Err "Unsupported architecture: $Arch" }
    }
}

# --- Release lookup ---

function Find-DownloadUrl {
    param([string]$AssetPattern)

    Write-Info "Fetching latest release from GitHub..."

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    try {
        $Release = Invoke-RestMethod -Uri $ApiUrl -Headers @{ Accept = "application/vnd.github.v3+json" }
    } catch {
        Write-Err "Failed to fetch release info from GitHub: $_"
    }

    $script:Tag = $Release.tag_name
    if (-not $Tag) {
        Write-Err "Could not determine latest release tag"
    }
    Write-Info "Latest release: $Tag"

    $Asset = $Release.assets | Where-Object { $_.name -like "*$AssetPattern*" } | Select-Object -First 1
    if (-not $Asset) {
        Write-Err "No release asset found matching '$AssetPattern'"
    }

    return $Asset.browser_download_url
}

# --- Install ---

function Install-Binary {
    param([string]$Url, [string]$AssetName)

    Write-Info "Downloading ${AssetName}..."

    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    $TmpFile = Join-Path $env:TEMP "opal-install-$([System.IO.Path]::GetRandomFileName()).exe"

    try {
        Invoke-WebRequest -Uri $Url -OutFile $TmpFile -UseBasicParsing
    } catch {
        if (Test-Path $TmpFile) { Remove-Item $TmpFile -Force }
        Write-Err "Download failed: $_"
    }

    # Sanity check: file should be at least 1 KB
    $Size = (Get-Item $TmpFile).Length
    if ($Size -lt 1024) {
        Remove-Item $TmpFile -Force
        Write-Err "Downloaded file is too small ($Size bytes) -- something went wrong"
    }

    Move-Item -Path $TmpFile -Destination $InstallPath -Force

    Write-Info "Installed to $InstallPath"
}

# --- PATH check ---

function Update-PathAdvice {
    $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($UserPath -and $UserPath.Split(";") -contains $InstallDir) {
        return
    }

    Write-Warn "$InstallDir is not in your PATH"
    Write-Host ""
    Write-Host "  Run this to add it permanently:"
    Write-Host ""
    Write-Host "    [Environment]::SetEnvironmentVariable('Path', `"$InstallDir;`" + [Environment]::GetEnvironmentVariable('Path', 'User'), 'User')" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Then restart your terminal."
    Write-Host ""
}

# --- Main ---

function Install-Opal {
    Write-Host ""
    Write-Host "OPAL Installer" -ForegroundColor White
    Write-Host ""

    $Arch = Get-Platform
    Write-Info "Detected platform: windows $Arch"

    $AssetName = "opal-windows-${Arch}.exe"
    $DownloadUrl = Find-DownloadUrl -AssetPattern $AssetName

    Install-Binary -Url $DownloadUrl -AssetName $AssetName
    Update-PathAdvice

    Write-Host ""
    Write-Host "OPAL $Tag installed successfully." -ForegroundColor White
    Write-Host "  Run " -NoNewline
    Write-Host "opal" -ForegroundColor Green -NoNewline
    Write-Host " to start."
    Write-Host ""
}

Install-Opal
