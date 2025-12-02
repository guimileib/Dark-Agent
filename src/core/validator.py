"""Validação de vídeos com FFprobe"""

import subprocess
import json
import logging
from pathlib import Path
from typing import Tuple, Dict

logger = logging.getLogger(__name__)


class VideoValidator:
    """Validador de vídeos usando FFprobe"""
    
    @staticmethod
    def validar_video_completo(caminho: Path) -> Tuple[bool, Dict[str, bool]]:
        """
        Validação tripla de vídeo
        
        Returns:
            (valido, checks) onde checks é um dict com resultados dos testes
        """
        checks = {
            'tem_video': VideoValidator._verificar_stream_video(caminho),
            'tem_audio': VideoValidator._verificar_stream_audio(caminho),
            'duracao_valida': VideoValidator._verificar_duracao(caminho),
            'codec_compativel': VideoValidator._verificar_codecs(caminho)
        }
        
        valido = all(checks.values())
        
        logger.info(f"Validação de {caminho.name}: {checks}")
        
        return valido, checks
    
    @staticmethod
    def _verificar_stream_video(caminho: Path) -> bool:
        """Verifica se existe stream de vídeo"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-count_packets",
            "-show_entries", "stream=nb_read_packets",
            "-of", "json",
            str(caminho)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if resultado.returncode == 0:
                dados = json.loads(resultado.stdout)
                streams = dados.get("streams", [])
                if streams:
                    nb_packets = int(streams[0].get("nb_read_packets", 0))
                    return nb_packets > 0
        except Exception as e:
            logger.error(f"Erro ao verificar stream de vídeo: {e}")
        
        return False
    
    @staticmethod
    def _verificar_stream_audio(caminho: Path) -> bool:
        """Verifica se existe stream de áudio"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-count_packets",
            "-show_entries", "stream=nb_read_packets",
            "-of", "json",
            str(caminho)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if resultado.returncode == 0:
                dados = json.loads(resultado.stdout)
                streams = dados.get("streams", [])
                if streams:
                    nb_packets = int(streams[0].get("nb_read_packets", 0))
                    return nb_packets > 0
        except Exception as e:
            logger.error(f"Erro ao verificar stream de áudio: {e}")
        
        return False
    
    @staticmethod
    def _verificar_duracao(caminho: Path) -> bool:
        """Verifica se a duração é válida (>0)"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(caminho)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if resultado.returncode == 0:
                dados = json.loads(resultado.stdout)
                duracao = float(dados.get("format", {}).get("duration", 0))
                return duracao > 0
        except Exception as e:
            logger.error(f"Erro ao verificar duração: {e}")
        
        return False
    
    @staticmethod
    def _verificar_codecs(caminho: Path) -> bool:
        """Verifica se os codecs são compatíveis"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=codec_name,codec_type",
            "-of", "json",
            str(caminho)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if resultado.returncode == 0:
                dados = json.loads(resultado.stdout)
                streams = dados.get("streams", [])
                
                # Verificar se tem pelo menos um codec de vídeo e um de áudio
                tem_video = any(s.get("codec_type") == "video" for s in streams)
                tem_audio = any(s.get("codec_type") == "audio" for s in streams)
                
                return tem_video and tem_audio
        except Exception as e:
            logger.error(f"Erro ao verificar codecs: {e}")
        
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
            str(caminho)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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
        
        # Stream de vídeo
        stream_video = next((s for s in streams if s.get("codec_type") == "video"), {})
        
        # Stream de áudio
        stream_audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        
        info = {
            "duracao": float(formato.get("duration", 0)),
            "tamanho_bytes": int(formato.get("size", 0)),
            "bitrate": int(formato.get("bit_rate", 0)),
            "largura": int(stream_video.get("width", 0)),
            "altura": int(stream_video.get("height", 0)),
            "fps": eval(stream_video.get("r_frame_rate", "0/1")),
            "codec_video": stream_video.get("codec_name", "unknown"),
            "codec_audio": stream_audio.get("codec_name", "unknown"),
            "bitrate_video": int(stream_video.get("bit_rate", 0)),
            "bitrate_audio": int(stream_audio.get("bit_rate", 0)),
        }
        
        return info
