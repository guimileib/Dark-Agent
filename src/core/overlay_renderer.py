"""Overlay renderer — burns text and image overlays onto video via FFmpeg."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.overlay import OverlayElemento

logger = logging.getLogger(__name__)

# Windows font resolution (same list as preview_renderer.py)
_FONT_MAP: dict[str, list[str]] = {
    "arial": [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "impact": [
        "C:/Windows/Fonts/impact.ttf",
    ],
    "helvetica": [
        "C:/Windows/Fonts/arial.ttf",  # Windows substitute
    ],
    "verdana": [
        "C:/Windows/Fonts/verdanab.ttf",
        "C:/Windows/Fonts/verdana.ttf",
    ],
    "calibri": [
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ],
    "trebuchet ms": [
        "C:/Windows/Fonts/trebucbd.ttf",
        "C:/Windows/Fonts/trebuc.ttf",
    ],
    "courier new": [
        "C:/Windows/Fonts/courbd.ttf",
        "C:/Windows/Fonts/cour.ttf",
    ],
}

_FALLBACK_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
]


def _resolve_font(nome: str, bold: bool = True) -> str:
    """Resolve a font family name to an absolute .ttf path on Windows."""
    key = nome.strip().lower()
    candidates = _FONT_MAP.get(key, [])
    if bold:
        # Prefer bold variants (files ending with 'b' or 'bd')
        bold_candidates = [c for c in candidates if "bd" in Path(c).stem.lower() or c.endswith("b.ttf")]
        candidates = bold_candidates + candidates
    for path in candidates:
        if Path(path).exists():
            return path
    for path in _FALLBACK_FONTS:
        if Path(path).exists():
            return path
    return "arial"  # Let FFmpeg try system lookup as last resort


def _escape_path(path: str) -> str:
    """Escape a Windows path for FFmpeg filter expressions.

    C:\\Users\\... -> C\\:/Users/...   (colons escaped, backslashes to forward)
    """
    return path.replace("\\", "/").replace(":", "\\:")


def _escape_text(text: str) -> str:
    """Escape text for FFmpeg drawtext filter."""
    # Order matters: backslash first, then the rest
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


def _hex_to_ffmpeg(hex_color: str) -> str:
    """Convert '#RRGGBB' to FFmpeg '0xRRGGBB' format."""
    return "0x" + hex_color.lstrip("#")


# Position maps — expressions for FFmpeg
_POS_TEXT: dict[str, tuple[str, str]] = {
    "top_left":       ("10",          "10"),
    "top_center":     ("(W-tw)/2",    "10"),
    "top_right":      ("W-tw-10",     "10"),
    "center_left":    ("10",          "(H-th)/2"),
    "center":         ("(W-tw)/2",    "(H-th)/2"),
    "center_right":   ("W-tw-10",     "(H-th)/2"),
    "bottom_left":    ("10",          "H-th-40"),
    "bottom_center":  ("(W-tw)/2",    "H-th-40"),
    "bottom_right":   ("W-tw-10",     "H-th-40"),
}

_POS_IMAGE: dict[str, tuple[str, str]] = {
    "top_left":       ("10",          "10"),
    "top_center":     ("(W-w)/2",     "10"),
    "top_right":      ("W-w-10",      "10"),
    "center_left":    ("10",          "(H-h)/2"),
    "center":         ("(W-w)/2",     "(H-h)/2"),
    "center_right":   ("W-w-10",      "(H-h)/2"),
    "bottom_left":    ("10",          "H-h-40"),
    "bottom_center":  ("(W-w)/2",     "H-h-40"),
    "bottom_right":   ("W-w-10",      "H-h-40"),
}


class OverlayRenderer:
    """Builds and runs FFmpeg commands to burn overlays onto a video."""

    def renderizar(
        self,
        video_path: Path,
        elementos: list[OverlayElemento],
        output_path: Path,
        preset: str = "medium",
    ) -> bool:
        """Render all overlay elements onto *video_path* and write *output_path*.

        Returns True on success.
        """
        if not elementos:
            logger.warning("Nenhum elemento para renderizar")
            return False

        cmd = self._construir_comando(video_path, elementos, output_path, preset)
        logger.info(f"FFmpeg overlay cmd: {' '.join(cmd)}")

        sp_kw: dict = {}
        if sys.platform == "win32":
            sp_kw["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
                stdin=subprocess.DEVNULL,
                **sp_kw,
            )
            if result.returncode == 0 and output_path.exists():
                logger.info(f"Overlay render OK: {output_path}")
                return True
            logger.error(f"FFmpeg overlay falhou (rc={result.returncode}): {result.stderr[-500:]}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg overlay timeout (>1h)")
            return False
        except Exception as exc:
            logger.error(f"Erro no overlay render: {exc}")
            return False

    def extrair_frame(
        self,
        video_path: Path,
        timestamp: float,
        output_path: Path,
    ) -> bool:
        """Extract a single frame at *timestamp* seconds as a PNG."""
        cmd = [
            "ffmpeg",
            "-ss", f"{timestamp:.2f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            "-y",
            str(output_path),
        ]
        sp_kw: dict = {}
        if sys.platform == "win32":
            sp_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL, **sp_kw,
            )
            return result.returncode == 0 and output_path.exists()
        except Exception as exc:
            logger.error(f"Erro ao extrair frame: {exc}")
            return False

    # ── Private helpers ──────────────────────────────────────────────

    def _construir_comando(
        self,
        video_path: Path,
        elementos: list[OverlayElemento],
        output_path: Path,
        preset: str,
    ) -> list[str]:
        textos = [e for e in elementos if e.tipo == "texto"]
        imagens = [e for e in elementos if e.tipo == "imagem" and e.caminho_imagem]

        if not imagens:
            # Text-only: simpler -vf chain
            return self._cmd_texto_only(video_path, textos, output_path, preset)
        else:
            # Mixed: filter_complex
            return self._cmd_misto(video_path, textos, imagens, output_path, preset)

    def _cmd_texto_only(
        self,
        video_path: Path,
        textos: list[OverlayElemento],
        output_path: Path,
        preset: str,
    ) -> list[str]:
        filtros = [self._filtro_drawtext(e) for e in textos]
        vf = ",".join(filtros) if filtros else "null"

        return [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", "23",
            "-c:a", "copy",
            "-y",
            str(output_path),
        ]

    def _cmd_misto(
        self,
        video_path: Path,
        textos: list[OverlayElemento],
        imagens: list[OverlayElemento],
        output_path: Path,
        preset: str,
    ) -> list[str]:
        # Build input list: [0] = video, [1..N] = images
        inputs: list[str] = ["-i", str(video_path)]
        for img in imagens:
            inputs.extend(["-i", img.caminho_imagem])

        # Build filter_complex
        # Step 1: apply all drawtext to video stream
        current_label = "0:v"
        parts: list[str] = []

        if textos:
            dt_chain = ",".join(self._filtro_drawtext(e) for e in textos)
            parts.append(f"[{current_label}]{dt_chain}[vtxt]")
            current_label = "vtxt"

        # Step 2: chain image overlays
        for i, img in enumerate(imagens):
            input_idx = i + 1  # 0 is the video
            img_label = f"img{i}"
            out_label = f"v{i}"

            # Scale + opacity
            scale_w = img.largura_imagem if img.largura_imagem > 0 else -1
            scale_filter = f"scale={scale_w}:-1"
            opacity_filter = f"colorchannelmixer=aa={img.opacidade:.2f}" if img.opacidade < 1.0 else ""
            img_filters = ",".join(filter(None, [scale_filter, "format=rgba", opacity_filter]))
            parts.append(f"[{input_idx}:v]{img_filters}[{img_label}]")

            # Overlay with timing
            pos = self._pos_imagem(img)
            enable = f"enable='between(t,{img.inicio:.2f},{img.fim:.2f})'"
            parts.append(f"[{current_label}][{img_label}]overlay={pos[0]}:{pos[1]}:{enable}[{out_label}]")
            current_label = out_label

        filter_complex = ";".join(parts)

        return [
            "ffmpeg",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{current_label}]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", "23",
            "-c:a", "copy",
            "-y",
            str(output_path),
        ]

    def _filtro_drawtext(self, elem: OverlayElemento) -> str:
        font_path = _resolve_font(elem.fonte, elem.bold)
        font_escaped = _escape_path(font_path)
        text_escaped = _escape_text(elem.texto)
        pos = self._pos_texto(elem)

        parts = [
            f"text='{text_escaped}'",
            f"fontfile='{font_escaped}'",
            f"fontsize={elem.tamanho_fonte}",
            f"fontcolor={_hex_to_ffmpeg(elem.cor_texto)}",
        ]
        if elem.borda_espessura > 0:
            parts.append(f"borderw={elem.borda_espessura}")
            parts.append(f"bordercolor={_hex_to_ffmpeg(elem.cor_borda)}")

        parts.append(f"x={pos[0]}")
        parts.append(f"y={pos[1]}")
        parts.append(f"enable='between(t,{elem.inicio:.2f},{elem.fim:.2f})'")

        return "drawtext=" + ":".join(parts)

    def _pos_texto(self, elem: OverlayElemento) -> tuple[str, str]:
        if elem.posicao_preset == "custom":
            return (str(elem.x_custom), str(elem.y_custom))
        return _POS_TEXT.get(elem.posicao_preset, _POS_TEXT["bottom_center"])

    def _pos_imagem(self, elem: OverlayElemento) -> tuple[str, str]:
        if elem.posicao_preset == "custom":
            return (str(elem.x_custom), str(elem.y_custom))
        return _POS_IMAGE.get(elem.posicao_preset, _POS_IMAGE["center"])
