from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QTextEdit, QPushButton, QFileDialog, 
    QGroupBox, QMessageBox, QProgressBar, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from pathlib import Path
import logging

from core.uploader import TikTokUploader

logger = logging.getLogger(__name__)

class LoginThread(QThread):
    concluido = pyqtSignal(bool, str)

    def __init__(self, uploader, browser="chrome"):
        super().__init__()
        self.uploader = uploader
        self.browser = browser

    def run(self):
        try:
            success = self.uploader.login(browser_name=self.browser)
            if success:
                self.concluido.emit(True, "Login realizado com sucesso!")
            else:
                self.concluido.emit(False, "Login cancelado ou falhou.")
        except Exception as e:
            self.concluido.emit(False, f"Erro: {str(e)}")

class UploaderThread(QThread):
    progresso = pyqtSignal(str) # Status message
    concluido = pyqtSignal(bool, str) # Success, Message

    def __init__(self, video_path, title, hashtags, browser="chrome"):
        super().__init__()
        self.video_path = video_path
        self.title = title
        self.hashtags = hashtags
        self.browser = browser
        self.uploader = TikTokUploader()

    def run(self):
        try:
            self.progresso.emit("Iniciando upload...")
            success = self.uploader.upload(
                self.video_path, 
                self.title, 
                self.hashtags, 
                headless=True,
                browser_name=self.browser
            )
            
            if success:
                self.concluido.emit(True, "Upload realizado com sucesso!")
            else:
                self.concluido.emit(False, "Falha no upload. Verifique cookies e arquivo.")
                
        except Exception as e:
            self.concluido.emit(False, f"Erro: {str(e)}")

class UploadWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.uploader = TikTokUploader() 
        self.login_thread = None

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- File Selection ---
        file_group = QGroupBox("Arquivo de Vídeo")
        file_layout = QHBoxLayout()
        
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Selecione o vídeo para upload...")
        self.btn_browse = QPushButton("Procurar...")
        self.btn_browse.clicked.connect(self.browse_file)
        
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(self.btn_browse)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # --- Metadata ---
        meta_group = QGroupBox("Detalhes do Vídeo")
        meta_layout = QVBoxLayout()
        
        meta_layout.addWidget(QLabel("Título:"))
        self.txt_title_field = QLineEdit()
        self.txt_title_field.setPlaceholderText("Título do vídeo (curto)")
        
        meta_layout.addWidget(QLabel("Legenda/Descrição:"))
        self.txt_caption = QTextEdit()
        self.txt_caption.setMaximumHeight(80)
        
        meta_layout.addWidget(QLabel("Hashtags (separadas por espaço):"))
        self.txt_hashtags = QLineEdit()
        self.txt_hashtags.setPlaceholderText("Ex: #fy #viral #darkagent")
        
        meta_layout.addWidget(self.txt_title_field)
        meta_layout.addWidget(self.txt_caption)
        meta_layout.addWidget(self.txt_hashtags)
        meta_group.setLayout(meta_layout)
        layout.addWidget(meta_group)


        # --- Account Status ---
        account_group = QGroupBox("Conta TikTok")
        account_layout = QHBoxLayout()
        
        self.lbl_status = QLabel("Status: Verificando...")
        self.btn_login = QPushButton("Conectar Conta")
        self.btn_login.clicked.connect(self.connect_account)
        
        account_layout.addWidget(self.lbl_status)
        account_layout.addWidget(self.btn_login)
        account_group.setLayout(account_layout)
        layout.addWidget(account_group)
        
        # --- Browser Selection ---
        browser_group = QGroupBox("Navegador")
        browser_layout = QHBoxLayout()
        
        browser_layout.addWidget(QLabel("Navegador para automação:"))
        self.combo_browser = QComboBox()
        self.combo_browser.addItems(["chrome", "brave", "firefox", "edge"])
        browser_layout.addWidget(self.combo_browser)
        
        browser_group.setLayout(browser_layout)
        layout.addWidget(browser_group)

        self.check_login_status()

        # --- Action ---
        self.btn_upload = QPushButton("🚀 Enviar para TikTok")
        self.btn_upload.setMinimumHeight(50)
        self.btn_upload.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #E91E63; color: white;")
        self.btn_upload.clicked.connect(self.start_upload)
        layout.addWidget(self.btn_upload)

        # Output/Progress
        self.lbl_progress = QLabel("")
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_progress)

        layout.addStretch()

    def browse_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Vídeo", "", "Video Files (*.mp4 *.mov *.avi)"
        )
        if filename:
            self.file_path.setText(filename)

    def check_login_status(self):
        if Path("cookies.txt").exists():
            self.lbl_status.setText("Status: ✅ Conectado")
            self.lbl_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.btn_login.setText("Reconectar")
        else:
            self.lbl_status.setText("Status: ❌ Não conectado")
            self.lbl_status.setStyleSheet("color: #F44336; font-weight: bold;")

    def connect_account(self):
        """Launches the browser for login"""
        # Disable button to prevent double click
        self.btn_login.setEnabled(False)
        self.lbl_progress.setText("Abrindo navegador para login...")
        
        self.lbl_progress.setText("Abrindo navegador para login...")
        
        browser = self.combo_browser.currentText()
        self.login_thread = LoginThread(self.uploader, browser=browser)
        self.login_thread.concluido.connect(self.login_finished)
        self.login_thread.start()

    def login_finished(self, success, msg):
        self.btn_login.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sucesso", msg)
            self.lbl_progress.setText("✅ Login salvo com sucesso")
            self.check_login_status()
        else:
            QMessageBox.warning(self, "Aviso", msg)
            self.lbl_progress.setText("❌ Falha no login")

    def start_upload(self):
        video = self.file_path.text()
        title_text = self.txt_title_field.text() # Title
        caption_text = self.txt_caption.toPlainText() # Description
        hashtags = self.txt_hashtags.text().replace("#", "").split()
        
        if not video or not Path(video).exists():
            QMessageBox.warning(self, "Erro", "Selecione um arquivo de vídeo válido!")
            return
            
        if not caption_text:
            QMessageBox.warning(self, "Erro", "Insira uma legenda/descrição!")
            return
            
        # Initialize full title/description
        # If both title and caption exist -> Title. Caption
        final_description = caption_text
        if title_text:
             final_description = f"{title_text}. {caption_text}"

        if not Path("cookies.txt").exists():
            QMessageBox.warning(self, "Erro", "Conecte sua conta antes de enviar!")
            return

        self.btn_upload.setEnabled(False)
        self.lbl_progress.setText("Iniciando upload (Browser oculto)...")
        
        browser = self.combo_browser.currentText()
        self.upload_thread = UploaderThread(video, final_description, hashtags, browser=browser)
        self.upload_thread.progresso.connect(self.update_status)
        self.upload_thread.concluido.connect(self.upload_finished)
        self.upload_thread.start()

    def update_status(self, msg):
        self.lbl_progress.setText(msg)

    def upload_finished(self, success, msg):
        self.btn_upload.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sucesso", msg)
            self.lbl_progress.setText("✅ Upload concluído!")
        else:
            QMessageBox.critical(self, "Erro", msg)
            self.lbl_progress.setText("❌ Falha no upload")

    def set_file(self, path):
        """Set file path programmatically"""
        self.file_path.setText(str(path))
