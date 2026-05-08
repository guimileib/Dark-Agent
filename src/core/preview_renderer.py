"""Renderizador de previews de legendas usando Pillow (rápido, sem FFmpeg)"""

import logging
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

try:
    from models import EstiloLegenda
    from config.settings import settings
    from config.paths import CACHE_DIR
except ImportError:
    from ..models import EstiloLegenda
    from ..config.settings import settings
    from ..config.paths import CACHE_DIR

logger = logging.getLogger(__name__)

# Fontes Windows padrão — prioriza Segoe UI Black/Bold para ficar coerente
# com os cards "Aa" do subtitle_widget (QFont "Segoe UI" ExtraBold).
_WINDOWS_FONTS_BOLD = [
    "C:/Windows/Fonts/seguibl.ttf",    # Segoe UI Black
    "C:/Windows/Fonts/segoeuib.ttf",   # Segoe UI Bold
    "C:/Windows/Fonts/arialbd.ttf",    # Arial Bold
    "C:/Windows/Fonts/calibrib.ttf",   # Calibri Bold
    "C:/Windows/Fonts/verdanab.ttf",   # Verdana Bold
]

_WINDOWS_FONTS_REGULAR = [
    "C:/Windows/Fonts/segoeui.ttf",    # Segoe UI
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/verdana.ttf",
]


def _ass_to_rgb(cor_ass: str) -> tuple[int, int, int]:
    """Converte cor ASS &HBBGGRR para tupla RGB."""
    cor = cor_ass.replace("&H", "").replace("&", "")
    if len(cor) >= 6:
        b = int(cor[0:2], 16)
        g = int(cor[2:4], 16)
        r = int(cor[4:6], 16)
        return (r, g, b)
    return (255, 255, 255)


