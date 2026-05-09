import logging
import re
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QProgressBar, QLabel, QMessageBox, QTabWidget, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon

from config.settings import settings
from config.paths import APP_DIR
from ui.widgets import DownloadWidget, SubtitleWidget, ClipWidget, UploadWidget, EditorWidget
from core import (
    VideoDownloader, VideoValidator, Transcriber,
    SubtitleGenerator, VideoEditor, PreviewRenderer
)

logger = logging.getLogger(__name__)


# ─── Auto-update via GitHub Releases ──────────────────────────────────────
GITHUB_REPO = "guimileib/Dark-Agent"
RELEASE_ASSET_NAME = "DarkAgentLauncher.exe"


def _parse_version(v: str) -> tuple:
    """Extrai tupla numérica de uma versão tipo 'v2.0.1' ou '2.0.1-rc1'."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in nums) if nums else (0,)


def _is_newer(remote: str, local: str) -> bool:
    try:
        return _parse_version(remote) > _parse_version(local)
    except Exception:
        return False


class UpdateCheckerThread(QThread):
    """Consulta a GitHub Releases API e sinaliza se há um release mais novo."""

    # tag_name (sem 'v'), URL do .exe, corpo do release
    update_available = pyqtSignal(str, str, str)

    def run(self):
        try:
            import requests
            from src import __version__

            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            resp = requests.get(
                api_url,
                timeout=10,
                headers={"Accept": "application/vnd.github+json"},
            )

            if resp.status_code == 404:
                logger.debug("Nenhum release publicado ainda no repositório.")
                return
            resp.raise_for_status()

            data = resp.json()
            tag_raw = (data.get("tag_name") or "").strip()
            tag = tag_raw.lstrip("v").strip()
            if not tag:
                return

            if not _is_newer(tag, __version__):
                logger.debug(f"Versão atual ({__version__}) >= release mais recente ({tag}).")
                return

            asset = next(
                (a for a in data.get("assets", []) if a.get("name") == RELEASE_ASSET_NAME),
                None,
            )
            if not asset or not asset.get("browser_download_url"):
                logger.warning(f"Release {tag_raw} sem asset '{RELEASE_ASSET_NAME}'.")
                return

            self.update_available.emit(
                tag,
                asset["browser_download_url"],
                data.get("body") or "",
            )
        except Exception as e:
            logger.debug(f"Aviso - Não foi possível verificar atualizações: {e}")


class PreviewGeneratorThread(QThread):
    """Thread para gerar previews de legendas em segundo plano"""
    
    progresso = pyqtSignal(int, int, str)  # atual, total, estilo_nome
    concluido = pyqtSignal()
    
    def __init__(self, estilos):
        super().__init__()
        self.estilos = estilos
    
    def run(self):
        try:
            renderer = PreviewRenderer()
            total_previews = 0
            previews_gerados = 0
            
            # Limpar previews antigos
            logger.info("Limpando previews antigos...")
            renderer.limpar_cache()
            
            # Calcular total de previews a gerar (estilos x tamanhos)
            for estilo in self.estilos:
                if hasattr(estilo, 'size_options') and estilo.size_options:
                    total_previews += len(estilo.size_options)
                else:
                    total_previews += 9  # tamanhos padrão
            
            logger.info(f"Gerando {total_previews} previews para {len(self.estilos)} estilos...")
            
            for estilo in self.estilos:
                try:
                    # Gerar previews para todos os tamanhos deste estilo (forçar regeneração)
                    previews = renderer.gerar_previews_todos_tamanhos(estilo, force=True)
                    
                    previews_gerados += len(previews)
                    self.progresso.emit(previews_gerados, total_previews, estilo.nome)
                    
                    logger.info(f"Gerados {len(previews)} previews para {estilo.nome}")
                    
                except Exception as e:
                    logger.warning(f"Erro ao gerar previews para {estilo.nome}: {e}")
                    continue
            
            logger.info(f"Geração de previews concluída: {previews_gerados}/{total_previews}")
            self.concluido.emit()
            
        except Exception as e:
            logger.error(f"Erro na thread de previews: {e}")
            self.concluido.emit()


class ProcessadorThread(QThread):
    progresso = pyqtSignal(str, int)  # mensagem, percentual
    concluido = pyqtSignal(dict)  # resultados {sucesso: [], falha: []}
    
    def __init__(self, config, estilo):
        super().__init__()
        self.config = config
        self.estilo = estilo
    
    def run(self):
        urls = self.config.get("urls", [])
        total_videos = len(urls)
        resultados = {"sucesso": [], "falha": []}
        
        try:
            for i, url in enumerate(urls):
                if self.isInterruptionRequested():
                    logger.info("Processamento interrompido pelo usuário")
                    break

                if not url.strip():
                    continue

                # Base progress calculation
                # Each video takes (100 / total_videos)% of the total progress
                video_progress_start = int((i / total_videos) * 100)
                video_progress_chunk = 100 / total_videos

                def report_progress(msg, step_percent, _start=video_progress_start, _chunk=video_progress_chunk, _idx=i):
                    """
                    step_percent: 0-100 relative to this video
                    global_percent: 0-100 absolute
                    """
                    current_chunk_progress = (step_percent / 100) * _chunk
                    global_percent = int(_start + current_chunk_progress)
                    # Clamp to 100
                    global_percent = min(99, global_percent)

                    # Log formatted message
                    formatted_msg = f"[{_idx+1}/{total_videos}] {msg}"
                    self.progresso.emit(formatted_msg, global_percent)

                logger.info(f"Processando: {url}")
                report_progress("Iniciando...", 0)

                audio_path: Optional[Path] = None
                try:
                    # Check if it is a local file
                    is_local_file = Path(url).exists() and Path(url).is_file()

                    if is_local_file:
                        caminho_video = Path(url)
                        report_progress(f"Arquivo local: {caminho_video.name}", 5)
                    else:
                        # Download
                        report_progress("Baixando vídeo...", 10)
                        downloader = VideoDownloader(self.config["pasta"])
                        sucesso, caminho_video, estrategia = downloader.download(
                            url,
                            self.config["qualidade"]
                        )

                        if not sucesso:
                            resultados["falha"].append((url, "Falha no download"))
                            continue

                    if self.isInterruptionRequested():
                        break

                    # Validar
                    report_progress("Validando vídeo...", 20)
                    valido, checks = VideoValidator.validar_video_completo(caminho_video)

                    if not valido:
                        resultados["falha"].append((url, f"Vídeo inválido: {checks}"))
                        continue

                    # Extrair áudio
                    report_progress("Extraindo áudio...", 30)
                    transcriber = Transcriber(
                        modelo=settings.whisper_model,
                        device=settings.whisper_device,
                        idioma=settings.whisper_language  # None = auto-detect
                    )
                    audio_path = caminho_video.parent / f"audio_temp_{i}.wav"

                    if not transcriber.extrair_audio_de_video(caminho_video, audio_path):
                        resultados["falha"].append((url, "Falha ao extrair áudio"))
                        continue

                    if self.isInterruptionRequested():
                        break

                    # Transcrever
                    report_progress("Transcrevendo com IA...", 50)
                    transcricao = transcriber.transcrever(audio_path)

                    if self.isInterruptionRequested():
                        break

                    # Gerar legendas
                    report_progress("Gerando legendas...", 70)
                    subtitle_gen = SubtitleGenerator()
                    ass_path = caminho_video.parent / f"{caminho_video.stem}.ass"

                    subtitle_gen.gerar_ass(transcricao, self.estilo, ass_path)

                    # Queimar legendas (com progresso em tempo real)
                    report_progress("Renderizando vídeo final...", 85)
                    editor = VideoEditor()
                    output_path = caminho_video.parent / f"{caminho_video.stem}_final.mp4"

                    def _burn_progress(pct: float):
                        # Mapeia 0–100% do encode para 85–94% do passo do vídeo
                        step = 85 + (pct * 0.09)
                        report_progress(f"Renderizando... {pct:.0f}%", step)

                    if not editor.queimar_legendas(
                        caminho_video, ass_path, output_path,
                        progress_callback=_burn_progress,
                    ):
                        resultados["falha"].append((url, "Falha ao renderizar"))
                        continue

                    # Aplicar marcador permanente per-URL, se solicitado
                    markers = self.config.get("markers") or {}
                    marker = markers.get(url)
                    if marker:
                        report_progress("Aplicando marcador...", 95)
                        marked_path = output_path.parent / f"{output_path.stem}_marked.mp4"
                        if editor.queimar_marcador(
                            video_path=output_path,
                            texto=marker["text"],
                            output_path=marked_path,
                            posicao=marker.get("position", "top_right"),
                        ) and marked_path.exists():
                            try:
                                output_path.unlink()
                                marked_path.rename(output_path)
                            except OSError as e:
                                logger.warning(
                                    f"Não foi possível substituir final.mp4 ({e}); usando _marked.mp4"
                                )
                                output_path = marked_path
                        else:
                            logger.warning(
                                f"Marcador falhou para {url}, mantendo vídeo sem marcador"
                            )

                    resultados["sucesso"].append((url, output_path))
                    report_progress("Concluído!", 100)

                except Exception as e:
                    logger.error(f"Erro ao processar {url}: {e}")
                    resultados["falha"].append((url, str(e)))
                finally:
                    # Sempre limpar o .wav temporário (vários GB em vídeos longos),
                    # mesmo em caso de erro ou cancelamento.
                    if audio_path is not None:
                        try:
                            audio_path.unlink(missing_ok=True)
                        except OSError as e:
                            logger.warning(f"Falha ao remover temp audio {audio_path}: {e}")

            self.progresso.emit("Processamento concluído!", 100)
            self.concluido.emit(resultados)

        except Exception as e:
            logger.error(f"Erro fatal no processamento: {e}")
            self.concluido.emit(resultados)


class BatchDownloadThread(QThread):
    """Thread para download de múltiplos vídeos"""
    progresso = pyqtSignal(str, int)  # mensagem, percentual
    concluido = pyqtSignal(dict)  # resultados {sucesso: [], falha: []}

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        urls = self.config.get("urls", [])
        total = len(urls)
        markers = self.config.get("markers") or {}  # {url: {"text", "position"}}
        resultados = {"sucesso": [], "falha": []}

        try:
            for i, url in enumerate(urls):
                if not url.strip():
                    continue

                self.progresso.emit(f"Baixando {i+1}/{total}: {url}...", int((i / total) * 100))

                downloader = VideoDownloader(self.config["pasta"])
                try:
                    sucesso, caminho, estrategia = downloader.download(
                        url,
                        self.config["qualidade"]
                    )

                    if sucesso:
                        # Aplicar marcador permanente per-URL, se solicitado
                        marker = markers.get(url)
                        if marker and caminho:
                            self.progresso.emit(
                                f"Aplicando marcador no vídeo {i+1}/{total}...",
                                int(((i + 0.5) / total) * 100),
                            )
                            caminho_final = self._aplicar_marcador(Path(caminho), marker)
                            if caminho_final:
                                caminho = caminho_final
                            else:
                                logger.warning(
                                    f"Marcador falhou para {url}, mantendo vídeo sem marcador"
                                )

                        resultados["sucesso"].append((url, caminho))
                        logger.info(f"Download sucesso: {url}")
                    else:
                        resultados["falha"].append((url, "Todas as estratégias falharam"))
                        logger.warning(f"Download falha: {url}")

                except Exception as e:
                    resultados["falha"].append((url, str(e)))
                    logger.error(f"Erro no download de {url}: {e}")

            self.progresso.emit("Finalizando...", 100)
            self.concluido.emit(resultados)

        except Exception as e:
            logger.error(f"Erro na thread de batch: {e}")
            self.concluido.emit(resultados)

    @staticmethod
    def _aplicar_marcador(video_path: Path, marker: dict) -> Optional[Path]:
        """Queima o marcador no vídeo, substituindo o original. Retorna o novo caminho ou None."""
        editor = VideoEditor()
        out_path = video_path.parent / f"{video_path.stem}_marked.mp4"
        ok = editor.queimar_marcador(
            video_path=video_path,
            texto=marker["text"],
            output_path=out_path,
            posicao=marker.get("position", "top_right"),
        )
        if not ok or not out_path.exists():
            return None
        # Substitui o original
        try:
            video_path.unlink()
            out_path.rename(video_path)
            return video_path
        except OSError as e:
            logger.warning(f"Não foi possível substituir o original ({e}); mantendo {out_path}")
            return out_path


class MainWindow(QMainWindow):
    """Janela principal do aplicativo"""
    
    def __init__(self):
        super().__init__()
        # Thread attributes must be initialized here — sem referência forte em
        # self, o GC pode destruir o objeto Python enquanto a thread nativa ainda
        # está rodando (undefined behavior no Qt).
        self.thread_processamento: Optional[QThread] = None
        self.thread_preview: Optional[QThread] = None
        self.thread_update: Optional[QThread] = None
        self.init_ui()
        self.aplicar_tema()
        
        # Iniciar geração de previews em segundo plano
        self.iniciar_geracao_previews()
        
        # Verificar primeiro uso
        QTimer.singleShot(100, self.check_first_run)
        
        # Verificar atualizações no repositório em segundo plano (após 3 seg)
        QTimer.singleShot(3000, self.check_for_updates)
        
    def check_first_run(self):
        """Verifica se é a primeira execução e mostra tutorial"""
        if settings.first_run:
            try:
                from ui.onboarding_dialog import OnboardingDialog
                dialog = OnboardingDialog(self)
                dialog.exec()
                
                # Marcar como visto e salvar
                settings.first_run = False
                settings.save_config()
            except Exception as e:
                logger.error(f"Erro ao mostrar onboarding: {e}")

    def check_for_updates(self):
        """Verifica atualizações no repositório via thread em background"""
        try:
            self.thread_update = UpdateCheckerThread()
            self.thread_update.update_available.connect(self.on_update_available)
            self.thread_update.start()
        except Exception as e:
            logger.warning(f"Erro ao iniciar verificador de atualizacoes: {e}")

    def on_update_available(self, tag: str, download_url: str, release_notes: str):
        """Mostra janela quando atualização for encontrada (via GitHub Releases)."""
        from src import __version__

        # Trunca release notes longas para caber no diálogo
        notes_preview = (release_notes or "").strip()
        if len(notes_preview) > 600:
            notes_preview = notes_preview[:600].rstrip() + "\n…"

        msg = (
            f"🚀 Nova versão disponível: v{tag} (atual: v{__version__}).\n\n"
            "Deseja baixar e aplicar agora? O aplicativo será reiniciado automaticamente."
        )
        if notes_preview:
            msg += f"\n\nNotas da versão:\n{notes_preview}"

        resposta = QMessageBox.question(
            self,
            "Atualização Disponível",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if resposta == QMessageBox.StandardButton.Yes:
            self.aplicar_atualizacao(tag, download_url)

    def aplicar_atualizacao(self, tag: str, download_url: str):
        """Baixa o novo .exe da Release e usa um helper .bat para substituir e relançar.

        Em modo dev (rodando do código-fonte), apenas informa o usuário —
        o auto-update binário só faz sentido para o .exe distribuído.
        """
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self,
                "Modo Desenvolvimento",
                f"Update v{tag} disponível, mas você está rodando a partir do código-fonte.\n\n"
                "Use 'git pull' nesta pasta para atualizar."
            )
            return

        if sys.platform != "win32":
            QMessageBox.warning(
                self,
                "Plataforma não suportada",
                "Auto-update binário só está disponível no Windows."
            )
            return

        try:
            import requests
            import subprocess

            self.status_label.setText(f"Baixando atualização v{tag}...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            QApplication.processEvents()

            update_dir = APP_DIR / "update"
            update_dir.mkdir(parents=True, exist_ok=True)
            new_exe = update_dir / "DarkAgentLauncher_new.exe"

            # Limpa download parcial anterior, se houver
            try:
                new_exe.unlink(missing_ok=True)
            except OSError:
                pass

            with requests.get(download_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(new_exe, "wb") as f:
                    for chunk in r.iter_content(chunk_size=128 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded / total * 100)
                            self.progress_bar.setValue(pct)
                            QApplication.processEvents()

            current_exe = Path(sys.executable).resolve()
            bat_path = update_dir / "apply_update.bat"

            # Helper .bat: aguarda o processo atual liberar o arquivo (retry no move),
            # substitui o binário, relança e auto-deleta.
            bat_content = (
                "@echo off\r\n"
                "ping 127.0.0.1 -n 3 >NUL\r\n"
                ":retry\r\n"
                f'move /Y "{new_exe}" "{current_exe}"\r\n'
                "if errorlevel 1 (\r\n"
                "    ping 127.0.0.1 -n 2 >NUL\r\n"
                "    goto retry\r\n"
                ")\r\n"
                f'start "" "{current_exe}"\r\n'
                'del "%~f0"\r\n'
            )
            bat_path.write_text(bat_content, encoding="ascii")

            # DETACHED_PROCESS faz o .bat sobreviver ao fechamento do app.
            DETACHED = 0x00000008  # subprocess.DETACHED_PROCESS (Windows-only)
            subprocess.Popen(
                ["cmd", "/c", str(bat_path)],
                creationflags=DETACHED | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )

            self.status_label.setText("Reiniciando para aplicar atualização...")
            QApplication.processEvents()
            QApplication.quit()
        except Exception as e:
            logger.error(f"Erro ao aplicar atualização: {e}", exc_info=True)
            self.status_label.setText("")
            self.progress_bar.setVisible(False)
            QMessageBox.critical(
                self,
                "Erro ao Atualizar",
                f"Falha ao baixar/aplicar a atualização:\n{e}"
            )

    def show_centered_message(self, title, message, icon=QMessageBox.Icon.Information):
        """Mostra uma mensagem centralizada na janela"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        
        # Estilo para garantir visibilidade
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #1e293b;
                color: #e2e8f0;
                border-radius: 16px;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 14px;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 8px 22px;
                border-radius: 10px;
                font-weight: 600;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:pressed {
                background-color: #1d4ed8;
            }
        """)
        
        # Centralizar
        msg_box.show()
        
        # Calcular posição central
        geo = self.geometry()
        x = geo.x() + (geo.width() - msg_box.width()) // 2
        y = geo.y() + (geo.height() - msg_box.height()) // 2
        msg_box.move(x, y)
        
        msg_box.exec()
    
    def init_ui(self):
        from src import __version__
        self.setWindowTitle(f"DarkAgent Pro v{__version__}")

        # Set Icon
        icon_path = settings.assets_dir / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 8, 16, 16)

        # Header
        header_container = QWidget()
        header_container.setStyleSheet("background: transparent;")
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(0, 8, 0, 12)
        header_layout.setSpacing(4)

        titulo = QLabel(f"DarkAgent Pro")
        titulo.setObjectName("HeaderTitle")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(titulo)

        subtitulo = QLabel(f"v{__version__}")
        subtitulo.setObjectName("SubTitle")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitulo)

        layout.addWidget(header_container)
        
        # Criar TabWidget
        self.tab_widget = QTabWidget()
        # Styling is now handled by modern_theme.qss
        
        # Aba 1: Download
        tab_download = QWidget()
        layout_download = QVBoxLayout(tab_download)
        self.download_widget = DownloadWidget()
        self.download_widget.download_video_apenas.connect(self.baixar_video_apenas)
        self.download_widget.download_e_legendar.connect(self.iniciar_fluxo_completo)
        layout_download.addWidget(self.download_widget)
        self.tab_widget.addTab(tab_download, "Download")
        
        # Aba 2: Cortes Inteligentes  
        tab_clips = QWidget()
        layout_clips = QVBoxLayout(tab_clips)
        self.clip_widget = ClipWidget()
        self.clip_widget.clip_selecionado.connect(self.processar_clip)
        layout_clips.addWidget(self.clip_widget)
        self.tab_widget.addTab(tab_clips, "Cortes Inteligentes")
        
        # Aba 3: Legendas
        tab_legendas = QWidget()
        layout_legendas = QVBoxLayout(tab_legendas)
        
        # Preview Renderer
        self.preview_renderer = PreviewRenderer(canvas_size=(640, 360))
        
        # Subtitle Widget
        estilos = settings.get_todos_estilos()
        self.subtitle_widget = SubtitleWidget(estilos, self.preview_renderer)
        layout_legendas.addWidget(self.subtitle_widget)
        
        self.tab_widget.addTab(tab_legendas, "Legendas")
        
        # Aba Upload
        self.upload_widget = UploadWidget()
        self.tab_widget.addTab(self.upload_widget, "Upload")

        # Aba Editor (Overlay Editor)
        self.editor_widget = EditorWidget()
        self.tab_widget.addTab(self.editor_widget, "Editor")

        # NOTE: previews are generated asynchronously by iniciar_geracao_previews()
        # in __init__. Do NOT call gerar_previews_iniciais() here (it was synchronous
        # and duplicated the work, blocking the UI on startup).

        layout.addWidget(self.tab_widget)
        
        # Botão processar
        self.btn_processar = QPushButton("PROCESSAR COM LEGENDAS")
        self.btn_processar.setObjectName("ProcessButton")
        self.btn_processar.setMinimumHeight(54)
        self.btn_processar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_processar.clicked.connect(self.processar_video)
        layout.addWidget(self.btn_processar)
        
        # Controle de visibilidade por aba
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.btn_processar.setVisible(False)  # Download é a primeira aba
        
        # Barra de progresso
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        central_widget.setLayout(layout)

        # Tamanho mínimo e padrão — permite redimensionamento livre
        self.setMinimumSize(850, 650)
        self.resize(1300, 820)

        # Centralizar na tela
        screen = self.screen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - 1300) // 2 + screen_geometry.x()
            y = (screen_geometry.height() - 820) // 2 + screen_geometry.y()
            self.move(x, y)
    
    def aplicar_tema(self):
        """Aplica tema escuro moderno"""
        tema_path = settings.assets_dir / "styles" / "modern_theme.qss"

        if tema_path.exists():
            with open(tema_path, 'r', encoding='utf-8') as f:
                qss = f.read()
            icons_dir = (settings.assets_dir / "icons").as_posix()
            qss = qss.replace("{ICONS_DIR}", icons_dir)
            self.setStyleSheet(qss)
        else:
            logger.warning(f"Tema não encontrado em: {tema_path}")
    
    
    def on_tab_changed(self, index):
        """Atualiza visibilidade de widgets conforme a aba selecionada"""
        nome_aba = self.tab_widget.tabText(index)
        # Mostrar botão de processar apenas na aba 'Legendas'
        self.btn_processar.setVisible(nome_aba == "Legendas")
        
        # Se mudou para a aba Legendas, atualizar lista de vídeos
        if nome_aba == "Legendas":
            self.atualizar_lista_videos_para_processar()

    def atualizar_lista_videos_para_processar(self):
        """Coleta vídeos das abas Upload e Download e atualiza lista na aba Legendas"""
        items = []
        
        # 1. Arquivos locais (Upload) - Prioridade
        if hasattr(self, 'upload_widget'):
            files = self.upload_widget.get_selected_files()
            if files:
                items.extend(files)
        
        # 2. URLs (Download) - Se não houver arquivos locais (ou opcionalmente ambos)
        # Por enquanto, mantemos a lógica de 'ou um ou outro' para simplificar o UX
        # Se adicionar URLs junto com arquivos, o usuario pode se confundir
        if not items and hasattr(self, 'download_widget'):
            config_download = self.download_widget.get_configuracao()
            urls = config_download.get("urls", [])
            items.extend(urls)
            
        # Atualizar widget de legendas
        if hasattr(self, 'subtitle_widget'):
            self.subtitle_widget.update_video_list(items)

    def _is_thread_running(self) -> bool:
        """Check if any processing thread is currently running."""
        return (self.thread_processamento is not None
                and self.thread_processamento.isRunning())

    def _is_preview_thread_running(self) -> bool:
        return self.thread_preview is not None and self.thread_preview.isRunning()

    def processar_video(self):
        """Inicia processamento do vídeo (Batch Auto)"""
        if self._is_thread_running():
            self.show_centered_message(
                "Aguarde", "Já existe um processamento em andamento!",
                QMessageBox.Icon.Warning)
            return

        # Obter vídeos selecionados na aba de Legendas
        items_para_processar = self.subtitle_widget.get_selected_videos()
            
        if not items_para_processar:
            self.show_centered_message(
                "Aviso", 
                "Por favor, selecione pelo menos um vídeo na lista!", 
                QMessageBox.Icon.Warning
            )
            return
        
        estilo = self.subtitle_widget.get_estilo_atual()
        
        if not estilo:
            self.show_centered_message("Aviso", "Por favor, selecione um estilo de legenda!", QMessageBox.Icon.Warning)
            return
        
        # Configuração final
        config_download = self.download_widget.get_configuracao()
        config = {
            "urls": items_para_processar, # ProcessadorThread usa 'urls' para iterar (seja link ou arquivo)
            "qualidade": config_download.get("qualidade", "720p"), # Fallback qualidade
            "pasta": config_download.get("pasta", Path(".")) # Fallback pasta
        }
        
        # Desabilitar botão
        self.btn_processar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Iniciar thread
        self.thread_processamento = ProcessadorThread(config, estilo)
        self.thread_processamento.progresso.connect(self.atualizar_progresso)
        self.thread_processamento.concluido.connect(self.processamento_concluido)
        self.thread_processamento.start()
    
    def atualizar_progresso(self, mensagem: str, percentual: int):
        """Atualiza barra de progresso do processamento (prioridade sobre preview)."""
        self.status_label.setText(mensagem)
        self.progress_bar.setValue(percentual)
        self.progress_bar.setVisible(True)
    
    def processamento_concluido(self, resultados):
        """Callback quando processamento termina (Batch)"""
        self.btn_processar.setEnabled(True)
        
        sucessos = resultados.get("sucesso", [])
        falhas = resultados.get("falha", [])
        
        msg = f"Processamento concluído!\n\n✅ Sucesso: {len(sucessos)}\n❌ Falhas: {len(falhas)}"
        
        if falhas:
            msg += "\n\nErros:\n"
            for url, erro in falhas:
                msg += f"• {url}: {erro}\n"
        
        icon = QMessageBox.Icon.Information if not falhas else QMessageBox.Icon.Warning
        
        # Mostrar relatório se houver processamentos
        if sucessos or falhas:
            self.show_centered_message("Relatório de Processamento", msg, icon)
        
        self.status_label.setText("")
        
        # Hide only if preview thread is not running
        if not self._is_preview_thread_running():
            self.progress_bar.setVisible(False)

        self.progress_bar.setValue(0)

        # Auto-preencher aba de upload com o primeiro sucesso
        if sucessos and hasattr(self, 'upload_widget'):
            output_path = str(sucessos[0][1])
            if output_path:
                self.upload_widget.set_file(output_path)
    
    def iniciar_geracao_previews(self):
        """Inicia geração de previews em segundo plano"""
        estilos = settings.get_todos_estilos()
        
        if not estilos:
            return
        
        self.thread_preview = PreviewGeneratorThread(estilos)
        self.thread_preview.progresso.connect(self.atualizar_progresso_preview)
        self.thread_preview.concluido.connect(self.previews_concluidos)
        self.thread_preview.start()
        self.progress_bar.setVisible(True)
        
        logger.info("Iniciando geração de previews em segundo plano...")
    
    def atualizar_progresso_preview(self, atual: int, total: int, estilo_nome: str):
        """Atualiza status da geração de previews — cede o label/bar para o processamento quando ativo."""
        if total <= 0:
            return
        percentual = int((atual / total) * 100)
        logger.info(f"Gerando previews: {atual}/{total} ({percentual}%) - {estilo_nome}")

        # Processamento tem prioridade absoluta sobre status de preview.
        if self._is_thread_running():
            return

        self.status_label.setText(f"🎨 Gerando previews: {percentual}%")
        self.progress_bar.setValue(percentual)

    def previews_concluidos(self):
        """Callback quando todos os previews foram gerados"""
        logger.info("Todos os previews gerados com sucesso!")

        # Limpar status se não estiver processando
        if not self._is_thread_running():
            self.status_label.setText("✅ Previews carregados")
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)
            
            # Limpar mensagem após 3 segundos
            QTimer.singleShot(3000, lambda: self.status_label.setText(""))
        
        # Atualizar widget de legendas com os novos previews
        if hasattr(self, 'subtitle_widget'):
            self.subtitle_widget.recarregar_previews()
    
    def iniciar_fluxo_completo(self, urls, qualidade, pasta):
        """Inicia o fluxo completo: download + legenda para URLs da aba Download."""
        if self._is_thread_running():
            self.show_centered_message(
                "Aguarde", "Já existe um processamento em andamento!",
                QMessageBox.Icon.Warning)
            return

        if not urls:
            self.show_centered_message(
                "Aviso",
                "Adicione pelo menos uma URL na fila de downloads!",
                QMessageBox.Icon.Warning
            )
            return

        estilo = self.subtitle_widget.get_estilo_atual()
        if not estilo:
            self.show_centered_message(
                "Aviso",
                "Nenhum estilo de legenda selecionado.\n"
                "Vá à aba Legendas e escolha um estilo antes de continuar.",
                QMessageBox.Icon.Warning
            )
            return

        config = {
            "urls": urls,
            "qualidade": qualidade,
            "pasta": pasta,
            "markers": self.download_widget.get_markers(),
        }

        # Desabilitar botões
        self.download_widget.btn_baixar.setEnabled(False)
        self.download_widget.btn_baixar_legendar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("⚡ Iniciando fluxo completo...")

        self.thread_processamento = ProcessadorThread(config, estilo)
        self.thread_processamento.progresso.connect(self.atualizar_progresso)
        self.thread_processamento.concluido.connect(self._fluxo_completo_concluido)
        self.thread_processamento.start()

    def _fluxo_completo_concluido(self, resultados):
        """Callback quando o fluxo completo (download+legenda) termina."""
        self.download_widget.btn_baixar.setEnabled(True)
        self.download_widget.btn_baixar_legendar.setEnabled(True)

        sucessos = resultados.get("sucesso", [])
        falhas   = resultados.get("falha", [])

        msg = f"Fluxo completo concluído!\n\n✅ Com legenda: {len(sucessos)}\n❌ Falhas: {len(falhas)}"
        if falhas:
            msg += "\n\nErros:\n"
            for url, erro in falhas:
                msg += f"• {url[:60]}: {erro}\n"

        icon = QMessageBox.Icon.Information if not falhas else QMessageBox.Icon.Warning
        if sucessos or falhas:
            self.show_centered_message("Relatório — Baixar + Legendar", msg, icon)

        self.status_label.setText("")
        if not self._is_preview_thread_running():
            self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

        # Preencher aba Upload com o primeiro vídeo legendado
        if sucessos and hasattr(self, 'upload_widget'):
            self.upload_widget.set_file(str(sucessos[0][1]))

    def baixar_video_apenas(self, urls, qualidade, pasta):
        """Inicia download apenas do vídeo (Batch)"""
        if self._is_thread_running():
            self.show_centered_message(
                "Aguarde", "Já existe um processamento em andamento!",
                QMessageBox.Icon.Warning)
            return

        if not urls:
            self.show_centered_message("Aviso", "Por favor, insira pelo menos uma URL válida!", QMessageBox.Icon.Warning)
            return

        config = {
            "urls": urls,
            "qualidade": qualidade,
            "pasta": pasta,
            "markers": self.download_widget.get_markers(),
        }
        
        # Desabilitar UI
        self.download_widget.btn_baixar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Iniciar thread (Batch)
        self.thread_processamento = BatchDownloadThread(config)
        self.thread_processamento.progresso.connect(self.atualizar_progresso)
        self.thread_processamento.concluido.connect(self.download_video_concluido)
        self.thread_processamento.start()
        
    def download_video_concluido(self, resultados):
        """Callback do download de vídeo apenas (Batch)"""
        self.download_widget.btn_baixar.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("")
        
        sucessos = resultados.get("sucesso", [])
        falhas = resultados.get("falha", [])
        
        msg = f"Downloads concluídos!\n\n✅ Sucesso: {len(sucessos)}\n❌ Falhas: {len(falhas)}"
        
        if falhas:
            msg += "\n\nErros:\n"
            for url, erro in falhas:
                msg += f"• {url}: {erro}\n"
        
        icon = QMessageBox.Icon.Information if not falhas else QMessageBox.Icon.Warning
        self.show_centered_message("Relatório de Download", msg, icon)
        
        # Auto-preencher aba de upload com o primeiro sucesso (opcional)
        if sucessos and hasattr(self, 'upload_widget'):
            primeiro_arquivo = sucessos[0][1]
            self.upload_widget.set_file(str(primeiro_arquivo))
    
    def processar_clip(self, info_clip: dict):
        """Processa um clip selecionado pelo usuário"""
        try:
            from core import ClipAnalyzer
            
            video_path = info_clip.get("video_path")
            inicio = info_clip.get("inicio")
            fim = info_clip.get("fim")
            
            if not video_path or inicio is None or fim is None:
                self.show_centered_message("Aviso", "Informações do clip incompletas!", QMessageBox.Icon.Warning)
                return
            
            # Criar pasta de saída se não existir
            output_dir = settings.output_dir / "clips"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Nome do arquivo de saída
            nome_video = Path(video_path).stem
            output_path = output_dir / f"{nome_video}_clip_{inicio:.1f}-{fim:.1f}.mp4"
            
            # Criar analyzer e extrair clip
            analyzer = ClipAnalyzer(video_path)
            
            self.status_label.setText(f"Extraindo clip {inicio:.1f}s - {fim:.1f}s...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(50)
            
            sucesso = analyzer.extrair_clip(inicio, fim, str(output_path))
            
            self.progress_bar.setValue(100)
            
            if sucesso:
                self.show_centered_message(
                    "Sucesso! 🎉",
                    f"Clip extraído com sucesso!\n\nSalvo em: {output_path}",
                    QMessageBox.Icon.Information
                )
                logger.info(f"Clip extraído: {output_path}")
            else:
                self.show_centered_message(
                    "Erro ❌",
                    "Falha ao extrair o clip. Verifique os logs.",
                    QMessageBox.Icon.Critical
                )
            
            self.status_label.setText("")
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)
            
        except Exception as e:
            logger.error(f"Erro ao processar clip: {e}")
            self.show_centered_message("Erro", f"Erro ao processar clip: {str(e)}", QMessageBox.Icon.Critical)
            self.status_label.setText("")
            self.progress_bar.setVisible(False)
            self.progress_bar.setValue(0)

    def closeEvent(self, event):
        """Executado quando a janela é fechada"""
        try:
            # Limpar cache de previews
            if hasattr(self, 'preview_renderer'):
                logger.info("Limpando cache de previews ao fechar...")
                self.preview_renderer.limpar_cache()

            # Request interruption and wait (quit() has no effect on run()-based threads).
            # NÃO usamos terminate() como fallback — matar a thread no meio de um
            # subprocess.run(ffmpeg) deixa o processo filho zumbi e pode corromper o
            # arquivo de saída. Se a thread não responde à interrupção em 10s, é um bug
            # no run() (loop bloqueante sem checar isInterruptionRequested) — logamos e
            # deixamos o OS encerrar no shutdown do processo.
            threads = [
                ("preview", getattr(self, "thread_preview", None)),
                ("processamento", getattr(self, "thread_processamento", None)),
                ("update", getattr(self, "thread_update", None)),
            ]
            for name, thread in threads:
                if thread and thread.isRunning():
                    logger.info(f"Aguardando thread de {name} finalizar...")
                    thread.requestInterruption()
                    if not thread.wait(10000):
                        logger.error(
                            f"Thread de {name} não respondeu a requestInterruption em 10s — "
                            "verifique se run() está checando isInterruptionRequested()."
                        )

        except Exception as e:
            logger.error(f"Erro ao fechar aplicação: {e}")

        event.accept()
