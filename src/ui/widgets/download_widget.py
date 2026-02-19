"""Widget principal de download"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPlainTextEdit,
    QPushButton, QComboBox, QLabel, QFileDialog, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt
from pathlib import Path


class DownloadWidget(QWidget):
    """Widget para configurar e iniciar download"""
    
    download_iniciado = pyqtSignal(list, str, Path)  # lista_urls, qualidade, pasta
    download_video_apenas = pyqtSignal(list, str, Path)  # lista_urls, qualidade, pasta (novo sіgnal)
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Container principal com efeito de vidro
        container = QFrame()
        container.setObjectName("GlassContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(20)
        container_layout.setContentsMargins(30, 30, 30, 30)
        
        # URL Input (Multi-line for batch)
        url_label = QLabel("URLs do Vídeo (Um por linha)")
        url_label.setObjectName("SectionTitle")
        container_layout.addWidget(url_label)

        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText("📺 Cole os links dos vídeos aqui (YouTube, South Park, TikTok, etc)...\nUm link por linha.")
        self.url_input.setMinimumHeight(100)
        # Styling handled by QSS
        container_layout.addWidget(self.url_input)
        
        # Configurações em Grid
        grid_config = QHBoxLayout()
        grid_config.setSpacing(20)
        
        # Qualidade
        qualidade_group = QVBoxLayout()
        qualidade_group.setSpacing(8)
        qualidade_label = QLabel("Qualidade")
        qualidade_label.setObjectName("SectionTitle")
        qualidade_group.addWidget(qualidade_label)
        
        self.qualidade_combo = QComboBox()
        self.qualidade_combo.addItems(["1080p", "720p", "480p", "360p"])
        self.qualidade_combo.setCurrentText("720p")
        self.qualidade_combo.setMinimumHeight(45)
        qualidade_group.addWidget(self.qualidade_combo)
        
        grid_config.addLayout(qualidade_group, 1)
        
        # Pasta de Saída
        pasta_group = QVBoxLayout()
        pasta_group.setSpacing(8)
        pasta_label = QLabel("Pasta de Saída")
        pasta_label.setObjectName("SectionTitle")
        pasta_group.addWidget(pasta_label)
        
        pasta_input_layout = QHBoxLayout()
        pasta_input_layout.setSpacing(10)
        
        try:
            from config.settings import settings
        except ImportError:
            from src.config.settings import settings
            
        self.pasta_label = QLineEdit(str(settings.output_dir))
        self.pasta_label.setReadOnly(True)
        self.pasta_label.setMinimumHeight(45)
        pasta_input_layout.addWidget(self.pasta_label)
        
        self.btn_pasta = QPushButton("Escolher...")
        self.btn_pasta.setMinimumHeight(45)
        self.btn_pasta.clicked.connect(self.escolher_pasta)
        pasta_input_layout.addWidget(self.btn_pasta)
        
        pasta_group.addLayout(pasta_input_layout)
        
        grid_config.addLayout(pasta_group, 2)
        
        container_layout.addLayout(grid_config)
        container_layout.addStretch()
        
        # Botão Apenas Baixar
        self.btn_baixar = QPushButton("⬇ Baixar Vídeo (Sem Legendas)")
        self.btn_baixar.setMinimumHeight(50)
        self.btn_baixar.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #3b82f6;")
        self.btn_baixar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_baixar.clicked.connect(self.on_baixar_clicked)
        container_layout.addWidget(self.btn_baixar)
        
        layout.addWidget(container)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def escolher_pasta(self):
        # Import local para evitar ciclo
        try:
            from config.settings import settings
        except ImportError:
            from src.config.settings import settings

        pasta = QFileDialog.getExistingDirectory(
            self, 
            "Escolher Pasta de Saída",
            settings.last_open_dir
        )
        if pasta:
            self.pasta_label.setText(pasta)
            
            # Salvar diretório atual
            settings.last_open_dir = pasta
            settings.last_open_dir = pasta
            settings.save_config()
            
    def on_baixar_clicked(self):
        """Emite sinal para baixar apenas o vídeo"""
        config = self.get_configuracao()
        if config["urls"]:
            self.download_video_apenas.emit(
                config["urls"], 
                config["qualidade"], 
                config["pasta"]
            )
        else:
             # Se vazio, emite lista vazia
            self.download_video_apenas.emit([], "", Path("."))
    
    def get_configuracao(self):
        # Quebrar texto em linhas e filtrar vazias
        raw_text = self.url_input.toPlainText()
        urls = [line.strip() for line in raw_text.splitlines() if line.strip()]
        
        return {
            "urls": urls,
            "qualidade": self.qualidade_combo.currentText(),
            "pasta": Path(self.pasta_label.text())
        }
