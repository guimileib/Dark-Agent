from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QPushButton, QFileDialog,
    QGroupBox, QMessageBox, QComboBox,
    QListWidget, QAbstractItemView, QRadioButton,
    QButtonGroup, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QDateTime
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDateTimeEdit
from pathlib import Path
import logging
from datetime import datetime

from core.uploader import TikTokUploader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------

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
    progresso = pyqtSignal(str)
    concluido = pyqtSignal(bool, str)

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


# ---------------------------------------------------------------------------
# Scheduled entry data class
# ---------------------------------------------------------------------------

class ScheduledPost:
    def __init__(self, video_path, title, hashtags, browser, scheduled_dt, timer):
        self.video_path = video_path
        self.title = title
        self.hashtags = hashtags
        self.browser = browser
        self.scheduled_dt = scheduled_dt   # datetime object
        self.timer = timer                 # QTimer
        self.upload_thread = None


# ---------------------------------------------------------------------------
# Main Widget
# ---------------------------------------------------------------------------

class UploadWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._scheduled_posts: list[ScheduledPost] = []
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._refresh_queue_labels)
        self._countdown_timer.start(1000)
        self.upload_thread = None
        self.login_thread = None
        self.uploader = TikTokUploader()
        self.init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- File Selection ---
        file_group = QGroupBox("Arquivos de Vídeo")
        file_layout = QVBoxLayout()

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setMinimumHeight(90)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Adicionar Vídeos...")
        self.btn_add.clicked.connect(self.browse_files)
        self.btn_remove = QPushButton("Remover Selecionados")
        self.btn_remove.clicked.connect(self.remove_selected_files)
        self.btn_clear = QPushButton("Limpar Lista")
        self.btn_clear.clicked.connect(self.clear_files)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addWidget(self.btn_clear)

        file_layout.addWidget(self.file_list)
        file_layout.addLayout(btn_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # --- Metadata ---
        meta_group = QGroupBox("Detalhes do Vídeo")
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(4)

        meta_layout.addWidget(QLabel("Título:"))
        self.txt_title_field = QLineEdit()
        self.txt_title_field.setPlaceholderText("Título curto do vídeo")
        meta_layout.addWidget(self.txt_title_field)

        meta_layout.addWidget(QLabel("Legenda / Descrição:"))
        self.txt_caption = QTextEdit()
        self.txt_caption.setPlaceholderText("Texto que aparece abaixo do vídeo")
        self.txt_caption.setMaximumHeight(72)
        meta_layout.addWidget(self.txt_caption)

        meta_layout.addWidget(QLabel("Hashtags (separadas por espaço):"))
        self.txt_hashtags = QLineEdit()
        self.txt_hashtags.setPlaceholderText("Ex: #fy #viral #darkagent")
        meta_layout.addWidget(self.txt_hashtags)

        meta_group.setLayout(meta_layout)
        layout.addWidget(meta_group)

        # --- Schedule ---
        sched_group = QGroupBox("⏰ Agendamento")
        sched_layout = QVBoxLayout()
        sched_layout.setSpacing(6)

        # Toggle: now vs scheduled
        toggle_layout = QHBoxLayout()
        self.radio_now = QRadioButton("Postar agora")
        self.radio_later = QRadioButton("Agendar para depois")
        self.radio_now.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.radio_now)
        self._mode_group.addButton(self.radio_later)
        toggle_layout.addWidget(self.radio_now)
        toggle_layout.addWidget(self.radio_later)
        toggle_layout.addStretch()
        sched_layout.addLayout(toggle_layout)

        # Date/time picker (hidden when "now")
        self.dt_picker_frame = QFrame()
        dt_frame_layout = QHBoxLayout(self.dt_picker_frame)
        dt_frame_layout.setContentsMargins(0, 0, 0, 0)
        lbl_dt = QLabel("Data e hora:")
        self.dt_picker = QDateTimeEdit()
        self.dt_picker.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.dt_picker.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.dt_picker.setCalendarPopup(True)
        self.dt_picker.setMinimumDateTime(QDateTime.currentDateTime().addSecs(60))
        dt_frame_layout.addWidget(lbl_dt)
        dt_frame_layout.addWidget(self.dt_picker)
        dt_frame_layout.addStretch()
        self.dt_picker_frame.setVisible(False)
        sched_layout.addWidget(self.dt_picker_frame)

        self.radio_now.toggled.connect(lambda checked: self.dt_picker_frame.setVisible(not checked))

        sched_group.setLayout(sched_layout)
        layout.addWidget(sched_group)

        # --- Scheduled Queue ---
        self.queue_group = QGroupBox("📋 Fila de Agendamentos")
        queue_layout = QVBoxLayout()

        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(70)
        self.queue_list.setMaximumHeight(130)

        btn_cancel = QPushButton("Cancelar Selecionado")
        btn_cancel.clicked.connect(self._cancel_selected)

        queue_layout.addWidget(self.queue_list)
        queue_layout.addWidget(btn_cancel)
        self.queue_group.setLayout(queue_layout)
        self.queue_group.setVisible(False)
        layout.addWidget(self.queue_group)

        # --- Account ---
        account_group = QGroupBox("Conta TikTok")
        account_layout = QHBoxLayout()
        self.lbl_status = QLabel("Status: Verificando...")
        self.btn_login = QPushButton("Conectar Conta")
        self.btn_login.clicked.connect(self.connect_account)
        account_layout.addWidget(self.lbl_status)
        account_layout.addWidget(self.btn_login)
        account_group.setLayout(account_layout)
        layout.addWidget(account_group)

        # --- Browser ---
        browser_group = QGroupBox("Navegador")
        browser_layout = QHBoxLayout()
        browser_layout.addWidget(QLabel("Navegador para automação:"))
        self.combo_browser = QComboBox()
        self.combo_browser.addItems(["chrome", "brave", "firefox", "edge"])
        browser_layout.addWidget(self.combo_browser)
        browser_group.setLayout(browser_layout)
        layout.addWidget(browser_group)

        self.check_login_status()

        # --- Action button ---
        self.btn_upload = QPushButton("🚀 Enviar para TikTok")
        self.btn_upload.setMinimumHeight(50)
        self.btn_upload.setStyleSheet(
            "font-size: 16px; font-weight: bold; background-color: #E91E63; color: white;"
        )
        self.btn_upload.clicked.connect(self.handle_action)
        layout.addWidget(self.btn_upload)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_progress)

        layout.addStretch()

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def browse_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Vídeos", "", "Video Files (*.mp4 *.mov *.avi)"
        )
        if filenames:
            self.file_list.addItems(filenames)

    def remove_selected_files(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def clear_files(self):
        self.file_list.clear()

    def get_selected_files(self):
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def check_login_status(self):
        if Path("cookies.txt").exists():
            self.lbl_status.setText("Status: ✅ Conectado")
            self.lbl_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.btn_login.setText("Reconectar")
        else:
            self.lbl_status.setText("Status: ❌ Não conectado")
            self.lbl_status.setStyleSheet("color: #F44336; font-weight: bold;")

    def connect_account(self):
        self.btn_login.setEnabled(False)
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

    # ------------------------------------------------------------------
    # Action dispatcher
    # ------------------------------------------------------------------

    def handle_action(self):
        """Decides between posting now or scheduling."""
        files = self.get_selected_files()
        if not files:
            QMessageBox.warning(self, "Erro", "Selecione pelo menos um arquivo de vídeo!")
            return

        video = files[0]
        title_text = self.txt_title_field.text()
        caption_text = self.txt_caption.toPlainText()
        hashtags = self.txt_hashtags.text().replace("#", "").split()

        if not Path(video).exists():
            QMessageBox.warning(self, "Erro", "Arquivo de vídeo não encontrado!")
            return

        if not caption_text:
            QMessageBox.warning(self, "Erro", "Insira uma legenda/descrição!")
            return

        final_description = f"{title_text}. {caption_text}" if title_text else caption_text

        if not Path("cookies.txt").exists():
            QMessageBox.warning(self, "Erro", "Conecte sua conta antes de enviar!")
            return

        browser = self.combo_browser.currentText()

        if self.radio_now.isChecked():
            self.start_upload(video, final_description, hashtags, browser)
        else:
            self._schedule_upload(video, final_description, hashtags, browser)

    # ------------------------------------------------------------------
    # Immediate upload
    # ------------------------------------------------------------------

    def start_upload(self, video, description, hashtags, browser):
        self.btn_upload.setEnabled(False)
        self.lbl_progress.setText("Iniciando upload (Browser oculto)...")
        self.upload_thread = UploaderThread(video, description, hashtags, browser=browser)
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

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _schedule_upload(self, video, description, hashtags, browser):
        qt_dt = self.dt_picker.dateTime()
        scheduled_dt = qt_dt.toPyDateTime()

        now = datetime.now()
        delta_ms = int((scheduled_dt - now).total_seconds() * 1000)
        if delta_ms <= 0:
            QMessageBox.warning(self, "Aviso", "A data/hora agendada deve ser no futuro!")
            return

        timer = QTimer(self)
        timer.setSingleShot(True)

        post = ScheduledPost(video, description, hashtags, browser, scheduled_dt, timer)
        self._scheduled_posts.append(post)

        timer.timeout.connect(lambda p=post: self._fire_scheduled(p))
        timer.start(delta_ms)

        self._refresh_queue_ui()
        self.lbl_progress.setText(
            f"⏰ Agendado para {scheduled_dt.strftime('%d/%m/%Y %H:%M')}"
        )

    def _fire_scheduled(self, post: ScheduledPost):
        """Called by QTimer when it's time to post."""
        logger.info(f"Firing scheduled upload: {post.video_path}")
        post.upload_thread = UploaderThread(
            post.video_path, post.title, post.hashtags, browser=post.browser
        )
        post.upload_thread.concluido.connect(
            lambda ok, msg, p=post: self._scheduled_upload_finished(ok, msg, p)
        )
        post.upload_thread.start()
        self._refresh_queue_ui()

    def _scheduled_upload_finished(self, success, msg, post: ScheduledPost):
        if post in self._scheduled_posts:
            self._scheduled_posts.remove(post)
        self._refresh_queue_ui()
        status = "✅" if success else "❌"
        video_name = Path(post.video_path).name
        self.lbl_progress.setText(f"{status} Upload agendado de '{video_name}': {msg}")

    def _cancel_selected(self):
        selected = self.queue_list.currentRow()
        if selected < 0 or selected >= len(self._scheduled_posts):
            return
        post = self._scheduled_posts[selected]
        post.timer.stop()
        self._scheduled_posts.pop(selected)
        self._refresh_queue_ui()
        self.lbl_progress.setText("🗑️ Agendamento cancelado.")

    def _refresh_queue_ui(self):
        self.queue_list.clear()
        for post in self._scheduled_posts:
            video_name = Path(post.video_path).name
            dt_str = post.scheduled_dt.strftime("%d/%m %H:%M")
            item = QListWidgetItem(f"📅 {dt_str}  —  {video_name}")
            self.queue_list.addItem(item)

        has_items = len(self._scheduled_posts) > 0
        self.queue_group.setVisible(has_items)

    def _refresh_queue_labels(self):
        """Updates countdown text every second for queued posts."""
        now = datetime.now()
        for i, post in enumerate(self._scheduled_posts):
            item = self.queue_list.item(i)
            if item is None:
                continue
            delta = post.scheduled_dt - now
            total_secs = int(delta.total_seconds())
            if total_secs <= 0:
                item.setText(f"🔄 Enviando... — {Path(post.video_path).name}")
            else:
                h, rem = divmod(total_secs, 3600)
                m, s = divmod(rem, 60)
                if h > 0:
                    countdown = f"{h}h {m:02d}m"
                else:
                    countdown = f"{m:02d}m {s:02d}s"
                dt_str = post.scheduled_dt.strftime("%d/%m %H:%M")
                item.setText(
                    f"📅 {dt_str}  —  {Path(post.video_path).name}  [{countdown}]"
                )

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------

    def set_file(self, path):
        """Add file path programmatically."""
        self.file_list.addItem(str(path))
