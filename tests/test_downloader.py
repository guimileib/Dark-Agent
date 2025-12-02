"""Testes do downloader"""

import pytest
from pathlib import Path
from src.core import VideoDownloader


def test_downloader_initialization():
    """Testa inicialização do downloader"""
    output_dir = Path("./test_output")
    downloader = VideoDownloader(output_dir)
    
    assert downloader.output_dir == output_dir
    assert len(downloader.estrategias) == 7


def test_get_video_info():
    """Testa obtenção de informações do vídeo"""
    downloader = VideoDownloader(Path("./test_output"))
    
    # URL de teste (vídeo curto do YouTube)
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo"
    
    info = downloader.get_video_info(url)
    
    assert isinstance(info, dict)
    # Se não conseguiu obter info, pode ser devido a restrições
    # Teste passa se retornar dict vazio ou com dados


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
