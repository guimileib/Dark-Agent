
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from core.downloader import VideoDownloader

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def test_download(url, output_dir="test_downloads"):
    downloader = VideoDownloader(Path(output_dir))
    print(f"Testing download for: {url}")
    
    success, path, strategy = downloader.download(url, "720p")
    
    if success:
        print(f"SUCCESS! Strategy: {strategy}")
        print(f"File: {path}")
    else:
        print("FAILURE: All strategies failed.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Default test URL (South Park clip or similar if possible, otherwise a generic safe test)
        # Using a YouTube video as a safe default for first test
        url = "https://www.youtube.com/watch?v=BaW_jenozKc" 
    
    test_download(url)
