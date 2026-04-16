"""
Path resolution for DarkAgent Pro — works in dev mode AND PyInstaller frozen mode.

Concepts:
- BUNDLE_DIR: where bundled read-only assets live (assets/, config/, estilos_padrao.json)
  - Dev:    G:/DarkAgent/src
  - Frozen: sys._MEIPASS/src  (temp extraction folder)

- APP_DIR: where the executable (or project root) lives — used for mutable data
  - Dev:    G:/DarkAgent
  - Frozen: directory containing DarkAgentLauncher.exe
"""

import sys
import os
from pathlib import Path


def is_frozen() -> bool:
    """Return True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _get_bundle_dir() -> Path:
    """Read-only bundled resources root (contains src/assets, src/config)."""
    if is_frozen():
        return Path(sys._MEIPASS)
    # Dev mode: G:/DarkAgent
    return Path(__file__).resolve().parent.parent.parent


def _get_app_dir() -> Path:
    """Mutable data root — where the .exe lives (or project root in dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


# ── Public path constants ─────────────────────────────────────────────────

BUNDLE_DIR = _get_bundle_dir()
APP_DIR = _get_app_dir()

# Read-only bundled resources
CONFIG_DIR = BUNDLE_DIR / "src" / "config"
ASSETS_DIR = BUNDLE_DIR / "src" / "assets"

# Mutable data directories (next to the .exe or project root)
OUTPUT_DIR = APP_DIR / "output"
CACHE_DIR = APP_DIR / "cache"
MODELS_DIR = APP_DIR / "models"
ACCOUNTS_DIR = APP_DIR / "accounts"
LOGS_DIR = APP_DIR / "logs"

# Mutable config (user settings saved here, not in the bundle)
USER_CONFIG_DIR = APP_DIR / "config"

# Cookies
COOKIES_FILE = APP_DIR / "cookies.txt"

# FFmpeg local directory
FFMPEG_DIR = APP_DIR / "ffmpeg"


def ensure_dirs() -> None:
    """Create all mutable directories if they don't exist."""
    for d in (OUTPUT_DIR, CACHE_DIR, MODELS_DIR, ACCOUNTS_DIR, LOGS_DIR, USER_CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def get_log_path(name: str) -> Path:
    """Return a path for a log file inside LOGS_DIR."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / name


def get_user_config_file() -> Path:
    """Return path to the user-writable config.json."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return USER_CONFIG_DIR / "config.json"
