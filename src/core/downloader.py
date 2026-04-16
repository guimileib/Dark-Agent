"""Sistema de download com 7 estratégias de fallback"""

import subprocess
import logging
import sys
import json
from pathlib import Path
from typing import Optional, Tuple
import time

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Downloader robusto com 7 estratégias de fallback"""

    # Default strategy order (class-level, never mutated)
    _DEFAULT_STRATEGIES_YOUTUBE = [
        "_estrategia_1_ytdlp_android",
        "_estrategia_2_ytdlp_ios",
        "_estrategia_3_ytdlp_web",
        "_estrategia_4_ytdlp_bypass",
        "_estrategia_5_ytdlp_merge_manual",
        "_estrategia_6_pytube_progressive",
        "_estrategia_7_ffmpeg_merge",
    ]

    _DEFAULT_STRATEGIES_OTHER = [
        "_estrategia_3_ytdlp_web",
        "_estrategia_4_ytdlp_bypass",
        "_estrategia_7_ffmpeg_merge",
        "_estrategia_1_ytdlp_android",
        "_estrategia_2_ytdlp_ios",
        "_estrategia_5_ytdlp_merge_manual",
        "_estrategia_6_pytube_progressive",
    ]

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_strategies(self, url: str):
        """Return a fresh list of strategy callables based on URL type."""
        if "youtube.com" in url or "youtu.be" in url:
            names = self._DEFAULT_STRATEGIES_YOUTUBE
        else:
            names = self._DEFAULT_STRATEGIES_OTHER
        return [getattr(self, name) for name in names]

    def download(self, url: str, qualidade: str = "720p", timeout: int = 300) -> Tuple[bool, Optional[Path], str]:
        """
        Tenta baixar vídeo usando todas as estratégias disponíveis.

        Returns:
            (sucesso, caminho_arquivo, estrategia_usada)
        """
        logger.info(f"Iniciando download: {url} - Qualidade: {qualidade}")

        estrategias = self._get_strategies(url)

        for i, estrategia in enumerate(estrategias, 1):
            estrategia_nome = estrategia.__name__
            logger.info(f"Tentando estratégia {i}/{len(estrategias)}: {estrategia_nome}")

            try:
                inicio = time.time()
                caminho = estrategia(url, qualidade, timeout)
                tempo = time.time() - inicio

                if caminho and caminho.exists():
                    logger.info(f"Sucesso com {estrategia_nome} em {tempo:.1f}s")
                    return True, caminho, estrategia_nome

            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout em {estrategia_nome} após {timeout}s")
                continue
            except Exception as e:
                logger.warning(f"Falha em {estrategia_nome}: {e}")
                continue

        logger.error("Todas as estratégias falharam!")
        return False, None, "none"

    def _run_ytdlp(self, cmd: list, timeout: int) -> Optional[Path]:
        """Helper para rodar yt-dlp com timeout e tratamento de erro"""
        try:
            base_cmd = [sys.executable, "-m", "yt_dlp"]

            # Remove "yt-dlp" from the beginning if present
            if cmd and cmd[0] == "yt-dlp":
                cmd = cmd[1:]

            # --- COOKIES SUPPORT ---
            try:
                from config.settings import settings
                if settings.cookies_file.exists():
                    base_cmd.extend(["--cookies", str(settings.cookies_file)])
                else:
                    base_cmd.extend(["--cookies-from-browser", "chrome"])
            except Exception:
                from config.paths import COOKIES_FILE
                if COOKIES_FILE.exists():
                    base_cmd.extend(["--cookies", str(COOKIES_FILE)])

            full_cmd = base_cmd + cmd

            # Adicionar flags para evitar hangs e ignorar erros de certificado
            full_cmd.extend(["--socket-timeout", "30", "--no-check-certificate"])

            logger.debug(f"Executando: {' '.join(full_cmd)}")

            # Snapshot existing .mp4 files BEFORE download to avoid race conditions
            existing_mp4s = set(self.output_dir.glob("*.mp4"))

            resultado = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )

            if resultado.returncode == 0:
                new_files = [f for f in self.output_dir.glob("*.mp4") if f not in existing_mp4s]
                if new_files:
                    return max(new_files, key=lambda p: p.stat().st_mtime)
                # Fallback: check all files if snapshot missed (e.g. overwrite)
                arquivos = list(self.output_dir.glob("*.mp4"))
                if arquivos:
                    return max(arquivos, key=lambda p: p.stat().st_mtime)
            else:
                logger.error(f"Erro yt-dlp (Exit Code {resultado.returncode}):")
                logger.error(f"STDOUT: {resultado.stdout}")
                logger.error(f"STDERR: {resultado.stderr}")

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout no yt-dlp após {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Erro ao executar yt-dlp: {e}")

        return None

    def _estrategia_1_ytdlp_android(self, url: str, qualidade: str, timeout: int) -> Optional[Path]:
        """Estratégia 1: yt-dlp com user-agent Android"""
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
        """Estratégia 2: yt-dlp com user-agent iOS"""
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
        """Estratégia 3: yt-dlp genérico"""
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
        """Estratégia 5: Download separado de vídeo e áudio via yt-dlp + merge FFmpeg"""
        import uuid
        uid = uuid.uuid4().hex[:8]
        output_video = self.output_dir / f"temp_video_{uid}.mp4"
        output_audio = self.output_dir / f"temp_audio_{uid}.m4a"
        output_final = self.output_dir / f"merged_video_{uid}.mp4"

        # Use _run_ytdlp for cookies/flags support
        half_timeout = int(timeout / 2)

        # Download video only
        cmd_video = [
            "yt-dlp",
            "-f", f"bestvideo[height<={qualidade[:-1]}]",
            "-o", str(output_video),
            url
        ]
        self._run_ytdlp(cmd_video, half_timeout)

        # Download audio only
        cmd_audio = [
            "yt-dlp",
            "-f", "bestaudio",
            "-o", str(output_audio),
            url
        ]
        self._run_ytdlp(cmd_audio, half_timeout)

        # Merge com FFmpeg
        if output_video.exists() and output_audio.exists():
            cmd_merge = [
                "ffmpeg",
                "-i", str(output_video),
                "-i", str(output_audio),
                "-c:v", "copy",
                "-c:a", "aac",
                "-y",
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
            "-y",
            str(output_path)
        ]

        resultado = subprocess.run(cmd, capture_output=True, timeout=timeout)

        if resultado.returncode == 0 and output_path.exists():
            return output_path

        return None

    def get_video_info(self, url: str) -> dict:
        """Obtém informações do vídeo usando yt-dlp (via python -m)"""
        try:
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--dump-json",
                "--no-download",
                "--no-check-certificate",
                url
            ]

            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if resultado.returncode == 0:
                return json.loads(resultado.stdout)
        except Exception as e:
            logger.warning(f"Erro ao obter info do vídeo: {e}")

        return {}
