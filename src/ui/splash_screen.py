from PyQt6.QtWidgets import (
    QSplashScreen, QProgressBar, QVBoxLayout, QLabel, 
    QWidget, QGraphicsDropShadowEffect, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QFont

class SplashScreen(QSplashScreen):
    """Tela de carregamento moderna"""
    
    def __init__(self):
        # Create a basic pixmap for the splash screen background
        # In a real app, we might load an image, but here we'll draw a gradient or solid color
        pixmap = QPixmap(600, 350)
        pixmap.fill(QColor(15, 23, 42)) # Deep Blue background
        
        super().__init__(pixmap)
        
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(40, 40, 40, 40)
        self.layout.setSpacing(20)
        
        # Logo / Title Area
        self.logo_label = QLabel("DarkAgent Pro")
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setStyleSheet("""
            color: white;
            font-size: 32px;
            font-weight: bold;
            font-family: 'Segoe UI', sans-serif;
        """)
        self.layout.addWidget(self.logo_label)
        
        self.subtitle_label = QLabel("AI Video Studio")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setStyleSheet("""
            color: #94a3b8;
            font-size: 16px;
            font-family: 'Segoe UI', sans-serif;
            margin-bottom: 20px;
        """)
        self.layout.addWidget(self.subtitle_label)
        
        self.layout.addStretch()
        
        # Loading Status
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #64748b; font-size: 12px;")
        self.layout.addWidget(self.status_label)
        
        # Progress Bar
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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #60a5fa);
                border-radius: 3px;
            }
        """)
        self.layout.addWidget(self.progress)
        
        # Add shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

    def update_progress(self, value, message=None):
        self.progress.setValue(value)
        if message:
            self.status_label.setText(message)
        if QApplication.instance():
            QApplication.instance().processEvents()
