"""Configurações do DarkAgent Pro"""

import json
from pathlib import Path
from typing import Dict, List

# Import absoluto
try:
    from models import EstiloLegenda
except ImportError:
    from ..models import EstiloLegenda

class Settings:
    """Gerenciador de configurações"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent.parent
        self.config_dir = self.base_dir / "src" / "config"
        self.assets_dir = self.base_dir / "src" / "assets"
        
        # Diretórios de trabalho
        self.output_dir = self.base_dir / "src" / "output"
        self.cache_dir = self.base_dir / "src" / "cache"
        self.models_dir = self.base_dir / "src" / "models"
        
        # Criar diretórios se não existirem
        self.output_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        self.models_dir.mkdir(exist_ok=True)
        
        # Configurações padrão
        self.whisper_model = "base"
        self.whisper_device = "auto"
        self.whisper_language = None  # None = auto-detect, ou "en", "pt", etc.
        
        self.ffmpeg_threads = 4
        self.ffmpeg_preset = "medium"
        
        self.max_retries = 3
        self.timeout = 300
        self.quality_preference = "720p"
        
        self.theme = "dark"
        self.language = "pt-BR"
        self.auto_save_config = True
        
        self.cache_enabled = True
        self.parallel_processing = True
        self.max_workers = 4
        
        # Carregar estilos
        self._estilos = self._carregar_estilos()
    
    def _carregar_estilos(self) -> Dict[str, EstiloLegenda]:
        """Carrega estilos do arquivo JSON"""
        arquivo_estilos = self.config_dir / "estilos_padrao.json"
        
        if not arquivo_estilos.exists():
            return {}
        
        with open(arquivo_estilos, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        estilos = {}
        for estilo_data in dados.get("estilos", []):
            estilo = EstiloLegenda.from_dict(estilo_data)
            estilos[estilo.id] = estilo
        
        return estilos
    
    def get_estilo(self, estilo_id: str) -> EstiloLegenda:
        """Retorna um estilo por ID"""
        return self._estilos.get(estilo_id)
    
    def get_todos_estilos(self) -> List[EstiloLegenda]:
        """Retorna todos os estilos disponíveis"""
        return list(self._estilos.values())
    
    def get_estilos_por_categoria(self, categoria: str) -> List[EstiloLegenda]:
        """Retorna estilos de uma categoria específica"""
        return [e for e in self._estilos.values() if e.categoria == categoria]
    
    def adicionar_estilo(self, estilo: EstiloLegenda):
        """Adiciona um novo estilo personalizado"""
        self._estilos[estilo.id] = estilo
        self._salvar_estilos()
    
    def _salvar_estilos(self):
        """Salva estilos no arquivo JSON"""
        arquivo_estilos = self.config_dir / "estilos_padrao.json"
        
        dados = {
            "estilos": [e.to_dict() for e in self._estilos.values()]
        }
        
        with open(arquivo_estilos, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)


# Instância global de configurações
settings = Settings()
