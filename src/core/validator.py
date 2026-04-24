"""Validação de vídeos com FFprobe"""

import subprocess
import sys
import json
import logging
from pathlib import Path
from typing import Tuple, Dict

logger = logging.getLogger(__name__)

_SP_KW: dict = {}
if sys.platform == "win32":
    _SP_KW["creationflags"] = subprocess.CREATE_NO_WINDOW


def _parse_fps(rate_str: str) -> float:
    """Parseia r_frame_rate ('30/1', '24000/1001') de forma segura."""
    try:
        if "/" in rate_str:
            num_str, den_str = rate_str.split("/", 1)
            num, den = float(num_str), float(den_str)
            return num / den if den else 0.0
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return 0.0


class VideoValidator:
    """Validador de vídeos usando FFprobe"""

    @staticmethod
    def validar_video_completo(caminho: Path) -> Tuple[bool, Dict[str, bool]]:
        """
        Validação de vídeo — executa UMA chamada ffprobe e deriva todos os checks.

        Returns:
            (valido, checks) onde checks é um dict com resultados dos testes
        """
        # Uma única chamada ffprobe para metadados completos.
        metadados = VideoValidator.obter_metadados(caminho)
        streams = metadados.get("streams", []) or []
        formato = metadados.get("format", {}) or {}

        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        try:
            duracao = float(formato.get("duration", 0) or 0)
        except (TypeError, ValueError):
            duracao = 0.0

        # Checagem de packets só é necessária quando o stream existe mas pode estar vazio.
        tem_video_stream = bool(video_streams)
        tem_audio_stream = bool(audio_streams)

        checks = {
            "tem_video": tem_video_stream and VideoValidator._stream_tem_packets(caminho, "v:0"),
            "tem_audio": tem_audio_stream and VideoValidator._stream_tem_packets(caminho, "a:0"),
            "duracao_valida": duracao > 0,
            "codec_compativel": tem_video_stream and tem_audio_stream,
        }

        valido = all(checks.values())
        logger.info(f"Validação de {caminho.name}: {checks}")
        return valido, checks

    @staticmethod
    def _stream_tem_packets(caminho: Path, select: str) -> bool:
        """Conta packets de um stream específico (v:0 ou a:0)."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", select,
            "-count_packets",
            "-show_entries", "stream=nb_read_packets",
            "-of", "json",
            str(caminho),
        ]
        try:
            resultado = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, **_SP_KW
            )
            if resultado.returncode == 0:
                dados = json.loads(resultado.stdout)
                streams = dados.get("streams", [])
                if streams:
                    return int(streams[0].get("nb_read_packets", 0)) > 0
        except Exception as e:
            logger.error(f"Erro ao contar packets de {select}: {e}")
        return False

    @staticmethod
    def obter_metadados(caminho: Path) -> dict:
        """Obtém todos os metadados do vídeo"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            str(caminho),
        ]

        try:
            resultado = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, **_SP_KW
            )
            if resultado.returncode == 0:
                return json.loads(resultado.stdout)
        except Exception as e:
            logger.error(f"Erro ao obter metadados: {e}")

        return {}

    @staticmethod
    def extrair_info_basica(caminho: Path) -> dict:
        """Extrai informações básicas do vídeo"""
        metadados = VideoValidator.obter_metadados(caminho)

        formato = metadados.get("format", {})
        streams = metadados.get("streams", [])

        stream_video = next((s for s in streams if s.get("codec_type") == "video"), {})
        stream_audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

        return {
            "duracao": float(formato.get("duration", 0) or 0),
            "tamanho_bytes": int(formato.get("size", 0) or 0),
            "bitrate": int(formato.get("bit_rate", 0) or 0),
            "largura": int(stream_video.get("width", 0) or 0),
            "altura": int(stream_video.get("height", 0) or 0),
            "fps": _parse_fps(stream_video.get("r_frame_rate", "0/1")),
            "codec_video": stream_video.get("codec_name", "unknown"),
            "codec_audio": stream_audio.get("codec_name", "unknown"),
            "bitrate_video": int(stream_video.get("bit_rate", 0) or 0),
            "bitrate_audio": int(stream_audio.get("bit_rate", 0) or 0),
        }
