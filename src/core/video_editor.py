"""Operações de edição de vídeo com FFmpeg"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class VideoEditor:
    """Editor de vídeos usando FFmpeg"""
    
    def __init__(self):
        pass
    
    def queimar_legendas(
        self,
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
        preset: str = "medium"
    ) -> bool:
        """
        Queima legendas ASS no vídeo
        
        Args:
            video_path: Caminho do vídeo original
            subtitle_path: Caminho do arquivo ASS
            output_path: Caminho do vídeo final
            preset: Preset de encoding (ultrafast, fast, medium, slow)
        
        Returns:
            bool indicando sucesso
        """
        logger.info(f"Queimando legendas em {video_path}")
        
        # Para Windows, o filtro subtitles funciona melhor com forward slashes e escape no drive
        # Ex: C:/path/to/file.ass -> C\:/path/to/file.ass
        subtitle_str = str(subtitle_path).replace('\\', '/').replace(':', '\\:')
        
        # Comando FFmpeg
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"subtitles='{subtitle_str}'",  # Aspas simples ajudam
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-y",
            str(output_path)
        ]
        
        # Log do comando para debug
        logger.info(f"Comando FFmpeg: {' '.join(cmd)}")
        logger.info(f"Arquivo de saída esperado: {output_path}")
        
        try:
            # stdin=subprocess.DEVNULL evita que o ffmpeg trave esperando input
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,
                stdin=subprocess.DEVNULL
            )
            
            logger.info(f"FFmpeg returncode: {resultado.returncode}")
            logger.info(f"FFmpeg stdout: {resultado.stdout[-500:] if resultado.stdout else 'vazio'}")
            
            if resultado.returncode == 0:
                if output_path.exists():
                    file_size = output_path.stat().st_size / (1024 * 1024)  # MB
                    logger.info(f"✅ Legendas queimadas com sucesso: {output_path} ({file_size:.2f} MB)")
                    return True
                else:
                    logger.error(f"❌ FFmpeg retornou sucesso mas arquivo não foi criado: {output_path}")
                    logger.error(f"Stderr: {resultado.stderr[-1000:]}")
                    return False
            else:
                logger.error(f"❌ Erro ao queimar legendas (código {resultado.returncode})")
                logger.error(f"Stderr: {resultado.stderr[-1000:]}")
                return False
                
        except Exception as e:
            logger.error(f"Exceção ao queimar legendas: {e}")
            return False
    
    def adicionar_logo(
        self,
        video_path: Path,
        logo_path: Path,
        output_path: Path,
        posicao: str = "top_right",
        opacidade: float = 0.8
    ) -> bool:
        """
        Adiciona logo em overlay no vídeo
        
        Args:
            video_path: Vídeo original
            logo_path: Imagem do logo (PNG com transparência)
            output_path: Vídeo final
            posicao: Posição do logo (top_left, top_right, bottom_left, bottom_right)
            opacidade: Opacidade do logo (0.0 a 1.0)
        
        Returns:
            bool indicando sucesso
        """
        logger.info(f"Adicionando logo ao vídeo")
        
        # Definir posição
        posicoes = {
            "top_left": "10:10",
            "top_right": "W-w-10:10",
            "bottom_left": "10:H-h-10",
            "bottom_right": "W-w-10:H-h-10",
            "center": "(W-w)/2:(H-h)/2"
        }
        
        overlay_pos = posicoes.get(posicao, posicoes["top_right"])
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-i", str(logo_path),
            "-filter_complex",
            f"[1:v]format=rgba,colorchannelmixer=aa={opacidade}[logo];[0:v][logo]overlay={overlay_pos}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "copy",
            "-y",
            str(output_path)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            
            if resultado.returncode == 0:
                logger.info(f"Logo adicionado com sucesso")
                return True
            else:
                logger.error(f"Erro ao adicionar logo: {resultado.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exceção ao adicionar logo: {e}")
            return False
    
    def cortar_video(
        self,
        video_path: Path,
        inicio: float,
        duracao: float,
        output_path: Path
    ) -> bool:
        """
        Corta um trecho do vídeo
        
        Args:
            video_path: Vídeo original
            inicio: Tempo de início em segundos
            duracao: Duração do corte em segundos
            output_path: Arquivo de saída
        
        Returns:
            bool indicando sucesso
        """
        logger.info(f"Cortando vídeo: {inicio}s por {duracao}s")
        
        cmd = [
            "ffmpeg",
            "-ss", str(inicio),
            "-i", str(video_path),
            "-t", str(duracao),
            "-c:v", "libx264",
            "-c:a", "copy",
            "-y",
            str(output_path)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if resultado.returncode == 0:
                logger.info(f"Vídeo cortado com sucesso")
                return True
            else:
                logger.error(f"Erro ao cortar vídeo: {resultado.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exceção ao cortar vídeo: {e}")
            return False
    
    def gerar_cortes_automaticos(
        self,
        video_path: Path,
        transcricao: dict,
        numero_cortes: int,
        duracao_corte: int,
        output_dir: Path
    ) -> List[Path]:
        """
        Gera cortes automáticos baseados na transcrição
        
        Args:
            video_path: Vídeo original
            transcricao: Transcrição com timestamps
            numero_cortes: Quantidade de cortes a gerar
            duracao_corte: Duração de cada corte em segundos
            output_dir: Diretório de saída
        
        Returns:
            Lista de caminhos dos cortes gerados
        """
        logger.info(f"Gerando {numero_cortes} cortes de {duracao_corte}s")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        segmentos = transcricao.get("segmentos", [])
        if not segmentos:
            logger.warning("Transcrição sem segmentos")
            return []
        
        # Selecionar pontos de corte (distribuídos ao longo do vídeo)
        duracao_total = segmentos[-1]["fim"]
        intervalo = duracao_total / (numero_cortes + 1)
        
        cortes_gerados = []
        
        for i in range(numero_cortes):
            tempo_alvo = intervalo * (i + 1)
            
            # Encontrar início de segmento mais próximo
            segmento_mais_proximo = min(
                segmentos,
                key=lambda s: abs(s["inicio"] - tempo_alvo)
            )
            
            inicio = segmento_mais_proximo["inicio"]
            
            # Garantir que não ultrapassa o vídeo
            if inicio + duracao_corte > duracao_total:
                inicio = max(0, duracao_total - duracao_corte)
            
            output_path = output_dir / f"corte_{i+1:02d}.mp4"
            
            if self.cortar_video(video_path, inicio, duracao_corte, output_path):
                cortes_gerados.append(output_path)
        
        logger.info(f"Gerados {len(cortes_gerados)} cortes")
        return cortes_gerados
    
    def redimensionar_video(
        self,
        video_path: Path,
        output_path: Path,
        formato: str = "vertical"
    ) -> bool:
        """
        Redimensiona vídeo para formato específico
        
        Args:
            video_path: Vídeo original
            output_path: Vídeo redimensionado
            formato: "vertical" (9:16), "horizontal" (16:9), "square" (1:1)
        
        Returns:
            bool indicando sucesso
        """
        formatos = {
            "vertical": "1080:1920",
            "horizontal": "1920:1080",
            "square": "1080:1080"
        }
        
        resolucao = formatos.get(formato, formatos["vertical"])
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"scale={resolucao}:force_original_aspect_ratio=decrease,pad={resolucao}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "copy",
            "-y",
            str(output_path)
        ]
        
        try:
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            
            if resultado.returncode == 0:
                logger.info(f"Vídeo redimensionado para {formato}")
                return True
            else:
                logger.error(f"Erro ao redimensionar: {resultado.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exceção ao redimensionar: {e}")
            return False
