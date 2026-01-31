import sys
import os
import unittest
from PyQt6.QtWidgets import QApplication

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from core.uploader import TikTokUploader
from ui.widgets.upload_widget import UploadWidget

class TestUploadIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create QApplication instance if it doesn't exist
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def test_uploader_instantiation(self):
        """Test if TikTokUploader initializes correctly"""
        uploader = TikTokUploader()
        self.assertIsNotNone(uploader)
        self.assertEqual(uploader.cookies_path, "cookies.txt")

    def test_widget_instantiation(self):
        """Test if UploadWidget initializes correctly"""
        widget = UploadWidget()
        self.assertIsNotNone(widget)
        # Check if UI elements exist
        self.assertTrue(hasattr(widget, 'file_path'))
        self.assertTrue(hasattr(widget, 'btn_upload'))
        self.assertTrue(hasattr(widget, 'btn_login'))

if __name__ == '__main__':
    unittest.main()
