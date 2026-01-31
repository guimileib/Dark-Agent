"""DarkAgent Pro v2.0 - Entry Point"""

# CRITICAL: Import torch_fix FIRST to resolve DLL loading issues
import sys
import os
from pathlib import Path

# Add src directory to path AND parent directory for proper imports
src_dir = Path(__file__).parent
project_root = src_dir.parent

# Add both to sys.path for flexible imports
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import torch fix module - this MUST be before any other imports that use torch
import torch_fix

import logging
from PyQt6.QtWidgets import QApplication, QMessageBox

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('darkagent.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def verificar_dependencias():
    """Verifica se todas as dependências estão instaladas"""
    dependencias_faltando = []
    
    # PyQt6
    try:
        import PyQt6
    except ImportError:
        dependencias_faltando.append("PyQt6")
    
    # Torch FIRST (before whisper, which depends on it)
    try:
        import torch
    except ImportError:
        dependencias_faltando.append("torch")
    
    # Whisper
    try:
        import whisper
    except ImportError:
        dependencias_faltando.append("openai-whisper")
    
    # PIL
    try:
        from PIL import Image
    except ImportError:
        dependencias_faltando.append("pillow")
    
    if dependencias_faltando:
        logger.error(f"Dependências faltando: {', '.join(dependencias_faltando)}")
        print("\n❌ ERRO: Dependências não instaladas!")
        print(f"\nInstale as dependências faltando:")
        print(f"pip install {' '.join(dependencias_faltando)}")
        return False
    
    return True


def verificar_ferramentas_externas():
    """Verifica se FFmpeg e FFprobe estão instalados"""
    try:
        from utils.ffmpeg_utils import verificar_ffmpeg_instalado, verificar_ffprobe_instalado
    except ImportError:
        from src.utils.ffmpeg_utils import verificar_ffmpeg_instalado, verificar_ffprobe_instalado
    
    avisos = []
    
    if not verificar_ffmpeg_instalado():
        avisos.append("FFmpeg não encontrado no PATH")
    
    if not verificar_ffprobe_instalado():
        avisos.append("FFprobe não encontrado no PATH")
    
    if avisos:
        logger.warning("\n".join(avisos))
        print("\n⚠️  AVISO: Ferramentas externas não encontradas!")
        for aviso in avisos:
            print(f"  - {aviso}")
        print("\nBaixe FFmpeg em: https://ffmpeg.org/download.html")
        
        return False
    
    return True


def main():
    """Função principal"""
    logger.info("="*60)
    logger.info("Iniciando DarkAgent Pro v2.0")
    logger.info("="*60)
    
    # Verificar dependências Python
    if not verificar_dependencias():
        input("\nPressione ENTER para sair...")
        sys.exit(1)
    
    # Verificar ferramentas externas
    ferramentas_ok = verificar_ferramentas_externas()
    
    # Configurar AppUserModelID para o ícone aparecer na barra de tarefas
    import ctypes
    myappid = 'darkagent.pro.v2.0' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # Criar aplicação Qt
    app = QApplication(sys.argv)
    app.setApplicationName("DarkAgent Pro")
    app.setApplicationVersion("2.0")
    
    # Set Application Icon (Global)
    from PyQt6.QtGui import QIcon
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # Avisar sobre ferramentas faltando
    if not ferramentas_ok:
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Ferramentas Faltando")
        msg.setText("FFmpeg e/ou FFprobe não foram encontrados!")
        msg.setInformativeText(
            "Algumas funcionalidades não estarão disponíveis.\n\n"
            "Baixe FFmpeg em: https://ffmpeg.org/download.html"
        )
        msg.exec()
    
    # Criar e mostrar janela principal
    try:
        from ui.main_window import MainWindow
        from ui.splash_screen import SplashScreen
        from PyQt6.QtCore import QTimer, Qt
        import time
        
        # Show Splash Screen
        splash = SplashScreen()
        splash.show()
        
        
        # Simulate loading steps (faster)
        splash.update_progress(10, "Loading configuration...")
        app.processEvents()
        
        splash.update_progress(30, "Initializing AI models...")
        app.processEvents()
        
        splash.update_progress(60, "Loading UI components...")
        app.processEvents()
        
        # Create Main Window (this might take a bit if it loads heavy stuff)
        window = MainWindow()
        
        splash.update_progress(90, "Starting application...")
        app.processEvents()
        
        splash.update_progress(100, "Ready!")
        app.processEvents()
        
        window.show()
        splash.finish(window)
        
        logger.info("Interface gráfica carregada com sucesso")
        
        # Executar aplicação
        sys.exit(app.exec())
        
    except Exception as e:
        import traceback
        with open("crash.txt", "w") as f:
            f.write(traceback.format_exc())
            
        logger.error(f"Erro fatal ao iniciar aplicação: {e}", exc_info=True)
        
        # Mostrar erro na GUI
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("Erro Fatal")
        msg.setText("Erro ao iniciar a aplicação!")
        msg.setDetailedText(str(e))
        msg.exec()
        
        sys.exit(1)


if __name__ == "__main__":
    main()
