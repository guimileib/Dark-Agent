import sys
import os
from pathlib import Path
import traceback

# Add src to path
src_dir = Path("src").absolute()
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

print(f"Python Path: {sys.path}")

try:
    print("Importing settings...")
    from config import settings
    print(f"Settings loaded. Assets dir: {settings.assets_dir}")
    
    print("Importing MainWindow...")
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    
    from ui.main_window import MainWindow
    print("MainWindow imported. Instantiating...")
    window = MainWindow()
    print("MainWindow instantiated.")
    
except Exception:
    traceback.print_exc()
