import logging
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QProgressBar, QLabel, QMessageBox, QTabWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon

try:
    from config.settings import settings
    from ui.widgets import DownloadWidget, SubtitleWidget, ClipWidget, SocialWidget, UploadWidget
    from core import (
        VideoDownloader, VideoValidator, Transcriber,
        SubtitleGenerator, VideoEditor, PreviewRenderer
    )
except ImportError:
    from ..config.settings import settings
    from .widgets import DownloadWidget, SubtitleWidget, ClipWidget, SocialWidget, UploadWidget
    from ..core import (
        VideoDownloader, VideoValidator, Transcriber,
        SubtitleGenerator, VideoEditor, PreviewRenderer
    )

logger = logging.getLogger(__name__)


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
    concluido = pyqtSignal(bool, str)  # sucesso, mensagem
    
    def __init__(self, config, estilo):
        super().__init__()
        self.config = config
        self.estilo = estilo
    
    def run(self):
        try:
            # Download
            self.progresso.emit("Baixando vídeo...", 10)
            downloader = VideoDownloader(self.config["pasta"])
            sucesso, caminho_video, estrategia = downloader.download(
                self.config["url"],
                self.config["qualidade"]
            )
            
            if not sucesso:
                self.concluido.emit(False, "Falha no download")
                return
            
            # Validar
            self.progresso.emit("Validando vídeo...", 20)
            valido, checks = VideoValidator.validar_video_completo(caminho_video)
            
            if not valido:
                self.concluido.emit(False, f"Vídeo inválido: {checks}")
                return
            
            # Extrair áudio
            self.progresso.emit("Extraindo áudio...", 30)
            transcriber = Transcriber(
                modelo=settings.whisper_model,
                idioma=settings.whisper_language  # None = auto-detect
            )
            audio_path = caminho_video.parent / "audio_temp.wav"
            
            if not transcriber.extrair_audio_de_video(caminho_video, audio_path):
                self.concluido.emit(False, "Falha ao extrair áudio")
                return
            
            # Transcrever
            self.progresso.emit("Transcrevendo com IA...", 50)
            transcricao = transcriber.transcrever(audio_path)
            
            # Gerar legendas
            self.progresso.emit("Gerando legendas...", 70)
            subtitle_gen = SubtitleGenerator()
            ass_path = caminho_video.parent / "legendas.ass"
            
            subtitle_gen.gerar_ass(transcricao, self.estilo, ass_path)
            
            # Queimar legendas
            self.progresso.emit("Queimando legendas no vídeo...", 85)
            editor = VideoEditor()
            output_path = caminho_video.parent / f"{caminho_video.stem}_final.mp4"
            
            if not editor.queimar_legendas(caminho_video, ass_path, output_path):
                self.concluido.emit(False, "Falha ao queimar legendas")
                return
            
            # Limpar temporários
            audio_path.unlink(missing_ok=True)
            
            self.progresso.emit("Concluído!", 100)
            self.concluido.emit(True, f"Vídeo salvo em: {output_path}")
            
        except Exception as e:
            logger.error(f"Erro no processamento: {e}")
            self.concluido.emit(False, f"Erro: {str(e)}")


