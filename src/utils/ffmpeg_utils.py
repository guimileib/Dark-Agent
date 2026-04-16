"""Utilitários FFmpeg"""

import subprocess
import sys
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Prevent console windows from flashing on Windows
_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def verificar_ffmpeg_instalado() -> bool:
    """Verifica se FFmpeg está instalado e acessível"""
    try:
        resultado = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATION_FLAGS,
        )
        return resultado.returncode == 0
    except Exception:
        return False


def verificar_ffprobe_instalado() -> bool:
    """Verifica se FFprobe está instalado"""
    try:
        resultado = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_CREATION_FLAGS,
        )
        return resultado.returncode == 0
    except Exception:
        return False


def obter_duracao_video(caminho: Path) -> float:
    """Obtém duração do vídeo em segundos"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(caminho)
    ]

    try:
        resultado = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=_CREATION_FLAGS,
        )
        if resultado.returncode == 0:
            dados = json.loads(resultado.stdout)
            return float(dados.get("format", {}).get("duration", 0))
    except Exception:
        pass

    return 0.0


def obter_resolucao_video(caminho: Path) -> tuple:
    """Obtém resolução do vídeo (largura, altura)"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(caminho)
    ]

    try:
        resultado = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=_CREATION_FLAGS,
        )
        if resultado.returncode == 0:
            dados = json.loads(resultado.stdout)
            stream = dados.get("streams", [{}])[0]
            largura = stream.get("width", 0)
            altura = stream.get("height", 0)
            return (largura, altura)
    except Exception:
        pass

    return (0, 0)


def formatar_tempo(segundos: float) -> str:
    """Formata tempo em HH:MM:SS"""
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    secs = int(segundos % 60)

    return f"{horas:02d}:{minutos:02d}:{secs:02d}"
