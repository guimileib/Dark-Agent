"""Operações de edição de vídeo com FFmpeg"""

import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import logging
from pathlib import Path
from typing import Callable, Optional, List

logger = logging.getLogger(__name__)


def _probe_duration(video_path: Path) -> Optional[float]:
    """Retorna a duração do vídeo em segundos via ffprobe, ou None se falhar.

    Usado para mapear `out_time_us` do `-progress pipe:1` em pct (0–100).
    """
    sp_kw: dict = {}
    if sys.platform == "win32":
        sp_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL, **sp_kw,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def _run_ffmpeg_with_progress(
    cmd: list,
    *,
    duration_sec: Optional[float],
    progress_callback: Optional[Callable[[float], None]],
    output_path: Path,
    timeout: int = 3600,
) -> bool:
    """Executa ffmpeg via Popen, parseia `-progress pipe:1` e drena stderr em thread.

    O fluxo bloqueante de `subprocess.run(capture_output=True)` esconde o
    progresso do encode até terminar. Aqui lemos `out_time_us=` linha-por-linha
    e chamamos `progress_callback(pct)` em cada incremento de 1%.

    `cmd` deve incluir `-progress pipe:1` (essa função NÃO adiciona).
    Stderr é drenado num thread separado para não dar deadlock no buffer
    quando ffmpeg escreve avisos.
    """
    sp_kw: dict = {}
    if sys.platform == "win32":
        sp_kw["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            **sp_kw,
        )
    except Exception as e:
        logger.error(f"Falha ao iniciar ffmpeg: {e}")
        return False

    stderr_chunks: List[str] = []

    def _drain_stderr():
        try:
            for line in proc.stderr:
                stderr_chunks.append(line)
        except Exception:
            pass

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    timed_out = {"flag": False}

    def _kill_on_timeout():
        if proc.poll() is None:
            timed_out["flag"] = True
            try:
                proc.kill()
            except OSError:
                pass

    timer = threading.Timer(timeout, _kill_on_timeout)
    timer.daemon = True
    timer.start()

    last_pct_emitted = -1
    try:
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("out_time_us="):
                val = line.split("=", 1)[1]
                if val.isdigit() and duration_sec and duration_sec > 0:
                    pct = min(100.0, int(val) / 1_000_000 / duration_sec * 100)
                    pct_int = int(pct)
                    if progress_callback and pct_int > last_pct_emitted:
                        try:
                            progress_callback(pct)
                        except Exception as cb_err:
                            logger.debug(f"progress_callback raised: {cb_err}")
                        last_pct_emitted = pct_int
            elif line.startswith("progress=end"):
                if progress_callback and last_pct_emitted < 100:
                    try:
                        progress_callback(100.0)
                    except Exception:
                        pass
                break
    finally:
        timer.cancel()
        try:
            rc = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            rc = -1
        stderr_thread.join(timeout=5)

    stderr_text = "".join(stderr_chunks)

    if timed_out["flag"]:
        logger.error(f"Timeout no ffmpeg após {timeout}s")
        return False

    if rc == 0 and output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"✅ Render concluído: {output_path.name} ({size_mb:.2f} MB)")
        return True

    logger.error(f"❌ FFmpeg falhou (rc={rc})")
    if stderr_text:
        logger.error(f"Stderr: {stderr_text[-1000:]}")
    return False


# Posições suportadas pelo marcador permanente (fórmulas FFmpeg)
_MARCADOR_POS = {
    "top_left":      ("24",                  "24"),
    "top_center":    ("(w-text_w)/2",        "24"),
    "top_right":     ("w-text_w-24",         "24"),
    "bottom_left":   ("24",                  "h-text_h-24"),
    "bottom_center": ("(w-text_w)/2",        "h-text_h-24"),
    "bottom_right":  ("w-text_w-24",         "h-text_h-24"),
}


