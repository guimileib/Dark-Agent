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
except ImportError:
    from ..models import EstiloLegenda
    from ..config.settings import settings

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


def _draw_play_icon(draw: ImageDraw.Draw, w: int, h: int) -> None:
    """Desenha um círculo com triângulo de play no centro superior do canvas."""
    cx, cy = w // 2, int(h * 0.38)
    radius = int(min(w, h) * 0.12)

    # Halo sutil (círculo externo semitransparente)
    halo_r = radius + 14
    for i in range(6):
        a = 40 - i * 6
        draw.ellipse(
            [cx - halo_r - i, cy - halo_r - i, cx + halo_r + i, cy + halo_r + i],
            outline=(255, 255, 255, max(a, 0)),
            width=1,
        )

    # Círculo de fundo do botão play
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(255, 255, 255),
        outline=(220, 220, 220),
        width=2,
    )

    # Triângulo de play (preto, ligeiramente deslocado à direita p/ parecer centrado)
    tri_size = int(radius * 0.55)
    tri_x_offset = int(radius * 0.12)
    p1 = (cx - tri_size // 2 + tri_x_offset, cy - tri_size)
    p2 = (cx - tri_size // 2 + tri_x_offset, cy + tri_size)
    p3 = (cx + tri_size + tri_x_offset, cy)
    draw.polygon([p1, p2, p3], fill=(15, 15, 15))


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
        # "_v2" marca a nova renderização (fundo preto + play icon) — bypassa
        # o cache de PNGs antigos com cityscape.
        output_path = output_dir / f"{estilo.id}_size{tamanho_atual}_{cor_safe}_v2.png"

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

        # Fundo totalmente preto — simula frame de vídeo pausado.
        img = Image.new("RGB", (w, h), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Ícone de play centralizado no topo.
        _draw_play_icon(draw, w, h)

        # Texto da legenda
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
