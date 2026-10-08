"""Montador de compilações — "Adivinhe a Música" / rankings para TikTok e Shorts.

Junta 2–5 clipes em um vídeo só, com transição xfade entre eles, rótulo
opcional por clipe (ex.: "Música 1", "#3") e logo do canal sobreposto o
tempo todo. Tudo em UMA passada de FFmpeg (filter_complex), sem arquivos
intermediários e sem dependência nova — usa o mesmo FFmpeg que o app já
embute, com o encoder auto-detectado (NVENC/QSV/AMF/x264).
"""

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from core.video_editor import (
    _ffmpeg_escape_path,
    _ffmpeg_escape_text,
    _probe_duration,
    _run_ffmpeg_with_progress,
)

logger = logging.getLogger(__name__)

_SP_KW: dict = {}
if sys.platform == "win32":
    _SP_KW["creationflags"] = subprocess.CREATE_NO_WINDOW

# Transições xfade expostas na UI: chave ffmpeg -> label humano.
TRANSICOES = {
    "fade":        "Fade",
    "slideleft":   "Deslizar ←",
    "slideright":  "Deslizar →",
    "wipeleft":    "Cortina ←",
    "wiperight":   "Cortina →",
    "circleopen":  "Círculo abrindo",
    "dissolve":    "Dissolver",
    "pixelize":    "Pixelizar",
}

# Cantos suportados para o logo do canal: chave -> (x, y) em expressão ffmpeg.
LOGO_POSICOES = {
    "top_left":     ("W*0.03",       "W*0.03"),
    "top_right":    ("W-w-W*0.03",   "W*0.03"),
    "bottom_left":  ("W*0.03",       "H-h-W*0.03"),
    "bottom_right": ("W-w-W*0.03",   "H-h-W*0.03"),
}

MIN_CLIPES = 2
MAX_CLIPES = 5


@dataclass
class SegmentoCompilacao:
    """Um clipe da compilação: vídeo + rótulo opcional queimado no topo."""
    video: Path
    rotulo: str = ""


