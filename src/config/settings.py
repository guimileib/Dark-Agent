"""Configurações do DarkAgent Pro"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from config.paths import (
    CONFIG_DIR, ASSETS_DIR, OUTPUT_DIR, CACHE_DIR, MODELS_DIR,
    COOKIES_FILE, ACCOUNTS_DIR, APP_DIR, get_user_config_file, ensure_dirs,
)

# Carrega .env (ao lado do .exe ou na raiz do projeto em dev) para popular
# os.environ ANTES de qualquer leitura de variável de ambiente abaixo.
# Falha silenciosa se python-dotenv não estiver instalado ou .env não existir.
try:
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")
except ImportError:
    pass

try:
    from models import EstiloLegenda
except ImportError:
    from models.estilo_legenda import EstiloLegenda


class Settings:
    """Gerenciador de configurações"""

    def __init__(self):
        # Read-only bundled paths
        self.config_dir = CONFIG_DIR
        self.assets_dir = ASSETS_DIR

        # Mutable data paths (next to .exe or project root)
        self.output_dir = OUTPUT_DIR
        self.cache_dir = CACHE_DIR
        self.models_dir = MODELS_DIR
        self.accounts_dir = ACCOUNTS_DIR

        # Arquivo de cookies
        self.cookies_file = COOKIES_FILE

        # Criar diretórios mutáveis
        ensure_dirs()

        # Configurações padrão
        self.whisper_model = "base"
        self.whisper_device = "auto"
        self.whisper_language = None  # None = auto-detect, ou "en", "pt", etc.

        self.ffmpeg_threads = 4
        self.ffmpeg_preset = "medium"  # legado — não usado pelo encoder novo

        # Encoder de vídeo: "auto" detecta NVENC/QSV/AMF; força com
        # "nvenc"/"qsv"/"amf"/"cpu". Ver core/encoder.py.
        self.video_encoder = "auto"
        # Pula re-encode de áudio em queimar_legendas quando input é AAC-LC.
        self.audio_passthrough = True
        # yt-dlp paralelismo em downloads HLS.
        self.ytdlp_concurrent_fragments = 8

        self.max_retries = 3
        self.timeout = 300
        self.quality_preference = "720p"

        self.theme = "dark"
        self.language = "pt-BR"
        self.auto_save_config = True

        self.cache_enabled = True
        self.parallel_processing = True
        self.max_workers = 4

        self.gemini_api_key = ""
        self.last_open_dir = str(Path.home())

        # Carregar estilos (do bundle read-only)
        self._estilos = self._carregar_estilos()

        # Carregar configurações gerais (do config mutável do usuário)
        self.first_run = True
        self.load_config()

        # Inicializar Social Manager
        self.social_manager = None

    def load_config(self):
        """Carrega configurações do arquivo JSON (user-writable)"""
        config_file = get_user_config_file()
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.first_run = data.get("first_run", True)
                    self.theme = data.get("theme", self.theme)
                    self.language = data.get("language", self.language)
                    self.whisper_model = data.get("whisper_model", self.whisper_model)
                    self.whisper_device = data.get("whisper_device", self.whisper_device)
                    self.video_encoder = data.get("video_encoder", self.video_encoder)
                    self.audio_passthrough = data.get("audio_passthrough", self.audio_passthrough)
                    self.ytdlp_concurrent_fragments = data.get(
                        "ytdlp_concurrent_fragments", self.ytdlp_concurrent_fragments
                    )
                    self.last_open_dir = data.get("last_open_dir", str(Path.home()))
                    # API key: env wins (do .env ou shell). Fallback: config.json.
                    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
                    self.gemini_api_key = env_key or data.get("gemini_api_key", "")
            except Exception as e:
                print(f"Erro ao carregar config: {e}")
                self.last_open_dir = str(Path.home())
                self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        else:
            self.last_open_dir = str(Path.home())
            self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    def save_config(self):
        """Salva configurações no arquivo JSON (user-writable)"""
        config_file = get_user_config_file()
        data = {
            "first_run": self.first_run,
            "theme": self.theme,
            "language": self.language,
            "whisper_model": self.whisper_model,
            "whisper_device": self.whisper_device,
            "video_encoder": self.video_encoder,
            "audio_passthrough": self.audio_passthrough,
            "ytdlp_concurrent_fragments": self.ytdlp_concurrent_fragments,
            "last_open_dir": self.last_open_dir,
            "gemini_api_key": self.gemini_api_key
        }
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Erro ao salvar config: {e}")

    def _carregar_estilos(self) -> Dict[str, EstiloLegenda]:
        """Carrega estilos do arquivo JSON (user copy takes priority over bundle)"""
        from config.paths import USER_CONFIG_DIR

        # User-writable copy takes priority (custom styles saved here)
        user_estilos = USER_CONFIG_DIR / "estilos_padrao.json"
        bundle_estilos = self.config_dir / "estilos_padrao.json"

        arquivo_estilos = user_estilos if user_estilos.exists() else bundle_estilos

        if not arquivo_estilos.exists():
            return {}

        try:
            with open(arquivo_estilos, 'r', encoding='utf-8') as f:
                dados = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logging.getLogger(__name__).warning(f"Erro ao carregar estilos de {arquivo_estilos}: {e}")
            return {}

        estilos = {}
        for estilo_data in dados.get("estilos", []):
            estilo = EstiloLegenda.from_dict(estilo_data)
            estilos[estilo.id] = estilo

        return estilos

    def get_estilo(self, estilo_id: str) -> Optional[EstiloLegenda]:
        """Retorna um estilo por ID (ou None se não encontrado)"""
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
        """Salva estilos no arquivo JSON (user-writable directory)"""
        from config.paths import USER_CONFIG_DIR
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        arquivo_estilos = USER_CONFIG_DIR / "estilos_padrao.json"

        dados = {
            "estilos": [e.to_dict() for e in self._estilos.values()]
        }

        with open(arquivo_estilos, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)


# Instância global de configurações
settings = Settings()
