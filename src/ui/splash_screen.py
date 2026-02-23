from PyQt6.QtWidgets import (
    QProgressBar, QVBoxLayout, QLabel,
    QWidget, QGraphicsDropShadowEffect, QApplication, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class SplashScreen(QWidget):
    """Tela de carregamento moderna com suporte a minimizar."""

    def __init__(self):
        super().__init__(None)

        # FramelessWindowHint mantém visual limpo
        # Window garante entrada na taskbar do Windows → permite minimizar
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(600, 350)

        # Centralizar na tela disponível
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - 600) // 2,
            screen.y() + (screen.height() - 350) // 2,
        )

        # Layout principal
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(40, 20, 40, 40)
        self.layout_v.setSpacing(20)

        # Fundo arredondado (widget filho)
        self._bg = QWidget(self)
        self._bg.setStyleSheet("""
            QWidget {
                background-color: #0F1729;
                border-radius: 16px;
            }
        """)
        self._bg.setGeometry(0, 0, 600, 350)
        self._bg.lower()

        # ── Top bar com botão minimizar ──────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        self.btn_minimize = QPushButton("─")
        self.btn_minimize.setFixedSize(30, 30)
        self.btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minimize.clicked.connect(self.showMinimized)
        self.btn_minimize.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: white;
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
            }
        """)
        top_bar.addWidget(self.btn_minimize)
        self.layout_v.addLayout(top_bar)

        # ── Título ───────────────────────────────────────────────────
        self.logo_label = QLabel("DarkAgent Pro")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setStyleSheet("""
            color: white;
            font-size: 32px;
            font-weight: bold;
            font-family: 'Segoe UI', sans-serif;
        """)
        self.layout_v.addWidget(self.logo_label)

        self.subtitle_label = QLabel("AI Video Studio")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setStyleSheet("""
            color: #94a3b8;
            font-size: 16px;
            font-family: 'Segoe UI', sans-serif;
            margin-bottom: 20px;
        """)
        self.layout_v.addWidget(self.subtitle_label)

        self.layout_v.addStretch()

        # ── Status + Progress bar ────────────────────────────────────
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #64748b; font-size: 12px;")
        self.layout_v.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #60a5fa);
                border-radius: 3px;
            }
        """)
        self.layout_v.addWidget(self.progress)

        # Sombra suave
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

    # ------------------------------------------------------------------

    def update_progress(self, value: int, message: str = None):
        """Atualiza barra de progresso e mensagem de status."""
        self.progress.setValue(value)
        if message:
            self.status_label.setText(message)
        if QApplication.instance():
            QApplication.instance().processEvents()

    def finish(self, window):
        """Fecha o splash e exibe a janela principal."""
        if window:
            window.show()
        self.close()
