"""Core package"""

from .downloader import VideoDownloader
from .validator import VideoValidator
from .subtitle_generator import SubtitleGenerator
from .preview_renderer import PreviewRenderer
from .video_editor import VideoEditor
from .clip_analyzer import ClipAnalyzer

# Transcriber pode não estar disponível se torch não funcionar
try:
    from .transcriber import Transcriber
except (ImportError, OSError) as e:
    # Criar versão mock
    class Transcriber:
        """Versão mock do Transcriber (PyTorch não disponível)"""
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "Transcriber não disponível.\n"
                "Python 3.13 não é compatível com PyTorch.\n"
                "Instale Python 3.11 para usar IA."
            )
    
    import logging
    logging.getLogger(__name__).warning(f"Transcriber desabilitado: {e}")

__all__ = [
    'VideoDownloader',
    'VideoValidator',
    'Transcriber',
    'SubtitleGenerator',
    'PreviewRenderer',
    'VideoEditor',
    'ClipAnalyzer'
]
