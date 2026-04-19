import logging
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QProgressBar, QLabel, QMessageBox, QTabWidget
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


class UpdateCheckerThread(QThread):
    """Thread para verificar atualizações no repositório GitHub via git sem travar a UI"""
    
    update_available = pyqtSignal(str, str)  # hash_local, hash_remoto
    
    def run(self):
        try:
            import subprocess
            import sys

            base_dir = APP_DIR
            _sp_kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

            # Pegar branch atual
            out_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=base_dir, capture_output=True, text=True, check=True, **_sp_kw
            )
            current_branch = out_branch.stdout.strip()
            if not current_branch:
                current_branch = "main"

            # Pegar hash local
            out_local = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=base_dir, capture_output=True, text=True, check=True, **_sp_kw
            )
            hash_local = out_local.stdout.strip()

            # Pegar hash remoto da branch atual
            out_remote = subprocess.run(
                ["git", "ls-remote", "origin", current_branch],
                cwd=base_dir, capture_output=True, text=True, check=True, **_sp_kw
            )

            if not out_remote.stdout:
                return

            hash_remoto = out_remote.stdout.split()[0].strip()

            if hash_remoto and hash_local != hash_remoto:
                # Verificar se já temos esse commit localmente (estamos apenas 'ahead' e não 'behind')
                check_local = subprocess.run(
                    ["git", "cat-file", "-e", hash_remoto],
                    cwd=base_dir, capture_output=True, **_sp_kw
                )
                
                # returncode != 0 significa que não temos esse commit no repo local -> é uma atualização real
                if check_local.returncode != 0:
                    self.update_available.emit(hash_local, hash_remoto)
                
        except Exception as e:
            logger.debug(f"Aviso - Não foi possível conferir atualizações via Git: {e}")


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
                        idioma=settings.whisper_language  # None = auto-detect
                    )
                    audio_path = caminho_video.parent / f"audio_temp_{i}.wav"
                    
                    if not transcriber.extrair_audio_de_video(caminho_video, audio_path):
                        resultados["falha"].append((url, "Falha ao extrair áudio"))
                        continue
                    
                    # Transcrever
                    report_progress("Transcrevendo com IA...", 50)
                    transcricao = transcriber.transcrever(audio_path)
                    
                    # Gerar legendas
                    report_progress("Gerando legendas...", 70)
                    subtitle_gen = SubtitleGenerator()
                    ass_path = caminho_video.parent / f"{caminho_video.stem}.ass"
                    
                    subtitle_gen.gerar_ass(transcricao, self.estilo, ass_path)
                    
                    # Queimar legendas
                    report_progress("Renderizando vídeo final...", 85)
                    editor = VideoEditor()
                    output_path = caminho_video.parent / f"{caminho_video.stem}_final.mp4"
                    
                    if not editor.queimar_legendas(caminho_video, ass_path, output_path):
                        resultados["falha"].append((url, "Falha ao renderizar"))
                        continue
                    
                    # Limpar temporários
                    audio_path.unlink(missing_ok=True)
                    
                    resultados["sucesso"].append((url, output_path))
                    report_progress("Concluído!", 100)
                    
                except Exception as e:
                    logger.error(f"Erro ao processar {url}: {e}")
                    resultados["falha"].append((url, str(e)))
            
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


class MainWindow(QMainWindow):
    """Janela principal do aplicativo"""
    
    def __init__(self):
        super().__init__()
        self.thread_processamento = None
        self.thread_preview = None
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

    def on_update_available(self, local_hash, remote_hash):
        """Mostra janela quando atualização for encontrada"""
        msg = (
            "🚀 Uma nova atualização está disponível no repositório GitHub!\n\n"
            "Deseja baixar e aplicar a atualização agora usando git pull?"
        )
        resposta = QMessageBox.question(
            self,
            "Atualização Disponível",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if resposta == QMessageBox.StandardButton.Yes:
            self.aplicar_atualizacao()

    def aplicar_atualizacao(self):
        """Usa git pull para atualizar o repositório"""
        try:
            import subprocess
            import sys

            base_dir = APP_DIR
            self.status_label.setText("Baixando atualização do repositório...")
            self.repaint() # Força a interface a atualizar o label

            _sp_kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

            proc = subprocess.run(
                ["git", "pull"],
                cwd=base_dir, capture_output=True, text=True, **_sp_kw
            )
            
            if proc.returncode == 0:
                QMessageBox.information(
                    self, 
                    "Sucesso ✨", 
                    "A atualização foi baixada e aplicada com sucesso!\n\n"
                    "Por favor, feche e abra o aplicativo novamente para carregar as modificações."
                )
            else:
                QMessageBox.warning(
                    self, 
                    "Erro ao Atualizar", 
                    f"Ocorreu um erro ao tentar executar o git pull:\n{proc.stderr}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Erro ❌", f"Erro fatal ao tentar atualizar: {e}")
        finally:
            self.status_label.setText("")

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
        """Atualiza barra de progresso"""
        self.status_label.setText(mensagem)
        self.progress_bar.setValue(percentual)
    
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
        if not hasattr(self, 'thread_preview') or not self.thread_preview or not self.thread_preview.isRunning():
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
        """Atualiza status da geração de previews"""
        percentual = int((atual / total) * 100)
        logger.info(f"Gerando previews: {atual}/{total} ({percentual}%) - {estilo_nome}")
        
        # Opcional: mostrar no status label se não estiver processando vídeo
        if not hasattr(self, 'thread_processamento') or not self.thread_processamento or not self.thread_processamento.isRunning():
            self.status_label.setText(f"🎨 Gerando previews: {percentual}%")
            self.progress_bar.setValue(percentual)
    
    def previews_concluidos(self):
        """Callback quando todos os previews foram gerados"""
        logger.info("Todos os previews gerados com sucesso!")
        
        # Limpar status se não estiver processando
        if not hasattr(self, 'thread_processamento') or not self.thread_processamento or not self.thread_processamento.isRunning():
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
        if not (hasattr(self, 'thread_preview') and self.thread_preview and self.thread_preview.isRunning()):
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
            "pasta": pasta
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

            # Request interruption and wait (quit() has no effect on run()-based threads)
            for name, thread in [("preview", self.thread_preview), ("processamento", self.thread_processamento)]:
                if thread and thread.isRunning():
                    logger.info(f"Aguardando thread de {name} finalizar...")
                    thread.requestInterruption()
                    if not thread.wait(5000):
                        logger.warning(f"Thread de {name} não finalizou a tempo, forçando...")
                        thread.terminate()
                        thread.wait(1000)

        except Exception as e:
            logger.error(f"Erro ao fechar aplicação: {e}")

        event.accept()
