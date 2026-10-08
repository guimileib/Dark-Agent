"""Metadados de vídeos"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from pathlib import Path

@dataclass
class VideoMetadata:
    """Metadados completos de um vídeo"""
    
    # Identificação
    url: str
    video_id: str
    titulo: str
    
    # Informações do vídeo
    duracao: float  # Segundos
    largura: int
    altura: int
    fps: float
    codec_video: str
    codec_audio: str
    tamanho_bytes: int
    
    # Qualidade
    resolucao: str  # "1080p", "720p", etc.
    bitrate_video: int
    bitrate_audio: int
    
    # Arquivos locais
    caminho_video: Optional[Path] = None
    caminho_audio: Optional[Path] = None
    caminho_legendas: Optional[Path] = None
    caminho_output: Optional[Path] = None
    
    # Status do processamento
    download_completo: bool = False
    transcricao_completa: bool = False
    legendas_aplicadas: bool = False
    
    # Timestamps
    data_download: Optional[datetime] = None
    data_transcricao: Optional[datetime] = None
    data_finalizacao: Optional[datetime] = None
    
    # Estatísticas
    tempo_download: float = 0.0
    tempo_transcricao: float = 0.0
    tempo_total: float = 0.0
    
    # Estratégia usada
    estrategia_download: Optional[str] = None
    modelo_whisper: Optional[str] = None
    
    def to_dict(self):
        """Converte para dicionário"""
        return {
            "url": self.url,
            "video_id": self.video_id,
            "titulo": self.titulo,
            "duracao": self.duracao,
            "largura": self.largura,
            "altura": self.altura,
            "fps": self.fps,
            "codec_video": self.codec_video,
            "codec_audio": self.codec_audio,
            "tamanho_bytes": self.tamanho_bytes,
            "resolucao": self.resolucao,
            "bitrate_video": self.bitrate_video,
            "bitrate_audio": self.bitrate_audio,
            "caminho_video": str(self.caminho_video) if self.caminho_video else None,
            "caminho_audio": str(self.caminho_audio) if self.caminho_audio else None,
            "caminho_legendas": str(self.caminho_legendas) if self.caminho_legendas else None,
            "caminho_output": str(self.caminho_output) if self.caminho_output else None,
            "download_completo": self.download_completo,
            "transcricao_completa": self.transcricao_completa,
            "legendas_aplicadas": self.legendas_aplicadas,
            "data_download": self.data_download.isoformat() if self.data_download else None,
            "data_transcricao": self.data_transcricao.isoformat() if self.data_transcricao else None,
            "data_finalizacao": self.data_finalizacao.isoformat() if self.data_finalizacao else None,
            "tempo_download": self.tempo_download,
            "tempo_transcricao": self.tempo_transcricao,
            "tempo_total": self.tempo_total,
            "estrategia_download": self.estrategia_download,
            "modelo_whisper": self.modelo_whisper
        }


@dataclass
class ConfiguracaoProcessamento:
    """Configurações para processamento de vídeo"""
    
    # Download
    qualidade: str = "720p"
    formato_video: str = "mp4"
    
    # Transcrição
    modelo_whisper: str = "base"
    idioma: str = "pt"
    device: str = "auto"  # auto, cuda, cpu
    
    # Legendas
    estilo_id: str = "tiktok_classic"
    posicao: str = "bottom"
    
    # Cortes
    gerar_cortes: bool = False
    numero_cortes: int = 3
    duracao_corte: int = 30
    formato_corte: str = "vertical"  # vertical, horizontal, square
    
    # Logo
    adicionar_logo: bool = False
    caminho_logo: Optional[Path] = None
    posicao_logo: str = "top_right"
    opacidade_logo: float = 0.8
    
    # Output
    pasta_output: Path = Path("./output")
    nome_arquivo: Optional[str] = None
    
    def to_dict(self):
        """Converte para dicionário"""
        return {
            "qualidade": self.qualidade,
            "formato_video": self.formato_video,
            "modelo_whisper": self.modelo_whisper,
            "idioma": self.idioma,
            "device": self.device,
            "estilo_id": self.estilo_id,
            "posicao": self.posicao,
            "gerar_cortes": self.gerar_cortes,
            "numero_cortes": self.numero_cortes,
            "duracao_corte": self.duracao_corte,
            "formato_corte": self.formato_corte,
            "adicionar_logo": self.adicionar_logo,
            "caminho_logo": str(self.caminho_logo) if self.caminho_logo else None,
            "posicao_logo": self.posicao_logo,
            "opacidade_logo": self.opacidade_logo,
            "pasta_output": str(self.pasta_output),
            "nome_arquivo": self.nome_arquivo
        }
