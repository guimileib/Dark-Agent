import sys
import os
import logging
import zipfile
import shutil
import ctypes
import requests
from pathlib import Path
from tqdm import tqdm

# Configure logging for the launcher
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('launcher.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Launcher")

# Constants
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_DIR_NAME = "ffmpeg"

def is_admin():
    """Check if the script is running with administrative privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def show_message_box(title, message, style=0):
    """
    Show a native Windows message box.
    Styles:
    0 : OK
    1 : OK | Cancel
    4 : Yes | No
    Icon styles can be added (e.g., | 0x40 for Information, | 0x30 for Warning)
    Returns the button clicked (6=Yes, 7=No, 1=OK, 2=Cancel)
    """
    return ctypes.windll.user32.MessageBoxW(0, message, title, style)

def check_ffmpeg():
    """Check if FFmpeg is available in PATH or local directory."""
    # Check system PATH
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True
    
    # Check local directory
    local_ffmpeg = Path(os.getcwd()) / FFMPEG_DIR_NAME / "bin" / "ffmpeg.exe"
    local_ffprobe = Path(os.getcwd()) / FFMPEG_DIR_NAME / "bin" / "ffprobe.exe"
    
    if local_ffmpeg.exists() and local_ffprobe.exists():
        # Add to PATH for this session
        os.environ["PATH"] += os.pathsep + str(local_ffmpeg.parent)
        return True
        
    return False

def download_ffmpeg():
    """Download and extract FFmpeg."""
    try:
        logger.info("Downloading FFmpeg...")
        
        # Create temp file for zip
        zip_path = Path("ffmpeg_temp.zip")
        
        # Download with progress bar
        response = requests.get(FFMPEG_URL, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(zip_path, "wb") as file, tqdm(
            desc="Downloading FFmpeg",
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in response.iter_content(chunk_size=1024):
                size = file.write(data)
                bar.update(size)
                
        logger.info("Extracting FFmpeg...")
        
        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Get the root folder name in the zip (usually ffmpeg-version-essentials_build)
            root_folder = zip_ref.namelist()[0].split('/')[0]
            zip_ref.extractall(".")
            
        # Rename to standard 'ffmpeg' folder
        extracted_path = Path(root_folder)
        target_path = Path(FFMPEG_DIR_NAME)
        
        if target_path.exists():
            shutil.rmtree(target_path)
            
        extracted_path.rename(target_path)
        
        # Cleanup
        zip_path.unlink()
        
        logger.info("FFmpeg setup complete.")
        return True
        
    except Exception as e:
        logger.error(f"Failed to download/install FFmpeg: {e}")
        show_message_box("Error", f"Failed to download FFmpeg:\n{e}", 0x10) # 0x10 = Critical Icon
        return False

def setup_environment():
    """Ensure environment is ready for the main application."""
    # 1. Check FFmpeg
    if not check_ffmpeg():
        # Ask user to download
        response = show_message_box(
            "Missing Dependency",
            "FFmpeg is required for this application but was not found.\n\nWould you like to download and install it automatically?",
            4 | 0x40 # Yes/No | Info Icon
        )
        
        if response == 6: # Yes
            if not download_ffmpeg():
                return False
            # Add to PATH after download
            local_bin = Path(os.getcwd()) / FFMPEG_DIR_NAME / "bin"
            os.environ["PATH"] += os.pathsep + str(local_bin)
        else:
            show_message_box(
                "Warning", 
                "The application may not function correctly without FFmpeg.",
                0x30 # Warning Icon
            )
            
    return True

def main():
    """Launcher entry point."""
    try:
        # Ensure src is in path
        current_dir = Path(__file__).parent
        project_root = current_dir.parent
        
        if str(current_dir) not in sys.path:
            sys.path.insert(0, str(current_dir))
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
            
        # Setup Environment
        if not setup_environment():
            logger.error("Environment setup failed.")
            sys.exit(1)
            
        # Launch Main App
        logger.info("Launching main application...")
        
        # Import here to avoid loading heavy libs before checks
        try:
            # Try importing as a module first
            from main import main as app_main
        except ImportError:
            # Fallback for when running from src directly
            from src.main import main as app_main
            
        app_main()
        
    except Exception as e:
        logger.critical(f"Launcher crashed: {e}", exc_info=True)
        show_message_box("Launcher Error", f"An unexpected error occurred:\n{e}", 0x10)
        sys.exit(1)

if __name__ == "__main__":
    main()
