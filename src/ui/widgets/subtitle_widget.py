"""Widget de legendas com preview"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QScrollArea, QGroupBox, QComboBox, QGridLayout, QSlider, QFrame,
    QColorDialog
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread
from PyQt6.QtGui import QPixmap, QColor
from pathlib import Path
import logging

try:
    from config import settings
except ImportError:
    from ...config import settings

logger = logging.getLogger(__name__)


class PreviewGeneratorThread(QThread):
    """Thread para gerar previews em background"""
    
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
        self.init_ui()
        
        # Carregar previews automaticamente
        self.carregar_previews_existentes()
    
    def init_ui(self):
        layout = QHBoxLayout()
        layout.setSpacing(20)
        
        # --- Lado Esquerdo: Estilos ---
        left_container = QFrame()
        left_container.setObjectName("GlassContainer")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(20, 20, 20, 20)
        
        # Título
        estilos_titulo = QLabel("Estilos de Legenda")
        estilos_titulo.setObjectName("SectionTitle")
        left_layout.addWidget(estilos_titulo)
        
        estilos_subtitulo = QLabel("Escolha o estilo visual das legendas")
        estilos_subtitulo.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 15px;")
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
        icons = {
            "tiktok_classic": "🎵",
            "tiktok_bold": "🎵",
            "reels_bold": "📷",
            "youtube_shorts": "▶️",
            "clean_minimal": "━",
            "neon_glow": "□",
            "bold_impact": "🎬"
        }
        
        row, col = 0, 0
        for estilo in self.estilos:
            icon = icons.get(estilo.id, "📝")
            nome_simples = estilo.nome.replace("TikTok ", "").replace("Instagram ", "").replace("YouTube ", "")
            
            btn = QPushButton(f"{icon}\n{nome_simples}")
            btn.setCheckable(True)
            btn.setFixedSize(110, 110)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 41, 59, 0.7);
                    color: white;
                    border: 2px solid rgba(255, 255, 255, 0.1);
                    border-radius: 16px;
                    font-weight: bold;
                    font-size: 13px;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: rgba(59, 130, 246, 0.2);
                    border: 2px solid #3b82f6;
                }
                QPushButton:checked {
                    background-color: #3b82f6;
                    border: 2px solid #60a5fa;
                }
            """)
            btn.clicked.connect(lambda checked, e=estilo: self.selecionar_estilo(e))
            grid_layout.addWidget(btn, row, col)
            self.botoes_estilos[estilo.id] = btn
            
            col += 1
            if col >= 2:  # 2 colunas
                col = 0
                row += 1
        
        grid_layout.setRowStretch(row + 1, 1)
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        
        layout.addWidget(left_container, 4) # 40% width
        
        # --- Lado Direito: Preview e Config ---
        right_container = QFrame()
        right_container.setObjectName("GlassContainer")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(15)
        
        # Preview Area
        self.preview_canvas = QLabel()
        self.preview_canvas.setMinimumSize(320, 180) # 16:9 aspect ratio base
        self.preview_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_canvas.setStyleSheet("""
            QLabel {
                background-color: #000;
                border-radius: 12px;
                border: 2px solid #334155;
            }
        """)
        self.preview_canvas.setText("Selecione um estilo")
        right_layout.addWidget(self.preview_canvas, 1) # Expand vertically
        
        # Slider de tempo (visual apenas)
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("00:00"))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setEnabled(False)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #334155;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #3b82f6;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
        """)
        time_layout.addWidget(slider)
        time_layout.addWidget(QLabel("00:10"))
        right_layout.addLayout(time_layout)
        
        # Configurações
        config_group = QWidget()
        config_group.setStyleSheet("background-color: rgba(30, 41, 59, 0.5); border-radius: 12px; padding: 10px;")
        config_layout = QVBoxLayout(config_group)
        
        # Tamanho da Fonte
        tamanho_label = QLabel("Tamanho da Fonte:")
        tamanho_label.setStyleSheet("font-weight: bold; color: #e2e8f0;")
        config_layout.addWidget(tamanho_label)
        
        self.tamanho_combo = QComboBox()
        self.tamanho_combo.addItems([str(s) for s in [12, 18, 24, 28, 32, 36, 40, 44, 48]])
        self.tamanho_combo.setCurrentText("48")
        self.tamanho_combo.currentTextChanged.connect(self.atualizar_tamanho)
        self.tamanho_combo.setMinimumHeight(40)
        config_layout.addWidget(self.tamanho_combo)
        
        config_layout.addSpacing(10)
        
        # Posição
        posicao_label = QLabel("Posição da Legenda:")
        posicao_label.setStyleSheet("font-weight: bold; color: #e2e8f0;")
        config_layout.addWidget(posicao_label)
        
        self.posicao_combo = QComboBox()
        self.posicao_combo.addItems(["Embaixo", "Centro", "Topo"])
        self.posicao_combo.setMinimumHeight(40)
        config_layout.addWidget(self.posicao_combo)
        
        config_layout.addSpacing(10)
        
        # Cor do Texto
        cor_label = QLabel("Cor do Texto:")
        cor_label.setStyleSheet("font-weight: bold; color: #e2e8f0;")
        config_layout.addWidget(cor_label)
        
        self.btn_cor = QPushButton("Alterar Cor")
        self.btn_cor.setMinimumHeight(40)
        self.btn_cor.clicked.connect(self.selecionar_cor)
        config_layout.addWidget(self.btn_cor)
        
        right_layout.addWidget(config_group)
        
        layout.addWidget(right_container, 6) # 60% width
        
        self.setLayout(layout)
    
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
            self.btn_cor.setStyleSheet(f"background-color: {nova_cor.name()}; color: {'black' if nova_cor.lightness() > 128 else 'white'}; border: 1px solid #ccc;")
            self.btn_cor.setText(f"Cor: {nova_cor.name().upper()}")
            
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
                # Escalar mantendo proporção
                scaled = pixmap.scaled(640, 360, Qt.AspectRatioMode.KeepAspectRatio, 
                                      Qt.TransformationMode.SmoothTransformation)
                self.preview_canvas.setPixmap(scaled)
                logger.debug(f"Preview exibido: {caminho_preview}")
                return
        
        # Fallback: gerar preview sob demanda
        if self.preview_renderer:
            logger.info(f"Gerando preview sob demanda para {estilo_id} tamanho {tamanho} cor {cor_safe}")
            preview_path = self.preview_renderer.gerar_preview(self.estilo_atual, tamanho=tamanho, force=force)
            
            if preview_path and preview_path.exists():
                # Adicionar ao cache
                if estilo_id not in self.previews_cache:
                    self.previews_cache[estilo_id] = {}
                self.previews_cache[estilo_id][tamanho] = str(preview_path)
                
                # Exibir
                pixmap = QPixmap(str(preview_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(640, 360, Qt.AspectRatioMode.KeepAspectRatio, 
                                          Qt.TransformationMode.SmoothTransformation)
                    self.preview_canvas.setPixmap(scaled)
                    logger.info(f"Preview gerado e exibido: {preview_path}")
                    return
        
        # Fallback final: mostrar informações do estilo
        info = f"{self.estilo_atual.nome}\n\n"
        info += f"{self.estilo_atual.texto_exemplo}\n\n"
        info += f"Tamanho: {self.estilo_atual.tamanho}px\n"
        info += f"Fonte: {self.estilo_atual.fonte}"
        self.preview_canvas.setText(info)
        logger.warning(f"Preview não disponível para {estilo_id} tamanho {tamanho}")
    
    def recarregar_previews(self):
        """Recarrega previews após geração em background"""
        self.carregar_previews_existentes()
        
        # Atualizar preview se houver estilo selecionado
        if self.estilo_atual:
            self.atualizar_preview()
            logger.info(f"Previews recarregados - estilo atual: {self.estilo_atual.nome}")
    
    def get_estilo_atual(self):
        return self.estilo_atual

