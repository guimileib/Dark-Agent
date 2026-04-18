"""
DarkAgent Pro — Launcher with visible splash/installer UI.

Responsible for:
- Showing a PyQt6 splash window as early as possible (so the user sees something
  immediately after the PyInstaller onefile bundle finishes extracting).
- Ensuring FFmpeg is available; downloads/extracts it in a background QThread,
  updating the splash with a determinate progress bar.
- Handing control over to `main.main()`, which reuses the existing QApplication.
"""

import sys
import os
import logging
import zipfile
import shutil
from pathlib import Path


# ---------------------------------------------------------------------------
# sys.path bootstrap (must run BEFORE importing from config.paths)
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    _SRC_DIR = Path(sys._MEIPASS) / "src"
    _BUNDLE_ROOT = Path(sys._MEIPASS)
else:
    _SRC_DIR = Path(__file__).resolve().parent
    _BUNDLE_ROOT = _SRC_DIR.parent

for _p in (str(_SRC_DIR), str(_BUNDLE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from config.paths import APP_DIR, ASSETS_DIR, FFMPEG_DIR, LOGS_DIR, ensure_dirs  # noqa: E402

ensure_dirs()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(LOGS_DIR / 'launcher.log'), encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("Launcher")


FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


# ---------------------------------------------------------------------------
# FFmpeg detection (no UI — pure logic)
# ---------------------------------------------------------------------------

def check_ffmpeg() -> bool:
    """Check if FFmpeg is available in PATH or in the local ffmpeg/ directory."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True

    local_bin = FFMPEG_DIR / "bin"
    local_ffmpeg = local_bin / "ffmpeg.exe"
    local_ffprobe = local_bin / "ffprobe.exe"

    if local_ffmpeg.exists() and local_ffprobe.exists():
        os.environ["PATH"] += os.pathsep + str(local_bin)
        return True

    return False


# ---------------------------------------------------------------------------
# PyQt6 UI (imported after sys.path setup)
# ---------------------------------------------------------------------------

from PyQt6.QtCore import Qt, QEventLoop, QThread, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QColor, QIcon, QPixmap  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FFmpegInstallerThread(QThread):
    """Downloads and extracts FFmpeg off the main thread."""

    progress = pyqtSignal(int, int, int)  # percent, downloaded_bytes, total_bytes
    status = pyqtSignal(str)
    finished_ok = pyqtSignal(bool, str)  # success, error_message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zip_path = APP_DIR / "ffmpeg_temp.zip"

    def run(self) -> None:  # noqa: C901 — linear flow is clearer than splitting
        try:
            import requests  # local import: keeps launcher startup snappy

            self.status.emit("Baixando FFmpeg...")
            logger.info("Downloading FFmpeg from %s", FFMPEG_URL)

            with requests.get(FFMPEG_URL, stream=True, timeout=30) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(self._zip_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if self.isInterruptionRequested():
                            logger.info("FFmpeg download cancelled by user")
                            self._cleanup_zip()
                            self.finished_ok.emit(False, "Download cancelado pelo usuário.")
                            return

                        if not chunk:
                            continue

                        written = fh.write(chunk)
                        downloaded += written

                        if total_size > 0:
                            pct = int(downloaded / total_size * 100)
                            self.progress.emit(pct, downloaded, total_size)
                        else:
                            # Unknown total — emit indeterminate signal (0, downloaded, 0)
                            self.progress.emit(0, downloaded, 0)

            if self.isInterruptionRequested():
                self._cleanup_zip()
                self.finished_ok.emit(False, "Download cancelado pelo usuário.")
                return

            self.status.emit("Extraindo FFmpeg...")
            logger.info("Extracting FFmpeg...")

            with zipfile.ZipFile(self._zip_path, 'r') as zip_ref:
                names = zip_ref.namelist()
                if not names:
                    raise RuntimeError("Arquivo zip do FFmpeg está vazio.")
                root_folder = names[0].split('/')[0]
                zip_ref.extractall(str(APP_DIR))

            extracted_path = APP_DIR / root_folder
            target_path = FFMPEG_DIR

            if target_path.exists():
                shutil.rmtree(target_path)

            extracted_path.rename(target_path)
            self._cleanup_zip()

            logger.info("FFmpeg setup complete.")
            self.finished_ok.emit(True, "")

        except Exception as exc:  # noqa: BLE001
            logger.error("FFmpeg install failed: %s", exc, exc_info=True)
            self._cleanup_zip()
            self.finished_ok.emit(False, str(exc))

    def _cleanup_zip(self) -> None:
        try:
            if self._zip_path.exists():
                self._zip_path.unlink()
        except OSError:
            pass


class LauncherSplash(QWidget):
    """Frameless splash shown by the launcher during FFmpeg setup."""

    def __init__(self):
        super().__init__(None)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(600, 350)

        # Taskbar icon / window icon
        icon_png = ASSETS_DIR / "icon.png"
        icon_ico = ASSETS_DIR / "icon.ico"
        if icon_ico.exists():
            self.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_png.exists():
            self.setWindowIcon(QIcon(str(icon_png)))

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

        # Background panel (rounded, gradient)
        self._bg = QWidget(self)
        self._bg.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #080c16, stop:0.5 #0f172a, stop:1 #0c1425);
                border-radius: 20px;
                border: 1px solid rgba(59, 130, 246, 0.15);
            }
        """)
        self._bg.setGeometry(0, 0, self.width(), self.height())
        self._bg.lower()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 40)
        layout.setSpacing(18)

        # Top bar (minimize button)
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.btn_minimize = QPushButton("─")
        self.btn_minimize.setFixedSize(30, 30)
        self.btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minimize.clicked.connect(self.showMinimized)
        self.btn_minimize.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #475569;
                border: none;
                font-size: 16px;
                font-weight: bold;
                border-radius: 15px;
            }
            QPushButton:hover {
                color: #e2e8f0;
                background-color: rgba(59, 130, 246, 0.15);
            }
        """)
        top_bar.addWidget(self.btn_minimize)
        layout.addLayout(top_bar)

        # Optional app icon
        if icon_png.exists():
            icon_label = QLabel()
            pixmap = QPixmap(str(icon_png)).scaled(
                72, 72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_label.setPixmap(pixmap)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(icon_label)

        # Title
        self.logo_label = QLabel("DarkAgent Pro")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setStyleSheet("""
            color: #f8fafc;
            font-size: 28px;
            font-weight: 800;
            font-family: 'Segoe UI', sans-serif;
            letter-spacing: -0.5px;
            background: transparent;
            border: none;
        """)
        layout.addWidget(self.logo_label)

        self.subtitle_label = QLabel("AI Video Studio")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setStyleSheet("""
            color: #60a5fa;
            font-size: 13px;
            font-weight: 600;
            font-family: 'Segoe UI', sans-serif;
            letter-spacing: 2px;
            background: transparent;
            border: none;
        """)
        layout.addWidget(self.subtitle_label)

        layout.addStretch()

        # Status + progress
        self.status_label = QLabel("Verificando dependências...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(
            "color: #94a3b8; font-size: 12px; font-weight: 500; "
            "letter-spacing: 0.3px; background: transparent; border: none;"
        )
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: rgba(30, 41, 59, 0.5);
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:0.5 #6366f1, stop:1 #8b5cf6);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

    # -- public API ---------------------------------------------------------

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)
        QApplication.processEvents()

    def set_progress(self, percent: int) -> None:
        # Clamp to [0, 100] just in case.
        self.progress.setValue(max(0, min(100, percent)))
        QApplication.processEvents()

    def set_indeterminate(self, indeterminate: bool) -> None:
        if indeterminate:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
        QApplication.processEvents()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _format_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def _install_ffmpeg_with_ui(splash: LauncherSplash) -> bool:
    """Run the FFmpeg installer in a QThread, updating the splash. Returns True on success."""
    thread = FFmpegInstallerThread()

    result = {"success": False, "error": ""}

    def on_progress(percent: int, downloaded: int, total: int) -> None:
        if total > 0:
            splash.set_indeterminate(False)
            splash.set_progress(percent)
            splash.set_status(
                f"Baixando FFmpeg... {percent}% "
                f"({_format_bytes(downloaded)} / {_format_bytes(total)})"
            )
        else:
            splash.set_indeterminate(True)
            splash.set_status(f"Baixando FFmpeg... ({_format_bytes(downloaded)})")

    def on_status(message: str) -> None:
        if message.startswith("Extraindo"):
            splash.set_indeterminate(True)
        splash.set_status(message)

    def on_finished(success: bool, error: str) -> None:
        result["success"] = success
        result["error"] = error

    thread.progress.connect(on_progress)
    thread.status.connect(on_status)
    thread.finished_ok.connect(on_finished)

    # When the user closes the splash, request cancellation of the download.
    original_close = splash.closeEvent

    def close_event(event) -> None:
        if thread.isRunning():
            thread.requestInterruption()
        original_close(event)

    splash.closeEvent = close_event  # type: ignore[assignment]

    # Use a local event loop so the UI stays responsive while we wait
    # for the installer thread to finish.
    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    thread.start()
    loop.exec()

    # Ensure the QThread object itself has fully cleaned up.
    thread.wait()

    # Restore progress bar to determinate for next phase.
    splash.set_indeterminate(False)
    splash.set_progress(100)

    if not result["success"]:
        if result["error"] and "cancelado" not in result["error"].lower():
            QMessageBox.critical(
                splash,
                "Erro ao instalar FFmpeg",
                f"Falha ao baixar/instalar o FFmpeg:\n\n{result['error']}",
            )
        return False

    # Make sure the freshly installed ffmpeg is on PATH.
    local_bin = FFMPEG_DIR / "bin"
    os.environ["PATH"] += os.pathsep + str(local_bin)
    return True


def main() -> None:
    """Launcher entry point."""
    # Create the QApplication as early as possible so the splash appears
    # immediately after PyInstaller finishes self-extraction.
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DarkAgent Pro")

    icon_png = ASSETS_DIR / "icon.png"
    icon_ico = ASSETS_DIR / "icon.ico"
    if icon_ico.exists():
        app.setWindowIcon(QIcon(str(icon_ico)))
    elif icon_png.exists():
        app.setWindowIcon(QIcon(str(icon_png)))

    splash = LauncherSplash()
    splash.show()
    app.processEvents()

    try:
        splash.set_status("Verificando dependências...")
        splash.set_progress(5)

        if not check_ffmpeg():
            splash.set_status("FFmpeg não encontrado.")
            app.processEvents()

            answer = QMessageBox.question(
                splash,
                "Dependência faltando",
                "O FFmpeg é necessário para este aplicativo, mas não foi encontrado.\n\n"
                "Deseja baixar e instalar automaticamente?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if answer == QMessageBox.StandardButton.Yes:
                if not _install_ffmpeg_with_ui(splash):
                    logger.error("FFmpeg installation failed or was cancelled.")
                    splash.close()
                    sys.exit(1)
            else:
                QMessageBox.warning(
                    splash,
                    "Aviso",
                    "O aplicativo pode não funcionar corretamente sem o FFmpeg.",
                )

        splash.set_status("Carregando DarkAgent...")
        splash.set_progress(100)
        app.processEvents()

        logger.info("Launching main application...")

        # Close launcher splash right before handing off. main.main() will
        # create its own (more detailed) splash during UI bootstrap.
        splash.close()
        app.processEvents()

        from main import main as app_main
        app_main()

    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.critical("Launcher crashed: %s", exc, exc_info=True)
        try:
            QMessageBox.critical(
                None,
                "Erro no Launcher",
                f"Ocorreu um erro inesperado:\n\n{exc}",
            )
        finally:
            sys.exit(1)


if __name__ == "__main__":
    main()
