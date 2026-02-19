import sys
import logging
from pathlib import Path

# Add src to path
sys.path.append(str(Path.cwd() / "src"))

# Setup logging
logging.basicConfig(level=logging.INFO)

from core.downloader import VideoDownloader

def test_southpark_download():
    url = "https://www.southparkstudios.com.br/episodios/2znij2/south-park-bons-tempos-com-armas-temporada-8-ep-1"
    output_dir = Path("output/test_downloads")
    
    print(f"Testing download from: {url}")
    print(f"Output directory: {output_dir}")
    
    downloader = VideoDownloader(output_dir)
    sucesso, caminho, estrategia = downloader.download(url, "720p")
    
    if sucesso:
        print(f"SUCCESS! Video downloaded to: {caminho}")
        print(f"Strategy used: {estrategia}")
        return True
    else:
        print("FAILURE! Download failed.")
        return False

if __name__ == "__main__":
    if test_southpark_download():
        sys.exit(0)
    else:
        sys.exit(1)
