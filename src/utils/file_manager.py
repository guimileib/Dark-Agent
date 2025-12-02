"""Gerenciador de arquivos e diretórios"""

import shutil
import logging
from pathlib import Path
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)


class FileManager:
    """Gerenciador de arquivos do projeto"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.output_dir = self.base_dir / "output"
        self.cache_dir = self.base_dir / "cache"
        self.temp_dir = self.base_dir / "temp"
        
        # Criar diretórios
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def criar_diretorio_processamento(self, video_id: str) -> Path:
        """Cria diretório para processamento de um vídeo específico"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dir_nome = f"{video_id}_{timestamp}"
        dir_path = self.output_dir / dir_nome
        dir_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Diretório de processamento criado: {dir_path}")
        return dir_path
    
    def limpar_temporarios(self):
        """Remove arquivos temporários"""
        if self.temp_dir.exists():
            for item in self.temp_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    logger.warning(f"Erro ao remover {item}: {e}")
        
        logger.info("Arquivos temporários limpos")
    
    def limpar_cache(self, dias: int = 7):
        """Remove cache antigo (mais de X dias)"""
        if not self.cache_dir.exists():
            return
        
        from datetime import timedelta
        limite = datetime.now() - timedelta(days=dias)
        
        for item in self.cache_dir.iterdir():
            try:
                if item.stat().st_mtime < limite.timestamp():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                    logger.info(f"Cache removido: {item.name}")
            except Exception as e:
                logger.warning(f"Erro ao remover cache {item}: {e}")
    
    def obter_tamanho_diretorio(self, caminho: Path) -> int:
        """Calcula tamanho total de um diretório em bytes"""
        total = 0
        
        try:
            for item in caminho.rglob('*'):
                if item.is_file():
                    total += item.stat().st_size
        except Exception as e:
            logger.error(f"Erro ao calcular tamanho: {e}")
        
        return total
    
    def formatar_tamanho(self, bytes: int) -> str:
        """Formata tamanho em formato legível"""
        for unidade in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024.0:
                return f"{bytes:.1f} {unidade}"
            bytes /= 1024.0
        
        return f"{bytes:.1f} PB"
    
    def listar_videos_processados(self) -> List[dict]:
        """Lista todos os vídeos já processados"""
        videos = []
        
        for dir_proc in self.output_dir.iterdir():
            if dir_proc.is_dir():
                # Procurar arquivo final
                arquivos_mp4 = list(dir_proc.glob("*_final.mp4"))
                
                if arquivos_mp4:
                    arquivo = arquivos_mp4[0]
                    videos.append({
                        "nome": arquivo.stem,
                        "caminho": arquivo,
                        "tamanho": arquivo.stat().st_size,
                        "data": datetime.fromtimestamp(arquivo.stat().st_mtime)
                    })
        
        return sorted(videos, key=lambda v: v["data"], reverse=True)