def _load_font(tamanho: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Tenta carregar fonte do sistema, com fallback."""
    candidates = _WINDOWS_FONTS_BOLD if bold else _WINDOWS_FONTS_REGULAR
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, tamanho)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_play_icon(draw: ImageDraw.Draw, w: int, h: int, img: Image.Image) -> None:
    """Desenha um botão de play minimalista moderno no centro do canvas.

    Estilo: rounded-square semitransparente com gradiente azul sutil, triângulo
    de play branco e leve sombra externa — visual alinhado a players modernos
    (YouTube/Netflix style).
    """
    cx, cy = w // 2, h // 2
    size = int(min(w, h) * 0.18)

    # Camada de sombra (Gaussian-ish via overlay)
    shadow = Image.new("RGBA", (size * 3, size * 3), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(shadow)
    sh_draw.rounded_rectangle(
        [size, size + 4, size * 2, size * 2 + 4],
        radius=int(size * 0.28),
        fill=(0, 0, 0, 80),
    )
    img.paste(shadow, (cx - int(size * 1.5), cy - int(size * 1.5)), shadow)

    # Botão principal — rounded-square branco translúcido
    btn = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    btn_draw = ImageDraw.Draw(btn)
    btn_draw.rounded_rectangle(
        [0, 0, size * 2, size * 2],
        radius=int(size * 0.28),
        fill=(255, 255, 255, 235),
    )

    # Triângulo de play (cinza-escuro, deslocado p/ centroide visual)
    tri_h = int(size * 0.95)
    tri_w = int(size * 0.80)
    offset_x = int(size * 0.12)
    cx_btn = size
    cy_btn = size
    p1 = (cx_btn - tri_w // 2 + offset_x, cy_btn - tri_h // 2)
    p2 = (cx_btn - tri_w // 2 + offset_x, cy_btn + tri_h // 2)
    p3 = (cx_btn + tri_w // 2 + offset_x, cy_btn)
    btn_draw.polygon([p1, p2, p3], fill=(30, 41, 59, 255))

    img.paste(btn, (cx - size, cy - size), btn)


def _text_y_position(posicao: str, h: int, txt_h: int) -> int:
    """Calcula Y da legenda conforme 'Embaixo' | 'Centro' | 'Topo'."""
    p = (posicao or "Embaixo").strip().lower()
    if p.startswith("topo") or p == "top":
        return int(h * 0.08)
    if p.startswith("cent") or p == "center":
        return (h - txt_h) // 2
    # Default: embaixo
    return h - txt_h - int(h * 0.10)


class PreviewRenderer:
    """Renderiza previews de legendas usando Pillow — rápido e sem FFmpeg."""

    def __init__(self, canvas_size: tuple = (640, 360)):
        self.canvas_size = canvas_size
        # Previews são gerados em runtime e precisam ficar em área mutável
        # (APP_DIR/cache). BUNDLE_DIR/src/assets é read-only no modo frozen e
        # desaparece quando o .exe fecha.
        self._preview_dir = CACHE_DIR / "previews"
        self._preview_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def gerar_preview(
        self,
        estilo: EstiloLegenda,
        tamanho: Optional[int] = None,
        output_dir: Optional[Path] = None,
        force: bool = False,
        posicao: str = "Embaixo",
    ) -> Optional[Path]:
        """Gera preview para um estilo, tamanho e posição específicos."""
        if not PILLOW_OK:
            logger.error("Pillow não instalado — pip install pillow")
            return None

        if output_dir is None:
            output_dir = self._preview_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        tamanho_atual = tamanho if tamanho is not None else estilo.tamanho
        cor_safe = estilo.cor_primaria.replace("&H", "").replace("&", "")
        pos_safe = (posicao or "Embaixo").strip().lower()[:4]
        # "_v3" marca a renderização atual (play icon moderno + posição variável).
        output_path = (
            output_dir
            / f"{estilo.id}_size{tamanho_atual}_{cor_safe}_pos{pos_safe}_v3.png"
        )

        if output_path.exists() and not force:
            return output_path

        try:
            return self._renderizar(estilo, tamanho_atual, output_path, posicao)
        except Exception as e:
            logger.error(f"Erro ao gerar preview {estilo.id}: {e}")
            return None

    def gerar_previews_todos_tamanhos(
        self,
        estilo: EstiloLegenda,
        tamanhos: Optional[list] = None,
        force: bool = False,
    ) -> dict:
        """Gera previews para todos os tamanhos de um estilo."""
        previews = {}

        if tamanhos is None:
            if hasattr(estilo, "size_options") and estilo.size_options:
                tamanhos = estilo.size_options
            else:
                tamanhos = [12, 18, 24, 28, 32, 36, 40, 44, 48]

        for t in tamanhos:
            p = self.gerar_preview(estilo, tamanho=t, force=force)
            if p:
                previews[t] = p

        return previews

    def limpar_cache(self) -> None:
        """Remove previews existentes."""
        try:
            for f in self._preview_dir.glob("*.png"):
                f.unlink()
            logger.info("Cache de previews limpo com sucesso")
        except Exception as e:
            logger.error(f"Erro ao limpar cache: {e}")

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _renderizar(
        self,
        estilo: EstiloLegenda,
        tamanho: int,
        output_path: Path,
        posicao: str = "Embaixo",
    ) -> Optional[Path]:
        w, h = self.canvas_size

        # Canvas RGBA para suportar o play icon com transparência/sombra.
        img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        # Ícone de play moderno, centralizado.
        _draw_play_icon(draw, w, h, img)

        texto = getattr(estilo, "texto_exemplo", "Texto de Exemplo")
        cor_texto = _ass_to_rgb(estilo.cor_primaria)
        cor_borda = _ass_to_rgb(getattr(estilo, "cor_borda", "&H000000"))
        bold = getattr(estilo, "bold", True)
        borda_esp = getattr(estilo, "borda_espessura", 2)
        sombra_off = getattr(estilo, "sombra_offset", 2)

        font = _load_font(tamanho, bold=bold)

        bbox = draw.textbbox((0, 0), texto, font=font)
        txt_w = bbox[2] - bbox[0]
        txt_h = bbox[3] - bbox[1]

        x = (w - txt_w) // 2
        y = _text_y_position(posicao, h, txt_h)

        if sombra_off > 0:
            draw.text((x + sombra_off, y + sombra_off), texto, font=font,
                      fill=(0, 0, 0))

        if borda_esp > 0:
            for dx in range(-borda_esp, borda_esp + 1):
                for dy in range(-borda_esp, borda_esp + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), texto, font=font,
                                  fill=cor_borda)

        draw.text((x, y), texto, font=font, fill=cor_texto)

        watermark_font = _load_font(11, bold=False)
        draw.text((8, 8), estilo.nome, font=watermark_font,
                  fill=(180, 180, 180))

        draw.rectangle([0, 0, w - 1, h - 1], outline=(60, 65, 80), width=2)

        img.convert("RGB").save(str(output_path), "PNG", optimize=True)
        logger.info(f"Preview gerado: {output_path.name}")
        return output_path
