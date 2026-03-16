#!/bin/sh
# OPAL installer — installs opal-erp Python package via uv, pipx, or pip.
# Usage: curl -fsSL https://raw.githubusercontent.com/CST-100/OPAL/master/install.sh | bash
set -eu

PACKAGE="opal-erp"
MIN_PYTHON="3.11"

# --- Output helpers ---

if [ -t 1 ]; then
    BOLD="\033[1m"
    GREEN="\033[32m"
    YELLOW="\033[33m"
    RED="\033[31m"
    RESET="\033[0m"
else
    BOLD=""
    GREEN=""
    YELLOW=""
    RED=""
    RESET=""
fi

info() {
    printf "${GREEN}info${RESET}: %s\n" "$1"
}

warn() {
    printf "${YELLOW}warn${RESET}: %s\n" "$1" >&2
}

err() {
    printf "${RED}error${RESET}: %s\n" "$1" >&2
    exit 1
}

# --- Python version check ---

check_python() {
    PYTHON=""
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            version="$("$candidate" --version 2>&1 | sed 's/Python //')"
            major="$(echo "$version" | cut -d. -f1)"
            minor="$(echo "$version" | cut -d. -f2)"
            if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                PYTHON="$candidate"
                info "Found Python $version ($candidate)"
                return
            fi
        fi
    done

    if [ -z "$PYTHON" ]; then
        err "Python ${MIN_PYTHON}+ is required but not found. Install Python first: https://www.python.org/downloads/"
    fi
}

# --- Installer detection ---

detect_installer() {
    if command -v uv >/dev/null 2>&1; then
        INSTALLER="uv"
        info "Using uv"
        return
    fi

    if command -v pipx >/dev/null 2>&1; then
        INSTALLER="pipx"
        info "Using pipx"
        return
    fi

    if command -v pip >/dev/null 2>&1 || command -v pip3 >/dev/null 2>&1; then
        INSTALLER="pip"
        info "Using pip"
        return
    fi

    # No installer found — offer to install uv
    info "No package installer found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source the uv env
    if [ -f "$HOME/.local/bin/env" ]; then
        . "$HOME/.local/bin/env"
    fi
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv >/dev/null 2>&1; then
        INSTALLER="uv"
        info "uv installed successfully"
    else
        err "Failed to install uv. Please install uv, pipx, or pip manually."
    fi
}

# --- Install package ---

install_package() {
    info "Installing ${PACKAGE}..."

    case "$INSTALLER" in
        uv)
            uv tool install "$PACKAGE" || uv tool upgrade "$PACKAGE"
            ;;
        pipx)
            pipx install "$PACKAGE" || pipx upgrade "$PACKAGE"
            ;;
        pip)
            PIP_CMD="pip3"
            if ! command -v pip3 >/dev/null 2>&1; then
                PIP_CMD="pip"
            fi
            "$PIP_CMD" install --user "$PACKAGE"
            ;;
    esac
}

# --- PATH check ---

check_path() {
    if command -v opal >/dev/null 2>&1; then
        info "opal is on PATH"
        return
    fi

    warn "opal command not found on PATH"

    SHELL_NAME="$(basename "${SHELL:-/bin/sh}")"
    case "$INSTALLER" in
        uv)
            printf "\n  uv should have added its bin directory to PATH.\n"
            printf "  Try restarting your shell, or add this to your shell config:\n\n"
            printf "    export PATH=\"\$HOME/.local/bin:\$PATH\"\n\n"
            ;;
        pipx)
            printf "\n  Run: pipx ensurepath\n\n"
            ;;
        pip)
            case "$SHELL_NAME" in
                fish)
                    printf "\n  Run: fish_add_path ~/.local/bin\n\n"
                    ;;
                zsh)
                    printf "\n  Add to ~/.zshrc:\n\n    export PATH=\"\$HOME/.local/bin:\$PATH\"\n\n"
                    ;;
                *)
                    printf "\n  Add to ~/.bashrc:\n\n    export PATH=\"\$HOME/.local/bin:\$PATH\"\n\n"
                    ;;
            esac
            ;;
    esac
}

# --- Main ---

main() {
    printf "\n${BOLD}OPAL Installer${RESET}\n\n"

    check_python
    detect_installer
    install_package
    check_path

    printf "\n${BOLD}OPAL installed successfully.${RESET}\n"
    printf "  Get started:\n\n"
    printf "    ${GREEN}opal init${RESET}           # initialize database\n"
    printf "    ${GREEN}opal serve${RESET}          # start server (foreground)\n"
    printf "    ${GREEN}opal serve --daemon${RESET}  # start server (background)\n"
    printf "\n"
}

main