def _ffmpeg_escape_text(text: str) -> str:
    """Escapa texto para o filtro drawtext do FFmpeg."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


def _ffmpeg_escape_path(path: str) -> str:
    """Escapa um caminho para uso DENTRO de single quotes num filtro FFmpeg.

    Aplica três passos cumulativos:
    - `\\` -> `/`  (forward slashes funcionam melhor no Windows com filtros)
    - `:`  -> `\\:` (drive letter colon precisa escape no parser do filtro)
    - `'`  -> `\\'` (apóstrofo fecharia a string single-quoted prematuramente)

    O bug clássico sem o escape de `'`: um arquivo como
    `Tooth Fairy's Tats.ass` vira `Tooth Fairys Tats.ass` no filtro porque
    o parser interpreta `'s Tats.ass` como conteúdo fora das aspas.
    """
    return (
        path.replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", "\\'")
    )


class VideoEditor:
    """Editor de vídeos usando FFmpeg"""
    
    def __init__(self):
        pass
    
    def queimar_legendas(
        self,
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
        preset: str = "medium",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> bool:
        """
        Queima legendas ASS no vídeo, com progresso em tempo real.

        Args:
            video_path: Caminho do vídeo original
            subtitle_path: Caminho do arquivo ASS
            output_path: Caminho do vídeo final
            preset: Preset de encoding (ultrafast, fast, medium, slow)
            progress_callback: Função opcional chamada com pct (0.0–100.0)
                a cada incremento de 1% durante o encode.

        Returns:
            bool indicando sucesso
        """
        logger.info(f"Queimando legendas em {video_path}")

        # Workaround: o parser interno do filtro `subtitles` quebra com
        # apóstrofos no caminho do .ass — testado com 5 variantes de escape
        # e nenhuma resolve. Copiamos o .ass para um path ASCII-safe.
        try:
            tmp_ass = Path(tempfile.gettempdir()) / f"darkagent_sub_{uuid.uuid4().hex[:12]}.ass"
            shutil.copy2(subtitle_path, tmp_ass)
        except OSError as e:
            logger.error(f"Falha ao copiar .ass para temp: {e}")
            return False

        try:
            subtitle_str = _ffmpeg_escape_path(str(tmp_ass))
            duration_sec = _probe_duration(video_path)

            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-loglevel", "error",
                "-i", str(video_path),
                "-vf", f"subtitles='{subtitle_str}'",
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-progress", "pipe:1",
                "-y",
                str(output_path),
            ]

            logger.info(f"Comando FFmpeg: {' '.join(cmd)}")
            logger.info(f"Arquivo de saída esperado: {output_path} (duração: {duration_sec}s)")

            return _run_ffmpeg_with_progress(
                cmd,
                duration_sec=duration_sec,
                progress_callback=progress_callback,
                output_path=output_path,
                timeout=3600,
            )
        finally:
            try:
                tmp_ass.unlink(missing_ok=True)
            except OSError:
                pass
    
    def queimar_marcador(
        self,
        video_path: Path,
        texto: str,
        output_path: Path,
        posicao: str = "top_right",
        tamanho_fonte: int = 36,
        preset: str = "fast",
    ) -> bool:
        """Queima um marcador de texto permanente (sempre visível) no vídeo.

        Usado para identificar o vídeo (ex.: "Episódio 5") sem timing —
        o texto aparece em todos os frames.
        """
        if not texto or not texto.strip():
            logger.warning("Marcador vazio — pulando")
            return False

        # Resolve fonte (Windows fallback)
        fonte_candidatos = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        fonte = next((p for p in fonte_candidatos if Path(p).exists()), None)

        x_expr, y_expr = _MARCADOR_POS.get(posicao, _MARCADOR_POS["top_right"])
        text_safe = _ffmpeg_escape_text(texto.strip())

        drawtext_parts = [
            f"text='{text_safe}'",
            f"fontsize={tamanho_fonte}",
            "fontcolor=white",
            "borderw=3",
            "bordercolor=black",
            "box=1",
            "boxcolor=black@0.45",
            "boxborderw=10",
            f"x={x_expr}",
            f"y={y_expr}",
        ]
        if fonte:
            drawtext_parts.insert(1, f"fontfile='{_ffmpeg_escape_path(fonte)}'")

        drawtext = "drawtext=" + ":".join(drawtext_parts)

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", drawtext,
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", "20",
            "-c:a", "copy",
            "-y",
            str(output_path),
        ]

        sp_kw: dict = {}
        if sys.platform == "win32":
            sp_kw["creationflags"] = subprocess.CREATE_NO_WINDOW

        logger.info(f"Queimando marcador '{texto}' em {video_path.name} (pos={posicao})")
        try:
            resultado = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600,
                stdin=subprocess.DEVNULL, **sp_kw,
            )
            if resultado.returncode == 0 and output_path.exists():
                logger.info(f"Marcador queimado com sucesso: {output_path.name}")
                return True
            logger.error(
                f"FFmpeg drawtext falhou (rc={resultado.returncode}): "
                f"{resultado.stderr[-500:] if resultado.stderr else ''}"
            )
            return False
        except subprocess.TimeoutExpired:
            logger.error("Timeout ao queimar marcador")
            return False
        except Exception as exc:
            logger.error(f"Exceção ao queimar marcador: {exc}")
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
