
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from PyQt6.QtCore import QCoreApplication

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

# Import torch_fix to avoid DLL errors
try:
    import torch_fix
except ImportError:
    pass

# Create QCoreApplication to handle signals
app = QCoreApplication(sys.argv)

from ui.main_window import BatchDownloadThread

class TestBatchDownload(unittest.TestCase):
    
    @patch('ui.main_window.VideoDownloader')
    def test_batch_download_success(self, MockDownloader):
        # Setup mock
        downloader_instance = MockDownloader.return_value
        downloader_instance.download.return_value = (True, Path("video.mp4"), "mock_strategy")
        
        config = {
            "urls": ["http://test1.com", "http://test2.com"],
            "qualidade": "720p",
            "pasta": Path(".")
        }
        
        thread = BatchDownloadThread(config)
        
        # Track results
        results = []
        def handle_concluido(res):
            results.append(res)
            
        thread.concluido.connect(handle_concluido)
        thread.run()
        
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(len(res["sucesso"]), 2)
        self.assertEqual(len(res["falha"]), 0)
        self.assertEqual(res["sucesso"][0][0], "http://test1.com")
        self.assertEqual(res["sucesso"][1][0], "http://test2.com")

    @patch('ui.main_window.VideoDownloader')
    def test_batch_download_partial_failure(self, MockDownloader):
        # Setup mock
        downloader_instance = MockDownloader.return_value
        # First call success, second failure
        downloader_instance.download.side_effect = [
            (True, Path("video1.mp4"), "mock_strategy"),
            (False, None, "none")
        ]
        
        config = {
            "urls": ["http://success.com", "http://fail.com"],
            "qualidade": "720p",
            "pasta": Path(".")
        }
        
        thread = BatchDownloadThread(config)
        
        results = []
        thread.concluido.connect(lambda res: results.append(res))
        thread.run()
        
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(len(res["sucesso"]), 1)
        self.assertEqual(len(res["falha"]), 1)
        self.assertEqual(res["sucesso"][0][0], "http://success.com")
        self.assertEqual(res["falha"][0][0], "http://fail.com")

if __name__ == '__main__':
    unittest.main()
