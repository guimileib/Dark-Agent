"""Widget principal de download"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QComboBox, QLabel, QFileDialog, QFrame
)
from PyQt6.QtCore import pyqtSignal
from pathlib import Path


class DownloadWidget(QWidget):
    """Widget para configurar e iniciar download"""
    
    download_iniciado = pyqtSignal(str, str, Path)  # url, qualidade, pasta
    
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
        
        # URL Input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("📺 Cole o link do vídeo aqui...")
        self.url_input.setMinimumHeight(50)
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
            from config import settings
        except ImportError:
            from src.config import settings
            
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
        
        layout.addWidget(container)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def escolher_pasta(self):
        # Import local para evitar ciclo
        try:
            from config import settings
        except ImportError:
            from src.config import settings

        pasta = QFileDialog.getExistingDirectory(
            self, 
            "Escolher Pasta de Saída",
            settings.last_open_dir
        )
        if pasta:
            self.pasta_label.setText(pasta)
            
            # Salvar diretório atual
            settings.last_open_dir = pasta
            settings.save_config()
    
    def get_configuracao(self):
        return {
            "url": self.url_input.text().strip(),
            "qualidade": self.qualidade_combo.currentText(),
            "pasta": Path(self.pasta_label.text())
        }
