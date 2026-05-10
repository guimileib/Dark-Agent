"""Utils package"""

from .ffmpeg_utils import (
    verificar_ffmpeg_instalado,
    verificar_ffprobe_instalado,
    obter_duracao_video,
    obter_resolucao_video,
    formatar_tempo
)

__all__ = [
    'verificar_ffmpeg_instalado',
    'verificar_ffprobe_instalado',
    'obter_duracao_video',
    'obter_resolucao_video',
    'formatar_tempo',
]
