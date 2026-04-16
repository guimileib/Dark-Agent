import sys
import os
import logging
import zipfile
import shutil
import ctypes
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# Determine the real application directory (where the .exe lives or project root)
# ---------------------------------------------------------------------------

def _get_app_dir() -> Path:
    """Return the directory where the .exe lives (frozen) or project root (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_DIR = _get_app_dir()
LOGS_DIR = APP_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging to a predictable location
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(LOGS_DIR / 'launcher.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Launcher")

# Constants
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_DIR_NAME = "ffmpeg"

# Windows MessageBox constants
MB_OK = 0x00
MB_YESNO = 0x04
MB_ICONERROR = 0x10
MB_ICONWARNING = 0x30
MB_ICONINFORMATION = 0x40
IDYES = 6


def is_admin():
    """Check if the script is running with administrative privileges."""
    if sys.platform != "win32":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def show_message_box(title, message, style=0):
    """Show a native Windows message box (no-op on non-Windows)."""
    if sys.platform != "win32":
        print(f"[{title}] {message}")
        return 0
    return ctypes.windll.user32.MessageBoxW(0, message, title, style)


def check_ffmpeg():
    """Check if FFmpeg is available in PATH or local directory."""
    # Check system PATH
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True

    # Check local directory (relative to the app, not CWD)
    local_ffmpeg = APP_DIR / FFMPEG_DIR_NAME / "bin" / "ffmpeg.exe"
    local_ffprobe = APP_DIR / FFMPEG_DIR_NAME / "bin" / "ffprobe.exe"

    if local_ffmpeg.exists() and local_ffprobe.exists():
        os.environ["PATH"] += os.pathsep + str(local_ffmpeg.parent)
        return True

    return False


def download_ffmpeg():
    """Download and extract FFmpeg."""
    try:
        logger.info("Downloading FFmpeg...")

        zip_path = APP_DIR / "ffmpeg_temp.zip"

        response = requests.get(FFMPEG_URL, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        last_logged_pct = -1

        with open(zip_path, "wb") as file:
            for data in response.iter_content(chunk_size=1024):
                size = file.write(data)
                downloaded += size
                if total_size > 0:
                    pct = int(downloaded / total_size * 100)
                    if pct % 10 == 0 and pct != last_logged_pct:
                        logger.info(f"FFmpeg download: {pct}%")
                        last_logged_pct = pct

        logger.info("Extracting FFmpeg...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            names = zip_ref.namelist()
            if not names:
                raise RuntimeError("Downloaded zip is empty")
            root_folder = names[0].split('/')[0]
            zip_ref.extractall(str(APP_DIR))

        extracted_path = APP_DIR / root_folder
        target_path = APP_DIR / FFMPEG_DIR_NAME

        if target_path.exists():
            shutil.rmtree(target_path)

        extracted_path.rename(target_path)

        zip_path.unlink()

        logger.info("FFmpeg setup complete.")
        return True

    except Exception as e:
        logger.error(f"Failed to download/install FFmpeg: {e}")
        show_message_box("Error", f"Failed to download FFmpeg:\n{e}", MB_ICONERROR)
        return False


def setup_environment():
    """Ensure environment is ready for the main application."""
    if not check_ffmpeg():
        response = show_message_box(
            "Missing Dependency",
            "FFmpeg is required for this application but was not found.\n\n"
            "Would you like to download and install it automatically?",
            MB_YESNO | MB_ICONINFORMATION
        )

        if response == IDYES:
            if not download_ffmpeg():
                return False
            local_bin = APP_DIR / FFMPEG_DIR_NAME / "bin"
            os.environ["PATH"] += os.pathsep + str(local_bin)
        else:
            show_message_box(
                "Warning",
                "The application may not function correctly without FFmpeg.",
                MB_ICONWARNING
            )

    return True


def main():
    """Launcher entry point."""
    try:
        # Determine the src directory for imports
        if getattr(sys, "frozen", False):
            # Frozen: src/ lives inside _MEIPASS
            src_dir = Path(sys._MEIPASS) / "src"
            bundle_root = Path(sys._MEIPASS)
        else:
            # Dev: launcher.py is inside src/
            src_dir = Path(__file__).resolve().parent
            bundle_root = src_dir.parent

        # Add to sys.path for imports
        for p in (str(src_dir), str(bundle_root)):
            if p not in sys.path:
                sys.path.insert(0, p)

        # Setup Environment (FFmpeg check)
        if not setup_environment():
            logger.error("Environment setup failed.")
            sys.exit(1)

        # Launch Main App
        logger.info("Launching main application...")

        from main import main as app_main
        app_main()

    except Exception as e:
        logger.critical(f"Launcher crashed: {e}", exc_info=True)
        show_message_box("Launcher Error", f"An unexpected error occurred:\n{e}", MB_ICONERROR)
        sys.exit(1)


if __name__ == "__main__":
    main()
