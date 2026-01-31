import sys
import os

print("Starting import test...")
try:
    print("Importing tiktok_uploader...")
    from tiktok_uploader.upload import upload_video
    print("tiktok_uploader imported successfully.")
except Exception as e:
    print(f"Failed to import tiktok_uploader: {e}")

try:
    sys.path.append(os.path.join(os.getcwd(), 'src'))
    print("Importing UploadWidget...")
    from ui.widgets.upload_widget import UploadWidget
    print("UploadWidget imported successfully.")
except Exception as e:
    print(f"Failed to import UploadWidget: {e}")
