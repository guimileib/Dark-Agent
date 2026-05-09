"""Detecção e seleção do encoder de vídeo do FFmpeg em runtime.

Detecta encoders por hardware (NVENC, QSV) através de um probe real:
roda um encode null de 1 frame e checa returncode. `ffmpeg -encoders`
LISTA encoders compilados, mas não diz se eles funcionam de fato — uma
GTX 1650 com driver desatualizado, por exemplo, lista `h264_nvenc` mas
falha na inicialização da sessão.

API pública:
- `select_encoder()` — retorna nome do encoder ativo respeitando settings
- `get_video_encoder_args(crf_equiv)` — args `-c:v ...` prontos pra cmd
- `get_active_encoder_label()` — string curta pra log/UI ("NVENC", etc.)

TODO: aplicar nos caminhos frios também (`adicionar_logo`,
`redimensionar_video`, `cortar_video`) num follow-up.
"""

import logging
import subprocess
import sys
from typing import Optional, List

logger = logging.getLogger(__name__)


# Ordem de preferência quando settings.video_encoder == "auto".
# NVENC primeiro (GeForce/Quadro/Tesla), QSV segundo (Intel iGPU),
# AMF terceiro (AMD), x264 como fallback CPU final.
_AUTO_ORDER = ("h264_nvenc", "h264_qsv", "h264_amf", "libx264")

# Mapeia chaves amigáveis (que ficam em settings) para o encoder real.
_ALIAS = {
    "auto":   None,              # usa _AUTO_ORDER
    "nvenc":  "h264_nvenc",
    "qsv":    "h264_qsv",
    "amf":    "h264_amf",
    "cpu":    "libx264",
    "x264":   "libx264",
}

# Cache do probe — uma vez por processo (probe custa ~1-3s na primeira call).
_probe_cache: dict = {}
_selected_encoder: Optional[str] = None


def _probe(name: str) -> bool:
    """Testa se um encoder funciona rodando um null encode de 1 frame.

    Retorna True se ffmpeg termina com returncode 0. Resultado é cacheado.
    libx264 é considerado sempre disponível (ffmpeg base sempre traz).
    """
    if name in _probe_cache:
        return _probe_cache[name]

    if name == "libx264":
        _probe_cache[name] = True
        return True

    sp_kw: dict = {}
    if sys.platform == "win32":
        sp_kw["creationflags"] = subprocess.CREATE_NO_WINDOW

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=size=128x128:rate=10:duration=0.1",
        "-c:v", name,
        "-f", "null", "-",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL, **sp_kw,
        )
        ok = result.returncode == 0
        if not ok:
            stderr_tail = (result.stderr or "")[-300:].strip()
            logger.debug(f"Probe {name} falhou: {stderr_tail}")
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug(f"Probe {name} exception: {e}")
        ok = False

    _probe_cache[name] = ok
    return ok


def select_encoder() -> str:
    """Decide o encoder ativo. Cacheado por processo.

    Respeita `settings.video_encoder`. Se "auto", testa _AUTO_ORDER em ordem.
    Se forçado para um encoder específico que falha no probe, cai pro libx264
    e loga warning.
    """
    global _selected_encoder
    if _selected_encoder is not None:
        return _selected_encoder

    try:
        from config.settings import settings
        pref = (getattr(settings, "video_encoder", "auto") or "auto").lower()
    except Exception:
        pref = "auto"

    target = _ALIAS.get(pref, None)

    if target is None:
        # auto: testa em ordem
        for candidate in _AUTO_ORDER:
            if _probe(candidate):
                _selected_encoder = candidate
                logger.info(f"Encoder selecionado (auto): {candidate}")
                return candidate
        # _AUTO_ORDER termina em libx264 que sempre passa, então não
        # deveríamos chegar aqui.
        _selected_encoder = "libx264"
        return "libx264"

    # forçado a um encoder específico
    if _probe(target):
        _selected_encoder = target
        logger.info(f"Encoder selecionado (forçado): {target}")
        return target

    logger.warning(
        f"Encoder forçado '{pref}' ({target}) falhou no probe — usando libx264"
    )
    _selected_encoder = "libx264"
    return "libx264"


def get_active_encoder_label() -> str:
    """Label curto pra log/UI."""
    enc = select_encoder()
    return {
        "h264_nvenc": "NVENC",
        "h264_qsv":   "QSV",
        "h264_amf":   "AMF",
        "libx264":    "CPU x264",
    }.get(enc, enc)


def get_video_encoder_args(crf_equiv: int = 23) -> List[str]:
    """Retorna o slice `-c:v ...` apropriado para o encoder ativo.

    Args:
        crf_equiv: valor de qualidade equivalente ao CRF do libx264 (lower = melhor).
            Mapeado para o controle de qualidade nativo de cada encoder.

    Returns:
        Lista de strings pra concatenar no comando ffmpeg.
        SEMPRE inclui `-pix_fmt yuv420p` e `-profile:v high` para garantir
        compatibilidade com TikTok/YouTube/etc.
    """
    enc = select_encoder()

    if enc == "h264_nvenc":
        # Turing+ aceita -bf 3 com segurança. -rc vbr + -cq mantém qualidade
        # constante; -maxrate evita explodir o bitrate em cenas complexas.
        # spatial-aq/temporal-aq melhora qualidade subjetiva sem custo notável.
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p5",
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", str(crf_equiv),
            "-b:v", "0",
            "-maxrate", "8M",
            "-bufsize", "16M",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-bf", "3",
            "-spatial-aq", "1",
            "-temporal-aq", "1",
        ]

    if enc == "h264_qsv":
        return [
            "-c:v", "h264_qsv",
            "-preset", "medium",
            "-global_quality", str(crf_equiv),
            "-look_ahead", "1",
            "-profile:v", "high",
            "-pix_fmt", "nv12",
        ]

    if enc == "h264_amf":
        return [
            "-c:v", "h264_amf",
            "-quality", "balanced",
            "-rc", "cqp",
            "-qp_i", str(crf_equiv),
            "-qp_p", str(crf_equiv),
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
        ]

    # libx264 fallback
    return [
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(crf_equiv),
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
    ]
