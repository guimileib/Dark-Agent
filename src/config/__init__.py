"""Config package"""

from .paths import (
    is_frozen, APP_DIR, BUNDLE_DIR,
    CONFIG_DIR, ASSETS_DIR, OUTPUT_DIR, CACHE_DIR, MODELS_DIR,
    ACCOUNTS_DIR, LOGS_DIR, COOKIES_FILE, FFMPEG_DIR,
    ensure_dirs, get_log_path, get_user_config_file,
)
from .settings import settings, Settings

__all__ = [
    'settings', 'Settings',
    'is_frozen', 'APP_DIR', 'BUNDLE_DIR',
    'CONFIG_DIR', 'ASSETS_DIR', 'OUTPUT_DIR', 'CACHE_DIR', 'MODELS_DIR',
    'ACCOUNTS_DIR', 'LOGS_DIR', 'COOKIES_FILE', 'FFMPEG_DIR',
    'ensure_dirs', 'get_log_path', 'get_user_config_file',
]