def _tem_audio(video_path: Path) -> bool:
    """True se o arquivo tem pelo menos um stream de áudio."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL, **_SP_KW,
        )
        return result.returncode == 0 and "audio" in (result.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return False


def _fonte_sistema() -> Optional[str]:
    """Fonte bold do Windows para o drawtext dos rótulos (mesma dos marcadores)."""
    candidatos = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    return next((p for p in candidatos if Path(p).exists()), None)


def calcular_offsets(duracoes: List[float], dur_transicao: float) -> List[float]:
    """Offsets (em s) de cada xfade ao encadear os clipes.

    O i-ésimo xfade (que junta o clipe i+1) começa em
    sum(duracoes[:i+1]) - (i+1) * dur_transicao, porque cada transição
    anterior já "comeu" dur_transicao do timeline acumulado.
    """
    offsets = []
    acumulado = 0.0
    for i, d in enumerate(duracoes[:-1]):
        acumulado += d
        offsets.append(round(acumulado - (i + 1) * dur_transicao, 3))
    return offsets


def duracao_total(duracoes: List[float], dur_transicao: float) -> float:
    """Duração final da compilação: soma dos clipes menos as sobreposições."""
    return sum(duracoes) - dur_transicao * (len(duracoes) - 1)


def clamp_transicao(duracoes: List[float], dur_transicao: float) -> float:
    """Garante que a transição caiba nos clipes (no máx. 40% do mais curto)."""
    if not duracoes:
        return dur_transicao
    limite = max(0.1, min(duracoes) * 0.4)
    return round(min(dur_transicao, limite), 3)


def construir_grafo(
    duracoes: List[float],
    audio_pads: List[str],
    rotulos: List[str],
    *,
    transicao: str = "fade",
    dur_transicao: float = 0.5,
    largura: int = 1080,
    altura: int = 1920,
    fps: int = 30,
    logo_pad: Optional[str] = None,
    logo_pos: str = "top_right",
    logo_frac: float = 0.14,
    fonte: Optional[str] = None,
) -> str:
    """Monta a string de filter_complex. Função pura — testável sem FFmpeg.

    Args:
        duracoes: duração de cada clipe em segundos (mesma ordem dos inputs 0..N-1).
        audio_pads: pad de áudio de cada clipe (ex.: "0:a", ou "5:a" apontando
            para um anullsrc quando o clipe não tem áudio).
        rotulos: texto a queimar no topo de cada clipe ("" = sem rótulo).
        logo_pad: pad do input do logo (ex.: "3:v"), ou None para sem logo.
    """
    n = len(duracoes)
    partes: List[str] = []

    # ── Normalização de cada clipe (xfade exige mesma resolução/fps/formato) ──
    fontsize = max(24, int(altura * 0.038))
    for i in range(n):
        cadeia = (
            f"[{i}:v]scale={largura}:{altura}:force_original_aspect_ratio=decrease,"
            f"pad={largura}:{altura}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps},format=yuv420p"
        )
        if rotulos[i].strip():
            texto = _ffmpeg_escape_text(rotulos[i].strip())
            drawtext = (
                f"drawtext=text='{texto}':fontsize={fontsize}:fontcolor=white:"
                f"borderw=3:bordercolor=black:box=1:boxcolor=black@0.45:boxborderw=14:"
                f"x=(w-text_w)/2:y=h*0.06"
            )
            if fonte:
                # O ':' do drive (C:/) quebraria o parser do filtergraph
                drawtext += f":fontfile='{_ffmpeg_escape_path(fonte)}'"
            cadeia += f",{drawtext}"
        partes.append(f"{cadeia}[v{i}]")
        partes.append(
            f"[{audio_pads[i]}]aresample=44100,"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]"
        )

    # ── Encadeamento com xfade (vídeo) + acrossfade (áudio) ──────────────────
    offsets = calcular_offsets(duracoes, dur_transicao)
    v_atual, a_atual = "v0", "a0"
    for i in range(1, n):
        v_saida = f"vx{i}" if i < n - 1 else "vcat"
        a_saida = f"ax{i}" if i < n - 1 else "acat"
        partes.append(
            f"[{v_atual}][v{i}]xfade=transition={transicao}:"
            f"duration={dur_transicao}:offset={offsets[i - 1]}[{v_saida}]"
        )
        partes.append(
            f"[{a_atual}][a{i}]acrossfade=d={dur_transicao}:c1=tri:c2=tri[{a_saida}]"
        )
        v_atual, a_atual = v_saida, a_saida

    # ── Logo do canal por cima do vídeo inteiro ───────────────────────────────
    if logo_pad:
        x, y = LOGO_POSICOES.get(logo_pos, LOGO_POSICOES["top_right"])
        logo_w = int(largura * logo_frac)
        partes.append(f"[{logo_pad}]scale={logo_w}:-1[lg]")
        partes.append(f"[{v_atual}][lg]overlay=x={x}:y={y}[vout]")
    else:
        partes.append(f"[{v_atual}]copy[vout]")

    partes.append(f"[{a_atual}]acopy[aout]")
    return ";".join(partes)


def montar_compilacao(
    segmentos: List[SegmentoCompilacao],
    output_path: Path,
    *,
    logo_path: Optional[Path] = None,
    logo_pos: str = "top_right",
    logo_frac: float = 0.14,
    transicao: str = "fade",
    dur_transicao: float = 0.5,
    resolucao: Tuple[int, int] = (1080, 1920),
    fps: int = 30,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> bool:
    """Renderiza a compilação. Bloqueante — chamar de um QThread.

    Returns:
        True se o arquivo final foi gerado com sucesso.
    """
    if not (MIN_CLIPES <= len(segmentos) <= MAX_CLIPES):
        logger.error(
            f"Compilação exige {MIN_CLIPES}–{MAX_CLIPES} clipes; recebi {len(segmentos)}"
        )
        return False

    for seg in segmentos:
        if not Path(seg.video).exists():
            logger.error(f"Clipe não encontrado: {seg.video}")
            return False
    if logo_path and not Path(logo_path).exists():
        logger.warning(f"Logo não encontrado ({logo_path}) — montando sem logo")
        logo_path = None

    duracoes = []
    for seg in segmentos:
        d = _probe_duration(Path(seg.video))
        if not d or d <= 0:
            logger.error(f"Não consegui medir a duração de {seg.video}")
            return False
        duracoes.append(d)

    dur_transicao = clamp_transicao(duracoes, dur_transicao)
    largura, altura = resolucao

    # ── Inputs: clipes, anullsrc para clipes mudos, logo por último ──────────
    cmd_inputs: List[str] = []
    for seg in segmentos:
        cmd_inputs += ["-i", str(seg.video)]

    audio_pads: List[str] = []
    proximo_input = len(segmentos)
    for i, seg in enumerate(segmentos):
        if _tem_audio(Path(seg.video)):
            audio_pads.append(f"{i}:a")
        else:
            # Silêncio com a duração do clipe, pra manter o acrossfade alinhado.
            cmd_inputs += [
                "-f", "lavfi", "-t", f"{duracoes[i]:.3f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            ]
            audio_pads.append(f"{proximo_input}:a")
            proximo_input += 1

    logo_pad = None
    if logo_path:
        cmd_inputs += ["-i", str(logo_path)]
        logo_pad = f"{proximo_input}:v"

    grafo = construir_grafo(
        duracoes,
        audio_pads,
        [seg.rotulo for seg in segmentos],
        transicao=transicao,
        dur_transicao=dur_transicao,
        largura=largura,
        altura=altura,
        fps=fps,
        logo_pad=logo_pad,
        logo_pos=logo_pos,
        logo_frac=logo_frac,
        fonte=_fonte_sistema(),
    )

    from core.encoder import get_video_encoder_args, get_active_encoder_label

    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error",
        *cmd_inputs,
        "-filter_complex", grafo,
        "-map", "[vout]", "-map", "[aout]",
        *get_video_encoder_args(crf_equiv=21),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-y",
        str(output_path),
    ]

    total = duracao_total(duracoes, dur_transicao)
    logger.info(
        f"Compilação: {len(segmentos)} clipes, transição={transicao} "
        f"({dur_transicao}s), {largura}x{altura}, ~{total:.1f}s, "
        f"encoder={get_active_encoder_label()}"
    )
    logger.debug(f"filter_complex: {grafo}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    return _run_ffmpeg_with_progress(
        cmd,
        duration_sec=total,
        progress_callback=progress_callback,
        output_path=output_path,
        timeout=3600,
    )