class VideoOnlyThread(QThread):
    """Thread apenas para download de vídeo"""
    progresso = pyqtSignal(str, int)  # mensagem, percentual
    concluido = pyqtSignal(bool, str)  # sucesso, mensagem
    
    def __init__(self, config):
        super().__init__()
        self.config = config
    
    def run(self):
        try:
            self.progresso.emit("Baixando vídeo...", 10)
            downloader = VideoDownloader(self.config["pasta"])
            sucesso, caminho, estrategia = downloader.download(
                self.config["url"],
                self.config["qualidade"]
            )
            
            if sucesso:
                self.progresso.emit("Concluído!", 100)
                self.concluido.emit(True, f"Vídeo salvo em: {caminho}")
            else:
                self.concluido.emit(False, "Falha no download.")
                
        except Exception as e:
            logger.error(f"Erro no download (video only): {e}")
            self.concluido.emit(False, f"Erro: {str(e)}")


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
                color: white;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2563eb;
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
        self.setWindowTitle("DarkAgent Pro v2.0")
        self.resize(1200, 800) # Tamanho base razoável
        self.center_window()   # Centralizar na tela
        
        # Set Icon
        icon_path = settings.assets_dir / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # Header
        header_container = QWidget()
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(0, 10, 0, 20)
        
        titulo = QLabel("DarkAgent Pro v2.0")
        titulo.setObjectName("HeaderTitle") # For QSS styling
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(titulo)
        
        layout.addWidget(header_container)
        
        # Criar TabWidget
        self.tab_widget = QTabWidget()
        # Styling is now handled by modern_theme.qss
        
        # Aba 1: Download
        tab_download = QWidget()
        layout_download = QVBoxLayout(tab_download)
        self.download_widget = DownloadWidget()
        self.download_widget.download_video_apenas.connect(self.baixar_video_apenas)
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
        
        # Aba Social (Nova)
        self.social_widget = SocialWidget()
        self.tab_widget.addTab(self.social_widget, "Social")

        # Aba Upload
        self.upload_widget = UploadWidget()
        self.tab_widget.addTab(self.upload_widget, "Upload")
        
        # Gerar previews automaticamente ao iniciar
        self.gerar_previews_iniciais()
        
        layout.addWidget(self.tab_widget)
        
        # Botão processar
        self.btn_processar = QPushButton("🎬 PROCESSAR COM LEGENDAS")
        self.btn_processar.setMinimumHeight(50)
        self.btn_processar.setStyleSheet("font-size: 16px;")
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
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        central_widget.setLayout(layout)

    def center_window(self):
        """Centraliza a janela na tela"""
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())
    
    def gerar_previews_iniciais(self):
        """Gera previews dos estilos ao iniciar o aplicativo"""
        logger.info("Gerando previews iniciais dos estilos...")
        
        estilos = settings.get_todos_estilos()
        for estilo in estilos:
            try:
                self.preview_renderer.gerar_previews_todos_tamanhos(estilo)
                logger.info(f"Previews gerados para estilo: {estilo.id}")
            except Exception as e:
                logger.error(f"Erro ao gerar preview para {estilo.id}: {e}")
    
    def aplicar_tema(self):
        """Aplica tema escuro moderno"""
        tema_path = settings.assets_dir / "styles" / "modern_theme.qss"
        
        if tema_path.exists():
            with open(tema_path, 'r', encoding='utf-8') as f:
                self.setStyleSheet(f.read())
        else:
            logger.warning(f"Tema não encontrado em: {tema_path}")
    
    
    def on_tab_changed(self, index):
        """Atualiza visibilidade de widgets conforme a aba selecionada"""
        nome_aba = self.tab_widget.tabText(index)
        # Mostrar botão de processar apenas na aba 'Legendas'
        self.btn_processar.setVisible(nome_aba == "Legendas")

    def processar_video(self):
        """Inicia processamento do vídeo"""
        # Validar configuração
        config = self.download_widget.get_configuracao()
        
        if not config["url"]:
            self.show_centered_message("Aviso", "Por favor, insira uma URL do YouTube!", QMessageBox.Icon.Warning)
            return
        
        estilo = self.subtitle_widget.get_estilo_atual()
        
        if not estilo:
            self.show_centered_message("Aviso", "Por favor, selecione um estilo de legenda!", QMessageBox.Icon.Warning)
            return
        
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
    
    def processamento_concluido(self, sucesso: bool, mensagem: str):
        """Callback quando processamento termina"""
        self.btn_processar.setEnabled(True)
        
        if sucesso:
            self.show_centered_message("Sucesso! 🎉", mensagem, QMessageBox.Icon.Information)
        else:
            self.show_centered_message("Erro ❌", mensagem, QMessageBox.Icon.Critical)
        
        self.status_label.setText("")
        
        # Hide only if preview thread is not running
        if not hasattr(self, 'thread_preview') or not self.thread_preview or not self.thread_preview.isRunning():
            self.progress_bar.setVisible(False)
            
        self.progress_bar.setValue(0)
    
        # Auto-preencher aba de upload
        if sucesso and hasattr(self, 'upload_widget'):
            output_path = mensagem.split(": ")[1] if ": " in mensagem else ""
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
    
    def baixar_video_apenas(self, url, qualidade, pasta):
        """Inicia download apenas do vídeo"""
        if not url:
            self.show_centered_message("Aviso", "Por favor, insira uma URL do YouTube!", QMessageBox.Icon.Warning)
            return
            
        config = {
            "url": url,
            "qualidade": qualidade,
            "pasta": pasta
        }
        
        # Desabilitar UI
        self.download_widget.btn_baixar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Iniciar thread
        self.thread_processamento = VideoOnlyThread(config)
        self.thread_processamento.progresso.connect(self.atualizar_progresso)
        self.thread_processamento.concluido.connect(self.download_video_concluido)
        self.thread_processamento.start()
        
    def download_video_concluido(self, sucesso, mensagem):
        """Callback do download de vídeo apenas"""
        self.download_widget.btn_baixar.setEnabled(True)
        self.processamento_concluido(sucesso, mensagem)
    
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
            
            # Parar threads se estiverem rodando
            if self.thread_preview and self.thread_preview.isRunning():
                self.thread_preview.terminate()
                self.thread_preview.wait()
                
            if self.thread_processamento and self.thread_processamento.isRunning():
                # Opcional: confirmar saída se estiver processando
                pass
                
        except Exception as e:
            logger.error(f"Erro ao fechar aplicação: {e}")
        
        event.accept()
