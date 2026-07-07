"""Sistema de download com 7 estratégias de fallback"""

import subprocess
import logging
import re
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
                    if not self._tem_video_e_audio(caminho):
                        logger.warning(
                            f"{estrategia_nome} retornou arquivo sem vídeo+áudio "
                            f"({caminho.name}) — tentando próxima estratégia"
                        )
                        continue
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

    @staticmethod
    def _tem_video_e_audio(caminho: Path) -> bool:
        """Confere via ffprobe se o arquivo tem stream de vídeo E de áudio.

        Evita aceitar intermediários de merge do yt-dlp (video-only) como
        resultado final. Se o ffprobe não estiver disponível, não bloqueia.
        """
        try:
            from core.validator import VideoValidator
            streams = VideoValidator.obter_metadados(caminho).get("streams", []) or []
            if not streams:
                return True  # ffprobe indisponível/falhou — não bloquear
            tipos = {s.get("codec_type") for s in streams}
            return "video" in tipos and "audio" in tipos
        except Exception:
            return True

    @staticmethod
    def _resolve_cookies_file() -> Optional[Path]:
        """Procura cookies.txt em APP_DIR (ao lado do .exe) e em BUNDLE_DIR/src (dev).

        Não há fallback para --cookies-from-browser: o Chrome 127+ usa
        App-Bound Encryption e o DPAPI falha em decifrar os cookies de fora
        do processo do navegador (yt-dlp issue #10927). Usuários que precisam
        de cookies (ex.: YouTube com idade restrita) devem exportar um
        cookies.txt e colocá-lo ao lado do executável.
        """
        try:
            from config.paths import APP_DIR, BUNDLE_DIR
            candidates = [
                APP_DIR / "cookies.txt",
                BUNDLE_DIR / "src" / "cookies.txt",
            ]
        except Exception:
            return None
        for c in candidates:
            try:
                if c.exists():
                    return c
            except OSError:
                continue
        return None

    def _run_ytdlp(self, cmd: list, timeout: int) -> Optional[Path]:
        """Helper para rodar yt-dlp com timeout e tratamento de erro"""
        try:
            base_cmd = [sys.executable, "-m", "yt_dlp"]

            # Remove "yt-dlp" from the beginning if present
            if cmd and cmd[0] == "yt-dlp":
                cmd = cmd[1:]

            cookies_path = self._resolve_cookies_file()
            if cookies_path:
                base_cmd.extend(["--cookies", str(cookies_path)])

            full_cmd = base_cmd + cmd

            # Paralelismo de fragmentos (HLS/DASH). Ler do settings com fallback
            # seguro para 8 — sweet spot pra HLS residencial; valores >16
            # tendem a derrubar em rate-limit de CDN.
            try:
                from config.settings import settings
                concurrent_frags = max(1, int(getattr(settings, "ytdlp_concurrent_fragments", 8)))
            except Exception:
                concurrent_frags = 8

            # Adicionar flags para evitar hangs, ignorar erros de cert e paralelizar.
            full_cmd.extend([
                "--socket-timeout", "30",
                "--no-check-certificate",
                "--concurrent-fragments", str(concurrent_frags),
                "--http-chunk-size", "10M",
                # Imprime o caminho final REAL (pós-merge/move) no stdout.
                # Sem isso, a heurística de glob por mtime pode devolver um
                # intermediário video-only órfão (ex.: "Titulo.fhls-4429.mp4")
                # de um download anterior interrompido.
                "--no-simulate",
                "--print", "after_move:filepath",
            ])

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
                # Caminho(s) impressos por --print after_move:filepath (um por
                # entrada; o último é o mais recente).
                for linha in reversed(resultado.stdout.splitlines()):
                    candidato = Path(linha.strip())
                    if linha.strip() and candidato.is_file():
                        return candidato
                # Fallback: glob por mtime, ignorando intermediários de merge
                # do yt-dlp (sufixo de format-id, ex.: "Titulo.fhls-4429.mp4").
                nao_intermediario = lambda p: not re.search(r"\.f[\w-]+\.mp4$", p.name)
                new_files = [
                    f for f in self.output_dir.glob("*.mp4")
                    if f not in existing_mp4s and nao_intermediario(f)
                ]
                if new_files:
                    return max(new_files, key=lambda p: p.stat().st_mtime)
                # Último recurso: qualquer mp4 não-intermediário (e.g. overwrite)
                arquivos = [f for f in self.output_dir.glob("*.mp4") if nao_intermediario(f)]
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
        try:
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

                if resultado.returncode == 0 and output_final.exists():
                    return output_final

            return None
        finally:
            # Limpar temporários mesmo quando só um dos downloads funcionou
            # (senão temp_video_*/temp_audio_* órfãos acumulam em raw/).
            output_video.unlink(missing_ok=True)
            output_audio.unlink(missing_ok=True)

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
