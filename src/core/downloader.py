"""Sistema de download com 7 estratégias de fallback"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple
import time

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Downloader robusto com 7 estratégias de fallback"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.estrategias = [
            self._estrategia_1_ytdlp_android,
            self._estrategia_2_ytdlp_ios,
            self._estrategia_3_ytdlp_web,
            self._estrategia_4_ytdlp_bypass,
            self._estrategia_5_ytdlp_merge_manual,
            self._estrategia_6_pytube_progressive,
            self._estrategia_7_ffmpeg_merge
        ]
    
    def download(self, url: str, qualidade: str = "720p", timeout: int = 300) -> Tuple[bool, Optional[Path], str]:
        """
        Tenta baixar vídeo usando todas as estratégias disponíveis
        
        Returns:
            (sucesso, caminho_arquivo, estrategia_usada)
        """
        logger.info(f"Iniciando download: {url} - Qualidade: {qualidade}")
        
        for i, estrategia in enumerate(self.estrategias, 1):
            estrategia_nome = estrategia.__name__
            logger.info(f"Tentando estratégia {i}/7: {estrategia_nome}")
            
            try:
                inicio = time.time()
                caminho = estrategia(url, qualidade, timeout)
                tempo = time.time() - inicio
                
                if caminho and caminho.exists():
                    logger.info(f"✓ Sucesso com {estrategia_nome} em {tempo:.1f}s")
                    return True, caminho, estrategia_nome
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"✗ Timeout em {estrategia_nome} após {timeout}s")
                continue
            except Exception as e:
                logger.warning(f"✗ Falha em {estrategia_nome}: {e}")
                continue
        
        logger.error("Todas as 7 estratégias falharam!")
        return False, None, "none"
    
    def _run_ytdlp(self, cmd: list, timeout: int) -> Optional[Path]:
        """Helper para rodar yt-dlp com timeout e tratamento de erro"""
        try:
            # Use sys.executable to ensure we use the same python environment
            import sys
            base_cmd = [sys.executable, "-m", "yt_dlp"]
            
            # Remove "yt-dlp" from the beginning if present, as checking strategies might include it
            if cmd[0] == "yt-dlp":
                cmd = cmd[1:]
                
            full_cmd = base_cmd + cmd
            
            # Adicionar flags para evitar hangs e ignorar erros de certificado
            full_cmd.extend(["--socket-timeout", "30", "--no-check-certificate"])
            
            logger.debug(f"Executando: {' '.join(full_cmd)}")
            
            resultado = subprocess.run(
                full_cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            
            if resultado.returncode == 0:
                # Encontrar arquivo criado
                arquivos = list(self.output_dir.glob("*.mp4"))
                if arquivos:
                    return max(arquivos, key=lambda p: p.stat().st_mtime)
            else:
                logger.debug(f"Erro yt-dlp: {resultado.stderr}")
                
        except subprocess.TimeoutExpired:
            raise
        except Exception as e:
            logger.error(f"Erro ao executar yt-dlp: {e}")
            
        return None

    def _estrategia_1_ytdlp_android(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 1: yt-dlp com user-agent Android (Bom para YouTube)"""
        output_path = self.output_dir / "%(title)s.%(ext)s"
        
        cmd = [
            "yt-dlp",
            "--user-agent", "com.google.android.youtube/17.36.4 (Linux; U; Android 12) gzip",
            "-f", f"bestvideo[height<={qualidade[:-1]}]+bestaudio/best/best",
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            url
        ]
        return self._run_ytdlp(cmd, timeout)
    
    def _estrategia_2_ytdlp_ios(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 2: yt-dlp com user-agent iOS (Bom para YouTube)"""
        output_path = self.output_dir / "%(title)s.%(ext)s"
        
        cmd = [
            "yt-dlp",
            "--user-agent", "com.google.ios.youtube/17.36.4 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)",
            "-f", f"bestvideo[height<={qualidade[:-1]}]+bestaudio/best/best",
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            url
        ]
        return self._run_ytdlp(cmd, timeout)
    
    def _estrategia_3_ytdlp_web(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 3: yt-dlp genérico (Bom para sites gerais)"""
        output_path = self.output_dir / "%(title)s.%(ext)s"
        
        cmd = [
            "yt-dlp",
            "-f", f"bestvideo[height<={qualidade[:-1]}]+bestaudio/best/best",
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            url
        ]
        return self._run_ytdlp(cmd, timeout)
    
    def _estrategia_4_ytdlp_bypass(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 4: yt-dlp com bypass de restrições geográficas"""
        output_path = self.output_dir / "%(title)s.%(ext)s"
        
        cmd = [
            "yt-dlp",
            "--geo-bypass",
            "-f", f"bestvideo[height<={qualidade[:-1]}]+bestaudio/best/best",
            "--merge-output-format", "mp4",
            "-o", str(output_path),
            url
        ]
        return self._run_ytdlp(cmd, timeout)
    
    def _estrategia_5_ytdlp_merge_manual(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 5: Download separado de vídeo e áudio + merge manual"""
        output_video = self.output_dir / "temp_video.mp4"
        output_audio = self.output_dir / "temp_audio.m4a"
        output_final = self.output_dir / "merged_video.mp4"
        
        # Baixar vídeo
        cmd_video = [
            "yt-dlp",
            "-f", f"bestvideo[height<={qualidade[:-1]}]",
            "-o", str(output_video),
            url
        ]
        subprocess.run(cmd_video, capture_output=True, timeout=timeout/2)
        
        # Baixar áudio
        cmd_audio = [
            "yt-dlp",
            "-f", "bestaudio",
            "-o", str(output_audio),
            url
        ]
        subprocess.run(cmd_audio, capture_output=True, timeout=timeout/2)
        
        # Merge com FFmpeg
        if output_video.exists() and output_audio.exists():
            cmd_merge = [
                "ffmpeg",
                "-i", str(output_video),
                "-i", str(output_audio),
                "-c:v", "copy",
                "-c:a", "aac",
                str(output_final)
            ]
            resultado = subprocess.run(cmd_merge, capture_output=True, timeout=60)
            
            # Limpar temporários
            output_video.unlink(missing_ok=True)
            output_audio.unlink(missing_ok=True)
            
            if resultado.returncode == 0 and output_final.exists():
                return output_final
        
        return None
    
    def _estrategia_6_pytube_progressive(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 6: PyTube com stream progressivo"""
        try:
            from pytube import YouTube
            
            yt = YouTube(url)
            
            # Tentar stream progressivo (vídeo+áudio junto)
            stream = yt.streams.filter(
                progressive=True,
                file_extension='mp4'
            ).order_by('resolution').desc().first()
            
            if stream:
                output_path = stream.download(output_path=str(self.output_dir), timeout=timeout)
                return Path(output_path)
            
        except Exception as e:
            logger.warning(f"PyTube falhou: {e}")
        
        return None
    
    def _estrategia_7_ffmpeg_merge(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 7: FFmpeg direto (última tentativa)"""
        output_path = self.output_dir / "ffmpeg_download.mp4"
        
        cmd = [
            "ffmpeg",
            "-i", url,
            "-c", "copy",
            str(output_path)
        ]
        
        resultado = subprocess.run(cmd, capture_output=True, timeout=timeout)
        
        if resultado.returncode == 0 and output_path.exists():
            return output_path
        
        return None
    
    def get_video_info(self, url: str) -> dict:
        """Obtém informações do vídeo usando yt-dlp"""
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            url
        ]
        
        resultado = subprocess.run(cmd, capture_output=True, text=True)
        
        if resultado.returncode == 0:
            import json
            return json.loads(resultado.stdout)
        
        return {}
