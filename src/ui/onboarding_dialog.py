from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QStackedWidget, QWidget, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont
from pathlib import Path
import logging

try:
    from config.settings import settings
except ImportError:
    from src.config.settings import settings

logger = logging.getLogger(__name__)

class OnboardingDialog(QDialog):
    """Dialogo de boas-vindas e tutorial inicial"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bem-vindo ao DarkAgent Pro")
        self.setFixedSize(800, 600)
        self.setModal(True)
        
        # Adicionar botões de minimizar e fechar explicitamente
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        
        self.init_ui()
        self.aplicar_estilo()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Área principal (Slides)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        # Adicionar slides
        self.add_slide_welcome()
        self.add_slide_step1()
        self.add_slide_step2()
        self.add_slide_step3()
        self.add_slide_step4()
        
        # Barra de navegação inferior
        nav_bar = QFrame()
        nav_bar.setObjectName("NavBar")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(20, 15, 20, 15)
        
        # Botão Pular
        self.btn_skip = QPushButton("Pular Tutorial")
        self.btn_skip.setObjectName("BtnSecondary")
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.clicked.connect(self.accept)
        nav_layout.addWidget(self.btn_skip)
        
        nav_layout.addStretch()
        
        # Indicador de páginas (bolinhas)
        self.lbl_pages = QLabel("1 / 5")
        self.lbl_pages.setObjectName("PageIndicator")
        nav_layout.addWidget(self.lbl_pages)
        
        nav_layout.addStretch()
        
        # Botões Anterior / Próximo
        self.btn_prev = QPushButton("Anterior")
        self.btn_prev.setObjectName("BtnSecondary")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.clicked.connect(self.prev_slide)
        self.btn_prev.setVisible(False)
        nav_layout.addWidget(self.btn_prev)
        
        self.btn_next = QPushButton("Próximo")
        self.btn_next.setObjectName("BtnPrimary")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.clicked.connect(self.next_slide)
        nav_layout.addWidget(self.btn_next)
        
        layout.addWidget(nav_bar)
        
    def create_slide_base(self, title, description, image_name=None):
        """Cria um slide base com título, descrição e imagem opcional"""
        slide = QWidget()
        layout = QVBoxLayout(slide)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Título
        lbl_title = QLabel(title)
        lbl_title.setObjectName("SlideTitle")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)
        
        # Imagem (placeholder ou ícone)
        if image_name:
            # Aqui poderíamos carregar uma imagem real se tivéssemos
            # Por enquanto, vamos usar um label estilizado ou tentar carregar do assets
            img_path = settings.assets_dir / image_name
            if img_path.exists():
                lbl_img = QLabel()
                pixmap = QPixmap(str(img_path))
                lbl_img.setPixmap(pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(lbl_img)
            else:
                # Placeholder
                lbl_placeholder = QLabel(f"[{image_name}]")
                lbl_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl_placeholder.setStyleSheet("color: #64748b; font-size: 14px; border: 2px dashed rgba(51, 65, 85, 0.6); border-radius: 16px; padding: 24px; background: rgba(15, 23, 42, 0.3);")
                layout.addWidget(lbl_placeholder)
        
        # Descrição
        lbl_desc = QLabel(description)
        lbl_desc.setObjectName("SlideDesc")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)
        
        layout.addStretch()
        return slide

    def add_slide_welcome(self):
        slide = self.create_slide_base(
            "Bem-vindo ao DarkAgent Pro",
            "Sua ferramenta definitiva para criar vídeos virais com legendas dinâmicas e cortes inteligentes.\n\nVamos fazer um tour rápido?",
            "icon.png"
        )
        self.stack.addWidget(slide)

    def add_slide_step1(self):
        slide = self.create_slide_base(
            "Passo 1: Cole o Link",
            "Copie o URL de um vídeo do YouTube e cole na barra principal.\nO DarkAgent baixará o vídeo automaticamente na melhor qualidade.",
            None
        )
        self.stack.addWidget(slide)

    def add_slide_step2(self):
        slide = self.create_slide_base(
            "Passo 2: Escolha o Estilo",
            "Selecione entre diversos estilos de legenda:\n\n• TikTok Classic\n• Instagram Reels\n• YouTube Shorts\n• Neon Glow\n\nVocê pode ver o preview em tempo real!",
            None
        )
        self.stack.addWidget(slide)

    def add_slide_step3(self):
        slide = self.create_slide_base(
            "Passo 3: Cortes Inteligentes",
            "Use a aba 'Cortes Inteligentes' para gerar clips virais automaticamente.\n\nA IA identifica os melhores momentos e cria vídeos verticais prontos para postar.",
            None
        )
        self.stack.addWidget(slide)
        
    def add_slide_step4(self):
        slide = self.create_slide_base(
            "Tudo Pronto!",
            "Clique em 'PROCESSAR' e deixe a mágica acontecer.\n\nO vídeo final será salvo na pasta 'output' com legendas queimadas e áudio sincronizado.\n\nVamos começar?",
            "icon.png"
        )
        self.stack.addWidget(slide)

    def next_slide(self):
        current = self.stack.currentIndex()
        if current < self.stack.count() - 1:
            self.stack.setCurrentIndex(current + 1)
            self.update_nav_buttons()
        else:
            self.accept() # Finalizar

    def prev_slide(self):
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            self.update_nav_buttons()

    def update_nav_buttons(self):
        current = self.stack.currentIndex()
        total = self.stack.count()
        
        self.lbl_pages.setText(f"{current + 1} / {total}")
        
        self.btn_prev.setVisible(current > 0)
        
        if current == total - 1:
            self.btn_next.setText("Começar!")
            self.btn_skip.setVisible(False)
        else:
            self.btn_next.setText("Próximo")
            self.btn_skip.setVisible(True)

    def aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f0f4ff;
            }
            QLabel#SlideTitle {
                font-size: 28px;
                font-weight: 800;
                color: #f8fafc;
                letter-spacing: -0.3px;
                margin-bottom: 16px;
            }
            QLabel#SlideDesc {
                font-size: 15px;
                color: #cbd5e1;
                line-height: 1.6;
            }
            QFrame#NavBar {
                background-color: rgba(8, 12, 22, 0.9);
                border-top: 1px solid rgba(51, 65, 85, 0.4);
            }
            QLabel#PageIndicator {
                color: #64748b;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton#BtnPrimary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #6366f1);
                color: white;
                border: none;
                padding: 11px 28px;
                border-radius: 12px;
                font-weight: 700;
                font-size: 14px;
            }
            QPushButton#BtnPrimary:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:1 #4f46e5);
            }
            QPushButton#BtnPrimary:pressed {
                background: #1d4ed8;
            }
            QPushButton#BtnSecondary {
                background-color: transparent;
                color: #94a3b8;
                border: 1.5px solid rgba(51, 65, 85, 0.6);
                padding: 11px 22px;
                border-radius: 12px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#BtnSecondary:hover {
                background-color: rgba(51, 65, 85, 0.4);
                color: #e2e8f0;
                border-color: rgba(59, 130, 246, 0.3);
            }
        """)
