"""Widget de legendas com preview"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QToolButton,
    QLabel, QScrollArea, QGroupBox, QComboBox, QGridLayout, QSlider, QFrame,
    QColorDialog, QListWidget, QListWidgetItem, QFileDialog, QAbstractItemView,
    QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread, QSize
from PyQt6.QtGui import QPixmap, QColor, QIcon, QPainter, QFont, QPen, QBrush, QLinearGradient
from pathlib import Path
import logging

try:
    from config.settings import settings
except ImportError:
    from ...config.settings import settings

logger = logging.getLogger(__name__)


class SinglePreviewGeneratorThread(QThread):
    """Thread para gerar um único preview sob demanda"""
    
    preview_ready = pyqtSignal(str)  # caminho
    
    def __init__(self, renderer, estilo, tamanho, force=False):
        super().__init__()
        self.renderer = renderer
        self.estilo = estilo
        self.tamanho = tamanho
        self.force = force
        
    def run(self):
        try:
            # Clonar estilo para não afetar o original durante renderização
            import copy
            estilo_clone = copy.deepcopy(self.estilo)
            
            path = self.renderer.gerar_preview(
                estilo_clone, 
                tamanho=self.tamanho, 
                force=self.force
            )
            
            if path:
                self.preview_ready.emit(str(path))
        except Exception as e:
            logger.error(f"Erro na thread de preview: {e}")


class PreviewGeneratorThread(QThread):
    """Thread para gerar previews em background (todos os tamanhos)"""
    
    preview_gerado = pyqtSignal(int, str)  # tamanho, caminho
    concluido = pyqtSignal()
    
    def __init__(self, estilo, renderer):
        super().__init__()
        self.estilo = estilo
        self.renderer = renderer
    
    def run(self):
        try:
            previews = self.renderer.gerar_previews_todos_tamanhos(self.estilo)
            
            for tamanho, caminho in previews.items():
                self.preview_gerado.emit(tamanho, str(caminho))
                
            self.concluido.emit()
        except Exception as e:
            logger.error(f"Erro ao gerar previews: {e}")


class SubtitleWidget(QWidget):
    """Widget para selecionar e visualizar estilos de legendas"""
    
    estilo_selecionado = pyqtSignal(str)  # ID do estilo
    
    def __init__(self, estilos, preview_renderer=None):
        super().__init__()
        self.estilos = estilos
        self.estilo_atual = None
        self.preview_renderer = preview_renderer
        self.previews_cache = {}  # {estilo_id: {tamanho: caminho}}
        self.preview_thread = None
        self._current_pixmap = None
        self.init_ui()

        # Inicialmente esconder lista (sem vídeos)
        self._toggle_placeholder()

        # Carregar previews existentes
        self.carregar_previews_existentes()

        # Auto-selecionar primeiro estilo e gerar preview
        if self.estilos:
            self.selecionar_estilo(self.estilos[0])
    
    def init_ui(self):
        layout = QHBoxLayout()
        layout.setSpacing(20)

        # =====================================================================
        # --- Lado Esquerdo: Logo + Seleção de Vídeos + Estilos ---
        # =====================================================================
        left_container = QFrame()
        left_container.setObjectName("GlassContainer")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(20, 16, 20, 20)
        left_layout.setSpacing(12)

        # ── Logo do Software ────────────────────────────────────────────────
        logo_frame = QFrame()
        logo_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(59,130,246,0.15), stop:1 rgba(139,92,246,0.15));
                border-radius: 12px;
                border: 1px solid rgba(59,130,246,0.3);
            }
        """)
        logo_frame_layout = QHBoxLayout(logo_frame)
        logo_frame_layout.setContentsMargins(12, 10, 12, 10)
        logo_frame_layout.setSpacing(10)

        # Carregar ícone do logo usando settings já importado no topo
        icon_path = settings.assets_dir / "icon.png"
        lbl_logo_img = QLabel()
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(
                42, 42,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            lbl_logo_img.setPixmap(pix)
        else:
            lbl_logo_img.setText("🎬")
            lbl_logo_img.setStyleSheet("font-size: 30px;")
        lbl_logo_img.setFixedSize(44, 44)
        logo_frame_layout.addWidget(lbl_logo_img)

        logo_text_layout = QVBoxLayout()
        logo_text_layout.setSpacing(0)
        lbl_app_name = QLabel("DarkAgent Pro")
        lbl_app_name.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: bold;
            font-family: 'Segoe UI', sans-serif;
            background: transparent;
            border: none;
        """)
        lbl_app_subtitle = QLabel("AI Video Studio · Legendas")
        lbl_app_subtitle.setStyleSheet("""
            color: #7dd3fc;
            font-size: 11px;
            font-family: 'Segoe UI', sans-serif;
            background: transparent;
            border: none;
        """)
        logo_text_layout.addWidget(lbl_app_name)
        logo_text_layout.addWidget(lbl_app_subtitle)
        logo_frame_layout.addLayout(logo_text_layout)
        logo_frame_layout.addStretch()
        left_layout.addWidget(logo_frame)

        # ── Seleção de Vídeos ────────────────────────────────────────────────
        videos_titulo = QLabel("📂  Vídeos para Processar")
        videos_titulo.setStyleSheet("""
            color: white;
            font-size: 13px;
            font-weight: bold;
            margin-top: 4px;
        """)
        left_layout.addWidget(videos_titulo)

        # Lista de vídeos (agora no painel esquerdo, mais visível)
        self.video_list = QListWidget()
        self.video_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.video_list.setMinimumHeight(100)
        self.video_list.setMaximumHeight(160)
        self.video_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 8px;
                color: white;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid rgba(255,255,255,0.05);
            }
            QListWidget::item:selected {
                background-color: rgba(59, 130, 246, 0.3);
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: rgba(255,255,255,0.07);
            }
            QListWidget::indicator {
                width: 16px;
                height: 16px;
            }
            QListWidget::indicator:checked {
                background-color: #3b82f6;
                border-radius: 3px;
                border: 1px solid #60a5fa;
            }
            QListWidget::indicator:unchecked {
                background-color: rgba(30,41,59,0.8);
                border-radius: 3px;
                border: 1px solid rgba(255,255,255,0.2);
            }
        """)
        left_layout.addWidget(self.video_list)

        # Placeholder label when empty
        self.lbl_no_videos = QLabel("Nenhum vídeo adicionado.\nClique em \"Adicionar Vídeos\" abaixo.")
        self.lbl_no_videos.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_videos.setStyleSheet("""
            color: #64748b;
            font-size: 12px;
            background: transparent;
            border: none;
        """)
        self.lbl_no_videos.setVisible(True)
        left_layout.addWidget(self.lbl_no_videos)

        # Botões de ação de vídeo
        video_btn_row1 = QHBoxLayout()
        video_btn_row1.setSpacing(6)

        self.btn_add_videos = QPushButton("➕  Adicionar Vídeos")
        self.btn_add_videos.clicked.connect(self.browse_videos)
        self.btn_add_videos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_videos.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        video_btn_row1.addWidget(self.btn_add_videos)

        self.btn_remove_videos = QPushButton("🗑  Remover")
        self.btn_remove_videos.clicked.connect(self.remove_selected_videos)
        self.btn_remove_videos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_videos.setStyleSheet("""
            QPushButton {
                background-color: rgba(239,68,68,0.2);
                color: #fca5a5;
                border: 1px solid rgba(239,68,68,0.4);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(239,68,68,0.35); }
        """)
        video_btn_row1.addWidget(self.btn_remove_videos)
        left_layout.addLayout(video_btn_row1)

        video_btn_row2 = QHBoxLayout()
        video_btn_row2.setSpacing(6)

        self.btn_check_all = QPushButton("✅  Marcar Todos")
        self.btn_check_all.clicked.connect(self.check_all_videos)
        self.btn_check_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_all.setStyleSheet("""
            QPushButton {
                background-color: rgba(34,197,94,0.15);
                color: #86efac;
                border: 1px solid rgba(34,197,94,0.3);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: rgba(34,197,94,0.28); }
        """)
        video_btn_row2.addWidget(self.btn_check_all)

        self.btn_uncheck_all = QPushButton("⬜  Desmarcar Todos")
        self.btn_uncheck_all.clicked.connect(self.uncheck_all_videos)
        self.btn_uncheck_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_uncheck_all.setStyleSheet("""
            QPushButton {
                background-color: rgba(100,116,139,0.15);
                color: #94a3b8;
                border: 1px solid rgba(100,116,139,0.3);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: rgba(100,116,139,0.28); }
        """)
        video_btn_row2.addWidget(self.btn_uncheck_all)
        left_layout.addLayout(video_btn_row2)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(255,255,255,0.08); max-height: 1px; border: none;")
        left_layout.addWidget(sep)

        # ── Estilos de Legenda ───────────────────────────────────────────────
        estilos_titulo = QLabel("🎨  Estilos de Legenda")
        estilos_titulo.setObjectName("SectionTitle")
        estilos_titulo.setStyleSheet("color: white; font-size: 13px; font-weight: bold;")
        left_layout.addWidget(estilos_titulo)

        estilos_subtitulo = QLabel("Escolha o estilo visual das legendas")
        estilos_subtitulo.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 8px;")
        left_layout.addWidget(estilos_subtitulo)

        # Scroll Area para Grid de Estilos
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(scroll_content)
        grid_layout.setSpacing(15)
        
        # Criar botões para cada estilo em grid
        self.botoes_estilos = {}

        row, col = 0, 0
        for estilo in self.estilos:
            nome_simples = estilo.nome.replace("TikTok ", "").replace("Instagram ", "").replace("YouTube ", "")

            btn = QToolButton()
            btn.setText(nome_simples)
            btn.setCheckable(True)
            btn.setFixedSize(130, 82)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(90, 38))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("nome_simples", nome_simples)
            btn.setStyleSheet("""
                QToolButton {
                    background-color: rgba(15, 23, 42, 0.6);
                    color: #cbd5e1;
                    border: 1.5px solid rgba(255, 255, 255, 0.08);
                    border-radius: 14px;
                    font-weight: 700;
                    font-size: 11px;
                    padding-bottom: 4px;
                }
                QToolButton:hover {
                    background-color: rgba(59, 130, 246, 0.12);
                    border: 1.5px solid rgba(59, 130, 246, 0.4);
                    color: #f0f4ff;
                }
                QToolButton:checked {
                    background-color: rgba(59, 130, 246, 0.18);
                    border: 2px solid #3b82f6;
                    color: #ffffff;
                }
            """)
            btn.clicked.connect(lambda checked, e=estilo: self.selecionar_estilo(e))
            grid_layout.addWidget(btn, row, col)
            self.botoes_estilos[estilo.id] = btn

            col += 1
            if col >= 2:
                col = 0
                row += 1
        
        grid_layout.setRowStretch(row + 1, 1)
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        
        layout.addWidget(left_container, 4)  # 40% width
        
        # --- Lado Direito: Preview e Config ---
        right_container = QFrame()
        right_container.setObjectName("GlassContainer")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(15)
        
        # Preview Area
        self.preview_canvas = QLabel()
        self.preview_canvas.setMinimumSize(240, 135)
        self.preview_canvas.setSizePolicy(
            self.preview_canvas.sizePolicy().horizontalPolicy(),
            self.preview_canvas.sizePolicy().verticalPolicy()
        )
        self.preview_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_canvas.setStyleSheet("""
            QLabel {
                background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.8, fx:0.5, fy:0.5, stop:0 #1e293b, stop:1 #0f172a);
                border-radius: 16px;
                border: 2px solid rgba(59, 130, 246, 0.4);
                padding: 4px;
            }
        """)
        self.preview_canvas.setText("Selecione um estilo")
        right_layout.addWidget(self.preview_canvas, 2)  # Diminui o peso visual do canvas
        
        # Configurações — dentro de QScrollArea para não cortar em telas pequenas
        config_group = QWidget()
        config_group.setStyleSheet("background-color: rgba(30, 41, 59, 0.5); border-radius: 12px; padding: 10px;")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(6)

        # Tamanho da Fonte
        lbl_tamanho = QLabel("Tamanho da Fonte:")
        lbl_tamanho.setStyleSheet("color: white; font-weight: bold;")
        config_layout.addWidget(lbl_tamanho)
        self.tamanho_combo = QComboBox()
        self.tamanho_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(30, 41, 59, 0.8);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                padding: 6px;
            }
            QComboBox:hover {
                border: 1px solid #3b82f6;
            }
        """)
        self.tamanho_combo.addItems([str(s) for s in [12, 18, 24, 28, 32, 36, 40, 44, 48]])
        self.tamanho_combo.setCurrentText("18")
        self.tamanho_combo.currentTextChanged.connect(self.atualizar_tamanho)
        config_layout.addWidget(self.tamanho_combo)

        # Posição
        lbl_posicao = QLabel("Posição da Legenda:")
        lbl_posicao.setStyleSheet("color: white; font-weight: bold; margin-top: 5px;")
        config_layout.addWidget(lbl_posicao)
        self.posicao_combo = QComboBox()
        self.posicao_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(30, 41, 59, 0.8);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                padding: 6px;
            }
            QComboBox:hover {
                border: 1px solid #3b82f6;
            }
        """)
        self.posicao_combo.addItems(["Embaixo", "Centro", "Topo"])
        config_layout.addWidget(self.posicao_combo)

        # Cor do Texto
        lbl_cor = QLabel("Cor do Texto:")
        lbl_cor.setStyleSheet("color: white; font-weight: bold; margin-top: 5px;")
        config_layout.addWidget(lbl_cor)
        self.btn_cor = QPushButton("🎨 Alterar Cor")
        self.btn_cor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cor.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 41, 59, 0.8);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(59, 130, 246, 0.2);
                border: 1px solid #3b82f6;
            }
        """)
        self.btn_cor.clicked.connect(self.selecionar_cor)
        config_layout.addWidget(self.btn_cor)

        # Cor da Borda
        lbl_cor_borda = QLabel("Cor da Borda:")
        lbl_cor_borda.setStyleSheet("color: white; font-weight: bold; margin-top: 5px;")
        config_layout.addWidget(lbl_cor_borda)
        self.btn_cor_borda = QPushButton("🎨 Alterar Cor da Borda")
        self.btn_cor_borda.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cor_borda.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 41, 59, 0.8);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(59, 130, 246, 0.2);
                border: 1px solid #3b82f6;
            }
        """)
        self.btn_cor_borda.clicked.connect(self.selecionar_cor_borda)
        config_layout.addWidget(self.btn_cor_borda)

        config_layout.addStretch()

        # Scroll area para o grupo de configs
        config_scroll = QScrollArea()
        config_scroll.setWidget(config_group)
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QFrame.Shape.NoFrame)
        config_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        config_scroll.setStyleSheet("background: transparent;")
        right_layout.addWidget(config_scroll, 3)  # Aumenta peso das configurações para elas não sumirem
        
        layout.addWidget(right_container, 6) # 60% width
        
        self.setLayout(layout)

    def _toggle_placeholder(self):
        """Mostra/esconde placeholder depending on list content"""
        has_items = self.video_list.count() > 0
        self.video_list.setVisible(has_items)
        self.lbl_no_videos.setVisible(not has_items)

    def browse_videos(self):
        """Abre diálogo para selecionar vídeos do computador"""
        caminhos, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar Vídeos para Legendar",
            "",
            "Arquivos de Vídeo (*.mp4 *.mov *.avi *.mkv *.webm *.wmv *.flv *.m4v)"
        )
        for caminho in caminhos:
            # Evitar duplicatas
            already = False
            for i in range(self.video_list.count()):
                if self.video_list.item(i).data(Qt.ItemDataRole.UserRole) == caminho:
                    already = True
                    break
            if not already:
                self._add_video_item(caminho)
        self._toggle_placeholder()

    def remove_selected_videos(self):
        """Remove os vídeos selecionados (highlight) da lista"""
        for item in self.video_list.selectedItems():
            self.video_list.takeItem(self.video_list.row(item))
        self._toggle_placeholder()

    def _add_video_item(self, text: str):
        """Cria e adiciona um QListWidgetItem com checkbox para um caminho/URL"""
        list_item = QListWidgetItem()
        list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        list_item.setCheckState(Qt.CheckState.Checked)
        list_item.setToolTip(text)
        if Path(text).exists() and Path(text).is_file():
            list_item.setText(f"📁 {Path(text).name}")
        else:
            list_item.setText(f"🌐 {text}")
        list_item.setData(Qt.ItemDataRole.UserRole, text)
        self.video_list.addItem(list_item)

    def update_video_list(self, items):
        """Atualiza a lista de vídeos disponíveis para processamento"""
        self.video_list.clear()
        for item in items:
            self._add_video_item(str(item))
        self._toggle_placeholder()

    def get_selected_videos(self):
        """Retorna lista de vídeos marcados (checkados)"""
        selected = []
        for i in range(self.video_list.count()):
            item = self.video_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def check_all_videos(self):
        for i in range(self.video_list.count()):
            self.video_list.item(i).setCheckState(Qt.CheckState.Checked)

    def uncheck_all_videos(self):
        for i in range(self.video_list.count()):
            self.video_list.item(i).setCheckState(Qt.CheckState.Unchecked)
    
    def carregar_previews_existentes(self):
        """Carrega previews já existentes no disco"""
        preview_dir = settings.assets_dir / "previews"
        
        if not preview_dir.exists():
            logger.info("Diretório de previews não existe ainda")
            return
        
        # Procurar por todos os arquivos de preview
        for preview_file in preview_dir.glob("*.png"):
            # Formato: {estilo_id}_size{tamanho}.png
            nome = preview_file.stem
            
            if "_size" in nome:
                partes = nome.split("_size")
                estilo_id = partes[0]
                resto = partes[1]
                
                # Tentar extrair tamanho (pode ter cor depois: 12_00FFFFFF)
                if "_" in resto:
                    tamanho_str = resto.split("_")[0]
                else:
                    tamanho_str = resto
                    
                try:
                    tamanho = int(tamanho_str)
                except ValueError:
                    logger.warning(f"Ignorando arquivo de preview com nome inválido: {preview_file.name}")
                    continue
                
                if estilo_id not in self.previews_cache:
                    self.previews_cache[estilo_id] = {}
                
                self.previews_cache[estilo_id][tamanho] = str(preview_file)
                logger.debug(f"Preview carregado: {estilo_id} tamanho {tamanho}")
        
        logger.info(f"Previews carregados: {sum(len(v) for v in self.previews_cache.values())} arquivos")
        self.atualizar_icones_botoes()
        
    @staticmethod
    def _criar_icone_estilo(cor_hex: str, cor_borda_hex: str = "#000000",
                            tem_borda: bool = True) -> QIcon:
        """Generates a styled 'Aa' preview icon using QPainter."""
        w, h = 90, 38
        pixmap = QPixmap(w, h)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cor = QColor(cor_hex)

        # ── Background pill with subtle gradient ──
        grad = QLinearGradient(0, 0, w, 0)
        bg = QColor(cor)
        bg.setAlpha(25)
        bg2 = QColor(cor)
        bg2.setAlpha(12)
        grad.setColorAt(0.0, bg)
        grad.setColorAt(1.0, bg2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(0, 0, w, h, 10, 10)

        # ── Colored accent bar on left ──
        accent = QColor(cor)
        accent.setAlpha(200)
        painter.setBrush(QBrush(accent))
        painter.drawRoundedRect(0, 6, 4, h - 12, 2, 2)

        # ── "Aa" text with optional border/shadow ──
        font = QFont("Segoe UI", 17, QFont.Weight.ExtraBold)
        painter.setFont(font)

        if tem_borda:
            # Text outline (simulated by drawing behind in border color)
            outline = QColor(cor_borda_hex)
            outline.setAlpha(180)
            painter.setPen(QPen(outline))
            for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1), (0, -1), (0, 1)]:
                painter.drawText(pixmap.rect().adjusted(12 + dx, dy, dx, dy),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 "Aa")

        # Main text
        painter.setPen(QPen(cor))
        painter.drawText(pixmap.rect().adjusted(12, 0, 0, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         "Aa")

        painter.end()
        return QIcon(pixmap)

    def _cor_ass_para_hex(self, cor_ass: str) -> str:
        """Converte cor ASS (&HBBGGRR) para hex (#RRGGBB)."""
        if len(cor_ass) >= 8:
            b, g, r = cor_ass[2:4], cor_ass[4:6], cor_ass[6:8]
            return f"#{r}{g}{b}"
        return "#FFFFFF"

    def atualizar_icones_botoes(self):
        """Atualiza os ícones dos botões com previews Aa nas cores do estilo."""
        for estilo_id, btn in self.botoes_estilos.items():
            nome = btn.property("nome_simples")

            estilo = next((e for e in self.estilos if e.id == estilo_id), None)

            cor_hex = "#FFFFFF"
            cor_borda_hex = "#000000"
            tem_borda = False

            if estilo:
                cor_hex = self._cor_ass_para_hex(estilo.cor_primaria)

                # Neon glow usa secundária para destaque
                if estilo_id == "neon_glow" and len(estilo.cor_secundaria) >= 8:
                    cor_hex = self._cor_ass_para_hex(estilo.cor_secundaria)

                if hasattr(estilo, "cor_borda"):
                    cor_borda_hex = self._cor_ass_para_hex(estilo.cor_borda)
                tem_borda = getattr(estilo, "borda_espessura", 0) > 0 or estilo_id == "neon_glow"

            cor_borda_css = cor_hex

            # Generate and set the icon
            icon = self._criar_icone_estilo(cor_hex, cor_borda_hex, tem_borda)
            btn.setIcon(icon)

            btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: rgba(15, 23, 42, 0.6);
                    color: {cor_hex};
                    border: 1.5px solid rgba(255, 255, 255, 0.08);
                    border-radius: 14px;
                    font-weight: 700;
                    font-size: 11px;
                    padding-bottom: 4px;
                }}
                QToolButton:hover {{
                    background-color: rgba(59, 130, 246, 0.12);
                    border: 1.5px solid {cor_borda_css};
                    color: #f0f4ff;
                }}
                QToolButton:checked {{
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 2px solid {cor_borda_css};
                    color: #ffffff;
                }}
            """)
            btn.setText(nome)

    def selecionar_estilo(self, estilo):
        self.estilo_atual = estilo
        self.estilo_selecionado.emit(estilo.id)
        
        # Desmarcar outros botões
        for btn_id, btn in self.botoes_estilos.items():
            btn.setChecked(btn_id == estilo.id)
        
        # Atualizar opções de tamanho se disponível no estilo
        if hasattr(estilo, 'size_options') and estilo.size_options:
            self.tamanho_combo.blockSignals(True)
            self.tamanho_combo.clear()
            self.tamanho_combo.addItems([str(s) for s in estilo.size_options])
            
            # Tentar selecionar o tamanho atual do estilo
            tamanho_str = str(estilo.tamanho)
            index = self.tamanho_combo.findText(tamanho_str)
            if index >= 0:
                self.tamanho_combo.setCurrentIndex(index)
            else:
                # Se não encontrar exato, seleciona o mais próximo ou o padrão
                self.tamanho_combo.setCurrentIndex(self.tamanho_combo.count() - 1)
                
            self.tamanho_combo.blockSignals(False)
            
        # Atualizar visual do botão de cor
        if hasattr(estilo, "cor_primaria"):
            cor_ass = estilo.cor_primaria
            cor_hex = "#FFFFFF"
            if len(cor_ass) >= 8:
                b, g, r = cor_ass[2:4], cor_ass[4:6], cor_ass[6:8]
                cor_hex = f"#{r}{g}{b}"
            
            try:
                cor_atual = QColor(cor_hex)
                self.btn_cor.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {cor_atual.name()};
                        color: {'#000000' if cor_atual.lightness() > 128 else '#ffffff'};
                        border: 2px solid rgba(255, 255, 255, 0.5);
                        border-radius: 8px;
                        padding: 8px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        border: 2px solid #3b82f6;
                    }}
                """)
                self.btn_cor.setText(f"🎨 Cor: {cor_atual.name().upper()}")
            except Exception as e:
                logger.debug(f"Erro ao parsear cor: {e}")
                
        # Atualizar visual do botão de cor da borda
        if hasattr(estilo, "cor_borda"):
            cor_ass_borda = estilo.cor_borda
            cor_hex_borda = "#000000"
            if len(cor_ass_borda) >= 8:
                b, g, r = cor_ass_borda[2:4], cor_ass_borda[4:6], cor_ass_borda[6:8]
                cor_hex_borda = f"#{r}{g}{b}"
            
            try:
                cor_atual_b = QColor(cor_hex_borda)
                self.btn_cor_borda.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {cor_atual_b.name()};
                        color: {'#000000' if cor_atual_b.lightness() > 128 else '#ffffff'};
                        border: 2px solid rgba(255, 255, 255, 0.5);
                        border-radius: 8px;
                        padding: 8px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        border: 2px solid #3b82f6;
                    }}
                """)
                self.btn_cor_borda.setText(f"🎨 Borda: {cor_atual_b.name().upper()}")
                
                # Só destacar ou mostrar se tiver borda
                if getattr(estilo, "borda_espessura", 0) > 0 or estilo.id == "neon_glow":
                    self.btn_cor_borda.setVisible(True)
                else:
                    self.btn_cor_borda.setVisible(False)
            except Exception as e:
                logger.debug(f"Erro ao parsear cor da borda: {e}")
        
        # Atualizar preview
        self.atualizar_preview()

    def atualizar_tamanho(self, texto):
        """Atualiza o tamanho do estilo atual quando o combo muda"""
        if self.estilo_atual and texto.isdigit():
            self.estilo_atual.tamanho = int(texto)
            self.estilo_atual.tamanho = int(texto)
            self.atualizar_preview()

    def selecionar_cor(self):
        """Abre diálogo para selecionar cor do texto"""
        if not self.estilo_atual:
            return
            
        # Converter cor ASS atual para QColor
        cor_ass = self.estilo_atual.cor_primaria
        # &HBBGGRR -> #RRGGBB
        cor_hex = "#FFFFFF"
        if len(cor_ass) >= 8:
            b, g, r = cor_ass[2:4], cor_ass[4:6], cor_ass[6:8]
            cor_hex = f"#{r}{g}{b}"
            
        cor_atual = QColor(cor_hex)
        
        nova_cor = QColorDialog.getColor(cor_atual, self, "Selecione a Cor do Texto")
        
        if nova_cor.isValid():
            # Converter QColor para ASS (&HBBGGRR)
            r = f"{nova_cor.red():02X}"
            g = f"{nova_cor.green():02X}"
            b = f"{nova_cor.blue():02X}"
            
            # ASS usa BGR
            cor_ass_nova = f"&H{b}{g}{r}"
            
            self.estilo_atual.cor_primaria = cor_ass_nova
            
            # Atualizar botão com a cor (opcional, visual feedback)
            self.btn_cor.setStyleSheet(f"""
                QPushButton {{
                    background-color: {nova_cor.name()};
                    color: {'#000000' if nova_cor.lightness() > 128 else '#ffffff'};
                    border: 2px solid rgba(255, 255, 255, 0.5);
                    border-radius: 8px;
                    padding: 8px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    border: 2px solid #3b82f6;
                }}
            """)
            self.btn_cor.setText(f"🎨 Cor: {nova_cor.name().upper()}")
            self.atualizar_icones_botoes()
            
            # Forçar atualização do preview
            self.atualizar_preview(force=True)

    def selecionar_cor_borda(self):
        """Abre diálogo para selecionar cor da borda"""
        if not self.estilo_atual:
            return
            
        cor_ass = self.estilo_atual.cor_borda
        cor_hex = "#000000"
        if len(cor_ass) >= 8:
            b, g, r = cor_ass[2:4], cor_ass[4:6], cor_ass[6:8]
            cor_hex = f"#{r}{g}{b}"
            
        cor_atual = QColor(cor_hex)
        nova_cor = QColorDialog.getColor(cor_atual, self, "Selecione a Cor da Borda")
        
        if nova_cor.isValid():
            r = f"{nova_cor.red():02X}"
            g = f"{nova_cor.green():02X}"
            b = f"{nova_cor.blue():02X}"
            
            cor_ass_nova = f"&H{b}{g}{r}"
            self.estilo_atual.cor_borda = cor_ass_nova
            
            self.btn_cor_borda.setStyleSheet(f"""
                QPushButton {{
                    background-color: {nova_cor.name()};
                    color: {'#000000' if nova_cor.lightness() > 128 else '#ffffff'};
                    border: 2px solid rgba(255, 255, 255, 0.5);
                    border-radius: 8px;
                    padding: 8px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    border: 2px solid #3b82f6;
                }}
            """)
            self.btn_cor_borda.setText(f"🎨 Borda: {nova_cor.name().upper()}")
            
            # Forçar atualização do preview
            self.atualizar_preview(force=True)

    def atualizar_preview(self, force=False):
        """Atualiza o preview exibido"""
        if not self.estilo_atual:
            self.preview_canvas.setText("Selecione um estilo de legenda")
            return
        
        # Verificar cache de previews para este estilo
        estilo_id = self.estilo_atual.id
        tamanho = self.estilo_atual.tamanho
        
        # Incluir cor no cache key se necessário, mas por enquanto usamos o path do arquivo
        # Sanitizar cor para busca no cache
        cor_safe = self.estilo_atual.cor_primaria.replace("&H", "").replace("&", "")
        
        # Se force=True, ignorar cache e regenerar
        if force:
            caminho_preview = None
        else:
            # Tentar encontrar preview exato para o tamanho e cor
            caminho_preview = None
        
        if estilo_id in self.previews_cache:
            # Primeiro, tentar tamanho exato
            if tamanho in self.previews_cache[estilo_id]:
                # Verificar se o caminho contém a cor atual (se implementado no cache)
                # Como o cache atual é simples {tamanho: path}, precisamos verificar o nome do arquivo
                path_cache = self.previews_cache[estilo_id][tamanho]
                if cor_safe in Path(path_cache).name:
                    caminho_preview = path_cache
                    logger.debug(f"Preview encontrado: {estilo_id} tamanho {tamanho} cor {cor_safe}")
                else:
                    # Cor diferente, ignorar cache
                    caminho_preview = None
            else:
                # Procurar tamanho mais próximo
                tamanhos_disponiveis = sorted(self.previews_cache[estilo_id].keys())
                if tamanhos_disponiveis:
                    # Encontrar o mais próximo
                    tamanho_proximo = min(tamanhos_disponiveis, key=lambda x: abs(x - tamanho))
                    caminho_preview = self.previews_cache[estilo_id][tamanho_proximo]
                    logger.debug(f"Usando preview próximo: {estilo_id} tamanho {tamanho_proximo}")
        
        # Carregar e exibir preview
        if caminho_preview and Path(caminho_preview).exists():
            pixmap = QPixmap(caminho_preview)
            if not pixmap.isNull():
                self._exibir_pixmap(pixmap)
                logger.debug(f"Preview exibido: {caminho_preview}")
                return

        # Fallback: gerar preview sob demanda (ASYNC)
        if self.preview_renderer:
            logger.info(f"Iniciando geração de preview async para {estilo_id} tamanho {tamanho}")
            self.preview_canvas.setText("⏳ Gerando preview...")

            if self.preview_thread and self.preview_thread.isRunning():
                self.preview_thread.terminate()
                self.preview_thread.wait()

            self.preview_thread = SinglePreviewGeneratorThread(
                self.preview_renderer,
                self.estilo_atual,
                tamanho,
                force=force
            )
            self.preview_thread.preview_ready.connect(self._on_preview_ready)
            self.preview_thread.start()
            return

        # Fallback final
        info = f"{self.estilo_atual.nome}\n\nTamanho: {self.estilo_atual.tamanho}px"
        self.preview_canvas.setText(info)

    def _exibir_pixmap(self, pixmap):
        """Escala o pixmap ao tamanho atual do canvas e exibe."""
        cw = max(self.preview_canvas.width(), 320)
        ch = max(self.preview_canvas.height(), 180)
        scaled = pixmap.scaled(cw, ch,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self.preview_canvas.setPixmap(scaled)
        # Guardar para re-escalar ao redimensionar
        self._current_pixmap = pixmap

    def resizeEvent(self, event):
        """Re-escala o preview quando a janela é redimensionada."""
        super().resizeEvent(event)
        if hasattr(self, "_current_pixmap") and self._current_pixmap:
            self._exibir_pixmap(self._current_pixmap)

    def _on_preview_ready(self, path):
        """Callback quando o preview async fica pronto."""
        if not self.estilo_atual:
            return

        estilo_id = self.estilo_atual.id
        tamanho = self.estilo_atual.tamanho

        if estilo_id not in self.previews_cache:
            self.previews_cache[estilo_id] = {}
        self.previews_cache[estilo_id][tamanho] = path

        if Path(path).exists():
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._exibir_pixmap(pixmap)
                logger.info(f"Preview async exibido: {path}")
        
        # Atualiza os botões dinamicamente assim que os previews ficam prontos
        self.atualizar_icones_botoes()
    
    def recarregar_previews(self):
        """Recarrega previews após geração em background"""
        self.carregar_previews_existentes()
        
        # Atualizar preview se houver estilo selecionado
        if self.estilo_atual:
            self.atualizar_preview()
            logger.info(f"Previews recarregados - estilo atual: {self.estilo_atual.nome}")
    
    def get_estilo_atual(self):
        return self.estilo_atual

