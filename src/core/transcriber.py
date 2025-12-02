"""Transcrição otimizada com Whisper"""

import logging
import time
from pathlib import Path
from typing import Optional, Dict
import torch

logger = logging.getLogger(__name__)

# Cache global de modelos
MODEL_CACHE = {}


class Transcriber:
    """Transcri otimizada com Whisper"""
    
    CONFIGS = {
        "tiny": {"beam_size": 3, "best_of": 3, "temperature": 0.0},
        "base": {"beam_size": 4, "best_of": 4, "temperature": [0.0, 0.2]},
        "small": {"beam_size": 5, "best_of": 5, "temperature": [0.0, 0.2, 0.4]},
        "medium": {"beam_size": 5, "best_of": 5, "temperature": [0.0, 0.2, 0.4]}
    }
    
    def __init__(self, modelo: str = "base", device: str = "auto", idioma: str = None):
        self.modelo_nome = modelo
        self.idioma = idioma  # None = detecção automática
        
        # Detectar device
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        
        logger.info(f"Transcriber inicializado - Modelo: {modelo}, Device: {self.device}")
    
    def transcrever(self, audio_path: Path, callback_progresso=None) -> dict:
        """
        Transcreve áudio usando Whisper
        
        Args:
            audio_path: Caminho para o arquivo de áudio
            callback_progresso: Função para atualizar progresso (opcional)
        
        Returns:
            dict com resultado da transcrição
        """
        logger.info(f"Iniciando transcrição: {audio_path}")
        inicio = time.time()
        
        try:
            # Carregar modelo (usa cache se já carregado)
            modelo = self._carregar_modelo()
            
            if callback_progresso:
                callback_progresso("Transcrevendo áudio...", 20)
            
            # Configurações otimizadas por modelo
            config = self.CONFIGS.get(self.modelo_nome, self.CONFIGS["base"])
            
            # Transcrever
            resultado = modelo.transcribe(
                str(audio_path),
                language=self.idioma,  # None = auto-detect
                task="transcribe",
                word_timestamps=True,  # CRÍTICO: habilitar timestamps de palavras
                fp16=(self.device == "cuda"),
                verbose=False,
                **config
            )
            
            if callback_progresso:
                callback_progresso("Transcrição concluída!", 100)
            
            tempo = time.time() - inicio
            logger.info(f"Transcrição concluída em {tempo:.1f}s")
            
            # Liberar memória GPU
            if self.device == "cuda":
                torch.cuda.empty_cache()
            
            # Processar resultado
            return self._processar_resultado(resultado, tempo)
            
        except Exception as e:
            logger.error(f"Erro na transcrição: {e}")
            raise
    
    def _carregar_modelo(self):
        """Carrega modelo Whisper com cache"""
        global MODEL_CACHE
        
        cache_key = f"{self.modelo_nome}_{self.device}"
        
        if cache_key not in MODEL_CACHE:
            logger.info(f"Carregando modelo Whisper '{self.modelo_nome}'...")
            
            try:
                import whisper
                
                modelo = whisper.load_model(
                    self.modelo_nome,
                    device=self.device,
                    download_root=None
                )
                
                MODEL_CACHE[cache_key] = modelo
                logger.info(f"Modelo carregado com sucesso")
                
            except Exception as e:
                logger.error(f"Erro ao carregar modelo: {e}")
                raise
        
        return MODEL_CACHE[cache_key]
    
    def _processar_resultado(self, resultado: dict, tempo: float) -> dict:
        """Processa resultado bruto do Whisper"""
        
        # Extrair segmentos com palavras
        segmentos = []
        for seg in resultado.get("segments", []):
            segmento = {
                "id": seg["id"],
                "texto": seg["text"].strip(),
                "inicio": seg["start"],
                "fim": seg["end"],
                "palavras": []
            }
            
            # Extrair palavras individuais (se disponível)
            if "words" in seg:
                for word in seg["words"]:
                    palavra = {
                        "texto": word.get("word", "").strip(),
                        "inicio": word.get("start", 0),
                        "fim": word.get("end", 0),
                        "confianca": word.get("probability", 1.0)
                    }
                    segmento["palavras"].append(palavra)
            else:
                # Estimativa simples se não tiver palavras individuais
                palavras_texto = seg["text"].strip().split()
                duracao_seg = seg["end"] - seg["start"]
                tempo_por_palavra = duracao_seg / max(len(palavras_texto), 1)
                
                for i, palavra_texto in enumerate(palavras_texto):
                    inicio_palavra = seg["start"] + (i * tempo_por_palavra)
                    fim_palavra = inicio_palavra + tempo_por_palavra
                    
                    palavra = {
                        "texto": palavra_texto,
                        "inicio": inicio_palavra,
                        "fim": fim_palavra,
                        "confianca": 1.0
                    }
                    segmento["palavras"].append(palavra)
            
            segmentos.append(segmento)
        
        return {
            "texto_completo": resultado.get("text", ""),
            "idioma": resultado.get("language", self.idioma),
            "segmentos": segmentos,
            "tempo_processamento": tempo,
            "modelo": self.modelo_nome
        }
    
    def extrair_audio_de_video(self, video_path: Path, output_path: Path) -> bool:
        """Extrai áudio do vídeo usando FFmpeg"""
        import subprocess
        
        logger.info(f"Extraindo áudio de {video_path}")
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",  # Sem vídeo
            "-acodec", "pcm_s16le",  # Codec de áudio para Whisper
            "-ar", "16000",  # Sample rate 16kHz
            "-ac", "1",  # Mono
            "-y",  # Sobrescrever
            str(output_path)
        ]
        
        try:
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if resultado.returncode == 0 and output_path.exists():
                logger.info(f"Áudio extraído com sucesso: {output_path}")
                return True
            else:
                logger.error(f"Erro ao extrair áudio: {resultado.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exceção ao extrair áudio: {e}")
            return False
    
    @staticmethod
    def limpar_cache():
        """Limpa cache de modelos"""
        global MODEL_CACHE
        MODEL_CACHE.clear()
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("Cache de modelos limpo")
