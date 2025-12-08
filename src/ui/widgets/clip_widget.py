"""Widget de cortes inteligentes com análise de viralização"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QScrollArea, QGroupBox, QSlider, QSpinBox,
    QProgressBar, QListWidget, QListWidgetItem, QFrame,
    QComboBox, QFileDialog, QMessageBox, QCheckBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QColor, QPalette
from pathlib import Path
import logging

try:
    from config import settings
except ImportError:
    from ...config import settings

logger = logging.getLogger(__name__)


class ClipAnalyzerThread(QThread):
    """Thread para análise inteligente de clipes"""
    
    progresso = pyqtSignal(int)  # percentual
    clip_encontrado = pyqtSignal(dict)  # {inicio, fim, score, razao}
    concluido = pyqtSignal(list)  # lista de clipes
    
    def __init__(self, video_path, duracao_min=15, duracao_max=60, max_clips=10):
        super().__init__()
        self.video_path = video_path
        self.duracao_min = duracao_min
        self.duracao_max = duracao_max
        self.max_clips = max_clips
    
    def run(self):
        try:
            from core.clip_analyzer import ClipAnalyzer
            
            analyzer = ClipAnalyzer(self.video_path)
            clips = []
            
            # Analisar vídeo em janelas deslizantes
            total_steps = 10
            for i, clip in enumerate(analyzer.analisar_clips(
                duracao_min=self.duracao_min,
                duracao_max=self.duracao_max,
                max_clips=self.max_clips
            )):
                clips.append(clip)
                self.clip_encontrado.emit(clip)
                self.progresso.emit(int((i + 1) / total_steps * 100))
            
            # Ordenar por score
            clips.sort(key=lambda x: x['score'], reverse=True)
            
            self.concluido.emit(clips)
            
        except Exception as e:
            logger.error(f"Erro na análise de clips: {e}")
            self.concluido.emit([])


class ClipItemWidget(QFrame):
    """Widget individual para cada clip sugerido"""
    
    selecionado = pyqtSignal(dict)
    
    def __init__(self, clip_data, parent=None):
        super().__init__(parent)
        self.clip_data = clip_data
        self.setup_ui()
    
    def setup_ui(self):
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("ClipItem")
        self.setStyleSheet("""
            QFrame#ClipItem {
                background-color: rgba(30, 41, 59, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                margin-bottom: 8px;
            }
            QFrame#ClipItem:hover {
                background-color: rgba(59, 130, 246, 0.1);
                border: 1px solid #3b82f6;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header com score
        header = QHBoxLayout()
        
        # Título com tempo
        inicio_str = self._format_time(self.clip_data['inicio'])
        fim_str = self._format_time(self.clip_data['fim'])
        duracao = self.clip_data['fim'] - self.clip_data['inicio']
        
        titulo = QLabel(f"📹 {inicio_str} → {fim_str} ({int(duracao)}s)")
        titulo.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        header.addWidget(titulo)
        
        header.addStretch()
        
        # Score com cor
        score = self.clip_data['score']
        score_label = QLabel(f"🔥 {int(score * 100)}%")
        score_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {self._get_score_color(score)};")
        header.addWidget(score_label)
        
        layout.addLayout(header)
        
        # Barra de viralização
        viral_bar = QProgressBar()
        viral_bar.setMaximum(100)
        viral_bar.setValue(int(score * 100))
        viral_bar.setTextVisible(True)
        viral_bar.setFormat("Potencial Viral: %p%")
        viral_bar.setStyleSheet(self._get_progressbar_style(score))
        layout.addWidget(viral_bar)
        
        # Razões da pontuação
        razoes_text = "\n".join([f"• {r}" for r in self.clip_data.get('razoes', [])])
        razoes_label = QLabel(razoes_text)
        razoes_label.setWordWrap(True)
        razoes_label.setStyleSheet("color: #94a3b8; font-size: 12px; margin: 5px;")
        layout.addWidget(razoes_label)
        
        # Botão de selecionar
        btn_selecionar = QPushButton("✂️ Selecionar este Clip")
        btn_selecionar.clicked.connect(lambda: self.selecionado.emit(self.clip_data))
        # Style handled by QSS (QPushButton)
        layout.addWidget(btn_selecionar)
        
        self.setLayout(layout)
    
    def _format_time(self, seconds):
        """Formata segundos para MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"
    
    def _get_score_color(self, score):
        """Retorna cor baseada no score"""
        if score >= 0.8:
            return "#00ff00"  # Verde forte
        elif score >= 0.6:
            return "#ffcc00"  # Amarelo
        elif score >= 0.4:
            return "#ff9900"  # Laranja
        else:
            return "#ff3300"  # Vermelho
    
    def _get_progressbar_style(self, score):
        """Retorna estilo da barra baseado no score"""
        color = self._get_score_color(score)
        return f"""
            QProgressBar {{
                border: 2px solid #333;
                border-radius: 5px;
                text-align: center;
                background-color: #1a1a1a;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """


class ClipWidget(QWidget):
    """Widget principal de cortes inteligentes"""
    
    clip_selecionado = pyqtSignal(dict)  # Emite quando um clip é selecionado
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path = None
        self.clips_sugeridos = []
        self.thread_analyzer = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        # --- Container Superior: Seleção e Configuração ---
        top_container = QFrame()
        top_container.setObjectName("GlassContainer")
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(20, 20, 20, 20)
        top_layout.setSpacing(15)
        
        # Título da Seção
        title_layout = QHBoxLayout()
        icon_label = QLabel("✂️")
        icon_label.setStyleSheet("font-size: 24px;")
        title_label = QLabel("Cortes Inteligentes com IA")
        title_label.setObjectName("HeaderTitle")
        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        top_layout.addLayout(title_layout)
        
        # Seleção de Vídeo
        video_layout = QVBoxLayout()
        video_label = QLabel("Seleção de Vídeo")
        video_label.setObjectName("SectionTitle")
        video_layout.addWidget(video_label)
        
        video_controls = QHBoxLayout()
        self.combo_video = QComboBox()
        self.combo_video.setMinimumHeight(45)
        self.combo_video.currentTextChanged.connect(self.on_video_selecionado)
        video_controls.addWidget(self.combo_video, 1)
        
        self.btn_refresh = QPushButton()
        self.btn_refresh.setFixedSize(45, 45)
        self.btn_refresh.setToolTip("Recarregar vídeos")
        
        # Set refresh icon
        refresh_icon_path = settings.assets_dir / "refresh.svg"
        if refresh_icon_path.exists():
            self.btn_refresh.setIcon(QIcon(str(refresh_icon_path)))
            self.btn_refresh.setIconSize(self.btn_refresh.size() * 0.6)
        else:
            self.btn_refresh.setText("🔄")
            
        self.btn_refresh.clicked.connect(self.carregar_videos)
        video_controls.addWidget(self.btn_refresh)
        
        self.btn_procurar = QPushButton("📁 Procurar...")
        self.btn_procurar.setMinimumHeight(45)
        self.btn_procurar.clicked.connect(self.procurar_arquivo)
        video_controls.addWidget(self.btn_procurar)
        
        video_layout.addLayout(video_controls)
        
        self.info_video = QLabel("Nenhum vídeo selecionado")
        self.info_video.setStyleSheet("color: #94a3b8; font-style: italic;")
        video_layout.addWidget(self.info_video)
        
        top_layout.addLayout(video_layout)
        
        # Configurações
        config_layout = QVBoxLayout()
        config_label = QLabel("Configurações")
        config_label.setObjectName("SectionTitle")
        config_layout.addWidget(config_label)
        
        params_layout = QHBoxLayout()
        
        # Duração Mínima
        min_layout = QHBoxLayout()
        min_layout.addWidget(QLabel("Duração Mínima (s):"))
        self.duracao_min_spin = QSpinBox()
        self.duracao_min_spin.setMinimum(10)
        self.duracao_min_spin.setMaximum(120)
        self.duracao_min_spin.setValue(15)
        self.duracao_min_spin.setMinimumHeight(40)
        min_layout.addWidget(self.duracao_min_spin)
        params_layout.addLayout(min_layout)
        
        params_layout.addSpacing(20)
        
        # Duração Máxima
        max_layout = QHBoxLayout()
        max_layout.addWidget(QLabel("Duração Máxima (s):"))
        self.duracao_max_spin = QSpinBox()
        self.duracao_max_spin.setMinimum(15)
        self.duracao_max_spin.setMaximum(180)
        self.duracao_max_spin.setValue(60)
        self.duracao_max_spin.setMinimumHeight(40)
        max_layout.addWidget(self.duracao_max_spin)
        params_layout.addLayout(max_layout)
        
        params_layout.addLayout(max_layout)
        
        params_layout.addSpacing(20)

        # Quantidade de Clips
        qtd_layout = QHBoxLayout()
        qtd_layout.addWidget(QLabel("Qtd. Clips:"))
        self.qtd_clips_spin = QSpinBox()
        self.qtd_clips_spin.setMinimum(1)
        self.qtd_clips_spin.setMaximum(50)
        self.qtd_clips_spin.setValue(10)
        self.qtd_clips_spin.setMinimumHeight(40)
        qtd_layout.addWidget(self.qtd_clips_spin)
        params_layout.addLayout(qtd_layout)
        
        params_layout.addLayout(qtd_layout)
        
        # Checkbox "Todas as possibilidades"
        self.check_todos = QCheckBox("Gerar todas as possibilidades")
        self.check_todos.setToolTip("Gera todos os clips possíveis e ordena por pontuação")
        self.check_todos.setChecked(True)
        self.check_todos.toggled.connect(self.on_check_todos_toggled)
        
        # Estilo personalizado para fundo transparente e checkmark
        # Usando forward slashes explicitamente e as_posix()
        check_icon_path = (settings.assets_dir / "check.svg").as_posix()
        
        self.check_todos.setStyleSheet(f"""
            QCheckBox {{
                background-color: transparent;
                color: #e2e8f0;
                font-size: 14px;
                font-weight: bold;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 22px;
                height: 22px;
                border: 2px solid #475569;
                border-radius: 6px;
                background: rgba(30, 41, 59, 0.5);
            }}
            QCheckBox::indicator:hover {{
                border-color: #3b82f6;
            }}
            QCheckBox::indicator:checked {{
                background-color: #3b82f6;
                border-color: #3b82f6;
                image: url("{check_icon_path}");
            }}
        """)
        
        params_layout.addWidget(self.check_todos)
        
        # Trigger initial state
        self.on_check_todos_toggled(True)
        
        params_layout.addStretch()
        config_layout.addLayout(params_layout)
        
        top_layout.addLayout(config_layout)
        
        # Botão Analisar
        self.btn_analisar = QPushButton("🔍 Analisar Vídeo")
        self.btn_analisar.setMinimumHeight(50)
        self.btn_analisar.clicked.connect(self.analisar_video)
        self.btn_analisar.setEnabled(False)
        top_layout.addWidget(self.btn_analisar)
        
        layout.addWidget(top_container, 0) # Don't expand top container
        
        # --- Container Inferior: Resultados ---
        results_container = QFrame()
        results_container.setObjectName("GlassContainer")
        results_layout = QVBoxLayout(results_container)
        results_layout.setContentsMargins(20, 20, 20, 20)
        
        results_header = QHBoxLayout()
        results_title = QLabel("Clips Sugeridos")
        results_title.setObjectName("SectionTitle")
        results_header.addWidget(results_title)
        results_header.addStretch()
        
        self.btn_baixar_todos = QPushButton("⬇️ Baixar Todos")
        self.btn_baixar_todos.clicked.connect(self.baixar_todos_clips)
        self.btn_baixar_todos.setEnabled(False)
        results_header.addWidget(self.btn_baixar_todos)
        
        results_layout.addLayout(results_header)
        
        # Scroll Area para Clips
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        
        self.clips_container = QWidget()
        self.clips_container.setStyleSheet("background: transparent;")
        self.clips_container_layout = QVBoxLayout()
        self.clips_container_layout.setSpacing(10)
        self.clips_container_layout.addStretch()
        self.clips_container.setLayout(self.clips_container_layout)
        
        self.scroll_area.setWidget(self.clips_container)
        results_layout.addWidget(self.scroll_area)
        
        layout.addWidget(results_container, 1) # Expand results container
        
        # Barra de Progresso e Status
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
    
    def on_check_todos_toggled(self, checked):
        """Habilita/desabilita spinbox de quantidade"""
        self.qtd_clips_spin.setEnabled(not checked)
        if checked:
            self.qtd_clips_spin.setSpecialValueText("Todos")
        else:
            self.qtd_clips_spin.setSpecialValueText("")

    def analisar_video(self):
        """Inicia análise inteligente do vídeo"""
        if not self.video_path or not self.video_path.exists():
            QMessageBox.warning(
                self, 
                "Vídeo não encontrado",
                "Por favor, selecione um vídeo válido para análise."
            )
            return
        
        # Validar configurações
        duracao_min = self.duracao_min_spin.value()
        duracao_max = self.duracao_max_spin.value()
        
        if duracao_min >= duracao_max:
            QMessageBox.warning(
                self,
                "Configuração inválida",
                "A duração mínima deve ser menor que a duração máxima."
            )
            return
        
        # Confirmar análise
        resposta = QMessageBox.question(
            self,
            "Confirmar Análise",
            f"Analisar vídeo: {self.video_path.name}?\n\n"
            f"Duração: {duracao_min}s - {duracao_max}s\n"
            f"Isso pode levar alguns minutos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if resposta != QMessageBox.StandardButton.Yes:
            return
        
        # Limpar clips anteriores
        self.limpar_clips()
        
        # Configurar UI
        self.btn_analisar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"🔍 Analisando {self.video_path.name}...")
        
        logger.info(f"Iniciando análise: {self.video_path} ({duracao_min}s-{duracao_max}s)")
        
        # Determinar max_clips
        max_clips = 0 if self.check_todos.isChecked() else self.qtd_clips_spin.value()
        
        # Iniciar thread de análise
        self.thread_analyzer = ClipAnalyzerThread(
            self.video_path,
            duracao_min=duracao_min,
            duracao_max=duracao_max,
            max_clips=max_clips
        )
        self.thread_analyzer.progresso.connect(self.atualizar_progresso)
        self.thread_analyzer.clip_encontrado.connect(self.adicionar_clip)
        self.thread_analyzer.concluido.connect(self.analise_concluida)
        self.thread_analyzer.start()
    
    def atualizar_progresso(self, percentual):
        """Atualiza barra de progresso"""
        self.progress_bar.setValue(percentual)
    
    def adicionar_clip(self, clip_data):
        """Adiciona um clip à lista"""
        clip_widget = ClipItemWidget(clip_data)
        clip_widget.selecionado.connect(self.on_clip_selecionado)
        
        # Inserir no início (antes do stretch)
        self.clips_container_layout.insertWidget(
            self.clips_container_layout.count() - 1,
            clip_widget
        )
        
        self.clips_sugeridos.append(clip_data)
    
    def analise_concluida(self, clips):
        """Callback quando análise termina"""
        self.btn_analisar.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if clips:
            self.status_label.setText(f"✅ {len(clips)} clips encontrados!")
            self.btn_baixar_todos.setEnabled(True)
        else:
            self.status_label.setText("⚠️ Nenhum clip sugerido")
            self.btn_baixar_todos.setEnabled(False)
        
        logger.info(f"Análise concluída: {len(clips)} clips encontrados")
    
    def on_clip_selecionado(self, clip_data):
        """Callback quando um clip é selecionado"""
        # Adicionar informações do vídeo ao clip_data
        clip_info = clip_data.copy()
        clip_info['video_path'] = str(self.video_path) if self.video_path else None
        
        self.clip_selecionado.emit(clip_info)
        logger.info(f"Clip selecionado: {clip_data['inicio']}-{clip_data['fim']} (score: {clip_data['score']})")
    
    def limpar_clips(self):
        """Remove todos os clips da lista"""
        # Remover todos os widgets exceto o stretch
        while self.clips_container_layout.count() > 1:
            item = self.clips_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.clips_sugeridos.clear()
        self.btn_baixar_todos.setEnabled(False)
    
    def baixar_todos_clips(self):
        """Baixa todos os clips sugeridos em lote"""
        if not self.clips_sugeridos:
            QMessageBox.warning(
                self,
                "Sem clips",
                "Nenhum clip disponível para download."
            )
            return
        
        # Confirmar download
        resposta = QMessageBox.question(
            self,
            "Confirmar Download",
            f"Deseja baixar todos os {len(self.clips_sugeridos)} clips?\n\n"
            f"Vídeo: {self.video_path.name}\n"
            f"Isso pode levar alguns minutos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if resposta != QMessageBox.StandardButton.Yes:
            return
        
        # Desabilitar botão durante processamento
        self.btn_baixar_todos.setEnabled(False)
        self.btn_analisar.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        try:
            from core.clip_analyzer import ClipAnalyzer
            from pathlib import Path as PathLib
            
            # Criar pasta de saída
            output_dir = PathLib("output/clips")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            analyzer = ClipAnalyzer(self.video_path)
            total_clips = len(self.clips_sugeridos)
            clips_baixados = 0
            
            for i, clip_data in enumerate(self.clips_sugeridos):
                inicio = clip_data['inicio']
                fim = clip_data['fim']
                score = clip_data['score']
                
                # Nome do arquivo com score
                nome_video = self.video_path.stem
                output_path = output_dir / f"{nome_video}_clip_{i+1:02d}_score{int(score*100)}.mp4"
                
                self.status_label.setText(f"⬇️ Baixando clip {i+1}/{total_clips}...")
                
                sucesso = analyzer.extrair_clip(inicio, fim, str(output_path))
                
                if sucesso:
                    clips_baixados += 1
                    logger.info(f"Clip {i+1}/{total_clips} baixado: {output_path}")
                else:
                    logger.warning(f"Falha ao baixar clip {i+1}/{total_clips}")
                
                # Atualizar progresso
                self.progress_bar.setValue(int((i + 1) / total_clips * 100))
            
            # Finalizar
            self.progress_bar.setVisible(False)
            self.btn_baixar_todos.setEnabled(True)
            self.btn_analisar.setEnabled(True)
            
            if clips_baixados == total_clips:
                QMessageBox.information(
                    self,
                    "Sucesso! 🎉",
                    f"Todos os {clips_baixados} clips foram baixados com sucesso!\n\n"
                    f"Salvos em: {output_dir}"
                )
                self.status_label.setText(f"✅ {clips_baixados} clips baixados!")
            else:
                QMessageBox.warning(
                    self,
                    "Download Parcial ⚠️",
                    f"{clips_baixados} de {total_clips} clips foram baixados.\n\n"
                    f"Verifique os logs para mais detalhes."
                )
                self.status_label.setText(f"⚠️ {clips_baixados}/{total_clips} clips baixados")
            
            logger.info(f"Download em lote concluído: {clips_baixados}/{total_clips}")
            
        except Exception as e:
            logger.error(f"Erro ao baixar clips em lote: {e}")
            QMessageBox.critical(
                self,
                "Erro ❌",
                f"Erro ao baixar clips:\n{str(e)}"
            )
            self.progress_bar.setVisible(False)
            self.btn_baixar_todos.setEnabled(True)
            self.btn_analisar.setEnabled(True)
    
    def get_clips_sugeridos(self):
        """Retorna lista de clips sugeridos"""
        return self.clips_sugeridos
    
    def carregar_videos(self):
        """Carrega lista de vídeos das pastas de download"""
        self.combo_video.clear()
        self.combo_video.addItem("Selecione um vídeo...")
        
        try:
            # Procurar vídeos em possíveis pastas de download
            pastas_busca = [
                Path.home() / "Downloads",
                Path.cwd() / "downloads",
                Path.cwd() / "output",
                Path.cwd(),
            ]
            
            extensoes_video = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
            videos_encontrados = []
            
            for pasta in pastas_busca:
                if pasta.exists():
                    for arquivo in pasta.iterdir():
                        if arquivo.is_file() and arquivo.suffix.lower() in extensoes_video:
                            videos_encontrados.append(arquivo)
            
            # Remover duplicatas e ordenar
            videos_unicos = list(set(videos_encontrados))
            videos_unicos.sort(key=lambda x: x.name)
            
            for video in videos_unicos:
                # Mostrar nome e tamanho
                tamanho_mb = video.stat().st_size / (1024 * 1024)
                display_name = f"{video.name} ({tamanho_mb:.1f} MB)"
                self.combo_video.addItem(display_name, userData=str(video))
            
            if videos_unicos:
                logger.info(f"Encontrados {len(videos_unicos)} vídeos")
            else:
                self.combo_video.addItem("Nenhum vídeo encontrado")
                
        except Exception as e:
            logger.error(f"Erro ao carregar vídeos: {e}")
            self.combo_video.addItem("Erro ao carregar vídeos")
    
    def procurar_arquivo(self):
        """Abre diálogo para selecionar arquivo específico"""
        arquivo, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Vídeo",
            str(Path.home()),
            "Vídeos (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v);;Todos os arquivos (*)"
        )
        
        if arquivo:
            video_path = Path(arquivo)
            tamanho_mb = video_path.stat().st_size / (1024 * 1024)
            display_name = f"{video_path.name} ({tamanho_mb:.1f} MB) [Selecionado]"
            
            # Adicionar no combo e selecionar
            self.combo_video.addItem(display_name, userData=str(video_path))
            self.combo_video.setCurrentIndex(self.combo_video.count() - 1)
    
    def on_video_selecionado(self, texto):
        """Callback quando vídeo é selecionado no combo"""
        if self.combo_video.currentData():
            self.video_path = Path(self.combo_video.currentData())
            
            # Mostrar informações do vídeo
            try:
                tamanho_mb = self.video_path.stat().st_size / (1024 * 1024)
                self.info_video.setText(
                    f"📹 {self.video_path.name}\n"
                    f"📁 {self.video_path.parent}\n"
                    f"💾 {tamanho_mb:.1f} MB"
                )
                self.info_video.setStyleSheet("color: #4CAF50; margin: 5px;")
                self.btn_analisar.setEnabled(True)
                
                logger.info(f"Vídeo selecionado: {self.video_path}")
                
            except Exception as e:
                self.info_video.setText(f"❌ Erro ao acessar arquivo: {e}")
                self.info_video.setStyleSheet("color: #f44336; margin: 5px;")
                self.btn_analisar.setEnabled(False)
        else:
            self.video_path = None
            self.info_video.setText("Nenhum vídeo selecionado")
            self.info_video.setStyleSheet("color: #888; font-style: italic; margin: 5px;")
            self.btn_analisar.setEnabled(False)
