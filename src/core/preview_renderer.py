"""Renderizador de previews de legendas usando Pillow (rápido, sem FFmpeg)"""

import logging
import random
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

try:
    from models import EstiloLegenda
    from config.settings import settings
except ImportError:
    from ..models import EstiloLegenda
    from ..config.settings import settings

logger = logging.getLogger(__name__)

# Paleta de fundos simulados para diferentes estilos
_BACKGROUNDS = {
    "tiktok_classic":  [(10, 10, 20), (25, 15, 35)],
    "tiktok_bold":     [(5, 5, 5), (20, 5, 10)],
    "reels_bold":      [(15, 10, 30), (30, 20, 50)],
    "youtube_shorts":  [(8, 12, 22), (20, 25, 40)],
    "clean_minimal":   [(18, 20, 28), (30, 33, 45)],
    "neon_glow":       [(5, 5, 15), (10, 5, 25)],
    "bold_impact":     [(5, 5, 5), (15, 10, 10)],
    "gradient_wave":   [(10, 15, 30), (20, 30, 55)],
}

_DEFAULT_BG = [(10, 12, 20), (25, 28, 45)]

# Fontes Windows padrão para fallback
_WINDOWS_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",   # Arial Bold
    "C:/Windows/Fonts/arial.ttf",     # Arial
    "C:/Windows/Fonts/calibrib.ttf",  # Calibri Bold
    "C:/Windows/Fonts/calibri.ttf",   # Calibri
    "C:/Windows/Fonts/trebucbd.ttf",  # Trebuchet Bold
    "C:/Windows/Fonts/verdanab.ttf",  # Verdana Bold
    "C:/Windows/Fonts/verdana.ttf",   # Verdana
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


def _load_font(tamanho: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Tenta carregar fonte do sistema, com fallback."""
    candidates = _WINDOWS_FONTS if not bold else [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/verdanab.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, tamanho)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_gradient_bg(draw: ImageDraw.Draw, w: int, h: int, colors: list) -> None:
    """Desenha fundo com gradiente vertical."""
    c1 = colors[0]
    c2 = colors[1]
    for y in range(h):
        t = y / h
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _draw_fake_scene(draw: ImageDraw.Draw, w: int, h: int) -> None:
    """Adiciona elementos de cena falsa para simular um frame de vídeo."""
    # Linha do horizonte sutil
    draw.rectangle([0, int(h * 0.55), w, int(h * 0.58)],
                   fill=(255, 255, 255, 10))

    # Silhuetas de prédios (rectangle escuros)
    buildings = [
        (w * 0.05, h * 0.30, w * 0.18, h * 0.55),
        (w * 0.20, h * 0.20, w * 0.30, h * 0.55),
        (w * 0.32, h * 0.35, w * 0.45, h * 0.55),
        (w * 0.55, h * 0.25, w * 0.65, h * 0.55),
        (w * 0.68, h * 0.15, w * 0.78, h * 0.55),
        (w * 0.80, h * 0.30, w * 0.92, h * 0.55),
    ]
    for bx0, by0, bx1, by1 in buildings:
        dark = (0, 0, 0, 180)
        draw.rectangle([int(bx0), int(by0), int(bx1), int(by1)], fill=(8, 10, 16))

    # Janelas nos prédios (pontilhados amarelos)
    for bx0, by0, bx1, by1 in buildings:
        bw = int(bx1 - bx0)
        bh = int(by1 - by0)
        cols = max(2, bw // 12)
        rows = max(3, bh // 14)
        win_w = max(2, bw // (cols * 2))
        win_h = max(2, bh // (rows * 2))
        for row in range(rows):
            for col in range(cols):
                if random.random() > 0.35:
                    wx = int(bx0) + col * (bw // cols) + 3
                    wy = int(by0) + row * (bh // rows) + 3
                    draw.rectangle([wx, wy, wx + win_w, wy + win_h],
                                   fill=(255, 220, 120))

    # Ground
    draw.rectangle([0, int(h * 0.55), w, h], fill=(5, 6, 10))


class PreviewRenderer:
    """Renderiza previews de legendas usando Pillow — rápido e sem FFmpeg."""

    def __init__(self, canvas_size: tuple = (640, 360)):
        self.canvas_size = canvas_size
        self._preview_dir = settings.assets_dir / "previews"
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
    ) -> Optional[Path]:
        """Gera preview para um estilo e tamanho específico."""
        if not PILLOW_OK:
            logger.error("Pillow não instalado — pip install pillow")
            return None

        if output_dir is None:
            output_dir = self._preview_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        tamanho_atual = tamanho if tamanho is not None else estilo.tamanho
        cor_safe = estilo.cor_primaria.replace("&H", "").replace("&", "")
        output_path = output_dir / f"{estilo.id}_size{tamanho_atual}_{cor_safe}.png"

        if output_path.exists() and not force:
            return output_path

        try:
            return self._renderizar(estilo, tamanho_atual, output_path)
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
    ) -> Optional[Path]:
        w, h = self.canvas_size

        img = Image.new("RGB", (w, h), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. Fundo gradiente baseado no estilo
        bg_colors = _BACKGROUNDS.get(estilo.id, _DEFAULT_BG)
        _draw_gradient_bg(draw, w, h, bg_colors)

        # 2. Cena de fundo (skyline)
        _draw_fake_scene(draw, w, h)

        # 3. Overlay escuro na parte inferior para legibilidade da legenda
        overlay_h = int(h * 0.38)
        overlay_y = h - overlay_h
        for y_off in range(overlay_h):
            alpha = int(160 * (y_off / overlay_h))
            draw.line([(0, overlay_y + y_off), (w, overlay_y + y_off)],
                      fill=(0, 0, 0))

        # 4. Texto da legenda
        texto = getattr(estilo, "texto_exemplo", "Texto de Exemplo")
        cor_texto = _ass_to_rgb(estilo.cor_primaria)
        cor_borda = _ass_to_rgb(getattr(estilo, "cor_borda", "&H000000"))
        bold = getattr(estilo, "bold", True)
        borda_esp = getattr(estilo, "borda_espessura", 2)
        sombra_off = getattr(estilo, "sombra_offset", 2)

        font = _load_font(tamanho, bold=bold)

        # Usar getbbox para medir texto
        bbox = draw.textbbox((0, 0), texto, font=font)
        txt_w = bbox[2] - bbox[0]
        txt_h = bbox[3] - bbox[1]

        # Posição: centralizado horizontalmente, 15% do fundo
        x = (w - txt_w) // 2
        y = h - txt_h - int(h * 0.10)

        # Sombra
        if sombra_off > 0:
            draw.text((x + sombra_off, y + sombra_off), texto, font=font,
                      fill=(0, 0, 0))

        # Borda (outline via múltiplos offsets)
        if borda_esp > 0:
            for dx in range(-borda_esp, borda_esp + 1):
                for dy in range(-borda_esp, borda_esp + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), texto, font=font,
                                  fill=cor_borda)

        # Texto principal
        draw.text((x, y), texto, font=font, fill=cor_texto)

        # 5. Watermark discreto do estilo
        watermark_font = _load_font(11)
        draw.text((8, 8), estilo.nome, font=watermark_font,
                  fill=(180, 180, 180))

        # 6. Borda cinza no frame (simula player de vídeo)
        draw.rectangle([0, 0, w - 1, h - 1], outline=(60, 65, 80), width=2)

        img.save(str(output_path), "PNG", optimize=True)
        logger.info(f"Preview gerado: {output_path.name}")
        return output_path
