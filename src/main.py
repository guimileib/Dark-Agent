"""DarkAgent Pro v2.0 - Entry Point"""

# CRITICAL: Import torch_fix FIRST to resolve DLL loading issues
import sys
import os
from pathlib import Path

# Ensure src directory is on sys.path (launcher.py already does this, but
# main.py may also be launched directly during development).
if getattr(sys, "frozen", False):
    _src_dir = Path(sys._MEIPASS) / "src"
    _bundle_root = Path(sys._MEIPASS)
else:
    _src_dir = Path(__file__).resolve().parent
    _bundle_root = _src_dir.parent

for _p in (str(_src_dir), str(_bundle_root)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Import torch fix module - this MUST be before any other imports that use torch
import torch_fix

import logging
from PyQt6.QtWidgets import QApplication, QMessageBox

# Import path helpers for log location
from config.paths import get_log_path, APP_DIR

# Configurar logging to a predictable location
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(get_log_path('darkagent.log')), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def verificar_dependencias():
    """Verifica se todas as dependências estão instaladas"""
    dependencias_faltando = []

    try:
        import PyQt6
    except ImportError:
        dependencias_faltando.append("PyQt6")

    try:
        import torch
    except ImportError:
        dependencias_faltando.append("torch")

    try:
        import whisper
    except ImportError:
        dependencias_faltando.append("openai-whisper")

    try:
        from PIL import Image
    except ImportError:
        dependencias_faltando.append("pillow")

    if dependencias_faltando:
        logger.error(f"Dependências faltando: {', '.join(dependencias_faltando)}")
        print("\nERRO: Dependências não instaladas!")
        print(f"\nInstale as dependências faltando:")
        print(f"pip install {' '.join(dependencias_faltando)}")
        return False

    return True


def verificar_ferramentas_externas():
    """Verifica se FFmpeg e FFprobe estão instalados"""
    from utils.ffmpeg_utils import verificar_ffmpeg_instalado, verificar_ffprobe_instalado

    avisos = []

    if not verificar_ffmpeg_instalado():
        avisos.append("FFmpeg não encontrado no PATH")

    if not verificar_ffprobe_instalado():
        avisos.append("FFprobe não encontrado no PATH")

    if avisos:
        logger.warning("\n".join(avisos))
        return False

    return True


def main():
    """Função principal"""
    logger.info("=" * 60)
    from src import __version__
    logger.info(f"Iniciando DarkAgent Pro v{__version__}")
    logger.info("=" * 60)

    try:
        logger.info("[boot] checando dependências Python...")
        if not verificar_dependencias():
            if not getattr(sys, "frozen", False):
                input("\nPressione ENTER para sair...")
            sys.exit(1)

        logger.info("[boot] checando FFmpeg/FFprobe...")
        ferramentas_ok = verificar_ferramentas_externas()
        logger.info(f"[boot] ferramentas_ok={ferramentas_ok}")

        if sys.platform == "win32":
            import ctypes
            myappid = 'darkagent.pro.v2.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            logger.info("[boot] AppUserModelID configurado")

        logger.info("[boot] obtendo QApplication...")
        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("DarkAgent Pro")
        app.setApplicationVersion(__version__)

        from PyQt6.QtGui import QIcon
        from config.paths import ASSETS_DIR
        icon_path = ASSETS_DIR / "icon.png"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        if not ferramentas_ok:
            logger.warning("[boot] mostrando aviso de FFmpeg faltando (modal)...")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Ferramentas Faltando")
            msg.setText("FFmpeg e/ou FFprobe não foram encontrados!")
            msg.setInformativeText(
                "Algumas funcionalidades não estarão disponíveis.\n\n"
                "Baixe FFmpeg em: https://ffmpeg.org/download.html"
            )
            msg.exec()
            logger.info("[boot] modal FFmpeg fechado pelo usuário")

        logger.info("[boot] importando MainWindow/SplashScreen...")
        from ui.main_window import MainWindow
        from ui.splash_screen import SplashScreen

        logger.info("[boot] criando SplashScreen...")
        splash = SplashScreen()
        splash.show()

        splash.update_progress(10, "Loading configuration...")
        app.processEvents()

        splash.update_progress(30, "Initializing AI models...")
        app.processEvents()

        splash.update_progress(60, "Loading UI components...")
        app.processEvents()

        logger.info("[boot] instanciando MainWindow...")
        window = MainWindow()
        logger.info("[boot] MainWindow OK")

        splash.update_progress(90, "Starting application...")
        app.processEvents()

        splash.update_progress(100, "Ready!")
        app.processEvents()

        window.show()
        splash.finish(window)

        logger.info("Interface gráfica carregada com sucesso")

        sys.exit(app.exec())

    except SystemExit:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            crash_path = APP_DIR / "logs" / "crash.txt"
            crash_path.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_path, "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass

        logger.error(f"Erro fatal ao iniciar aplicação: {e}\n{tb}")

        try:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Erro Fatal")
            msg.setText("Erro ao iniciar a aplicação!")
            msg.setDetailedText(tb)
            msg.exec()
        except Exception:
            pass

        sys.exit(1)


if __name__ == "__main__":
    main()
