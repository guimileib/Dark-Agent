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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #080c16, stop:0.5 #0f172a, stop:1 #0c1425);
                border-radius: 20px;
                border: 1px solid rgba(59, 130, 246, 0.15);
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
                color: #475569;
                border: none;
                font-size: 16px;
                font-weight: bold;
                border-radius: 15px;
            }
            QPushButton:hover {
                color: #e2e8f0;
                background-color: rgba(59, 130, 246, 0.15);
            }
        """)
        top_bar.addWidget(self.btn_minimize)
        self.layout_v.addLayout(top_bar)

        # ── Título ───────────────────────────────────────────────────
        self.logo_label = QLabel("DarkAgent Pro")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setStyleSheet("""
            color: #f8fafc;
            font-size: 36px;
            font-weight: 800;
            font-family: 'Segoe UI', sans-serif;
            letter-spacing: -0.5px;
        """)
        self.layout_v.addWidget(self.logo_label)

        self.subtitle_label = QLabel("AI Video Studio")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setStyleSheet("""
            color: #60a5fa;
            font-size: 15px;
            font-weight: 600;
            font-family: 'Segoe UI', sans-serif;
            letter-spacing: 2px;
            margin-bottom: 20px;
        """)
        self.layout_v.addWidget(self.subtitle_label)

        self.layout_v.addStretch()

        # ── Status + Progress bar ────────────────────────────────────
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500; letter-spacing: 0.3px;")
        self.layout_v.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: rgba(30, 41, 59, 0.5);
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:0.5 #6366f1, stop:1 #8b5cf6);
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
