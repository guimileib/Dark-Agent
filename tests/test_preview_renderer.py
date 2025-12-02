"""Testes do preview renderer"""

import pytest
from pathlib import Path
from src.core import PreviewRenderer
from src.models import EstiloLegenda


def test_preview_renderer_init():
    """Testa inicialização do renderer"""
    renderer = PreviewRenderer()
    
    assert renderer.canvas_size == (1280, 720)
    assert isinstance(renderer.cache, dict)


def test_renderizar_preview():
    """Testa renderização de preview"""
    renderer = PreviewRenderer()
    
    estilo = EstiloLegenda(
        id="test",
        nome="Test Style",
        categoria="social",
        texto_exemplo="Teste de PREVIEW"
    )
    
    img = renderer.renderizar(estilo)
    
    assert img is not None
    assert img.size == (1280, 720)


def test_ass_para_rgb():
    """Testa conversão de cor ASS para RGB"""
    # Branco: &H00FFFFFF
    rgb = PreviewRenderer._ass_para_rgb("&H00FFFFFF")
    assert rgb == (255, 255, 255)
    
    # Amarelo: &H0000FFFF (BGR: FF FF 00 -> RGB: 00 FF FF = ciano, mas ASS inverte)
    # Na verdade em ASS: &HBBGGRR, então &H0000FFFF = RR=FF, GG=FF, BB=00 = Amarelo
    rgb = PreviewRenderer._ass_para_rgb("&H0000FFFF")
    assert rgb == (255, 255, 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
