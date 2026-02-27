"""
UploadWidget — multiple TikTok accounts, multi-browser, post-now / scheduled.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QDateTime
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDateTimeEdit,
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QRadioButton, QTextEdit, QVBoxLayout, QWidget,
)

from core.uploader import (
    TikTokUploader,
    add_account,
    list_accounts,
    remove_account,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class LoginThread(QThread):
    finished = pyqtSignal(bool, str)   # success, message

    def __init__(self, account_name: str, browser: str):
        super().__init__()
        self.account_name = account_name
        self.browser = browser

    def run(self):
        uploader = TikTokUploader(self.account_name)
        try:
            ok = uploader.login(browser_name=self.browser)
            if ok:
                self.finished.emit(True, f"Conta '{self.account_name}' conectada com sucesso!")
            else:
                self.finished.emit(False, "Login cancelado ou expirou.")
        except Exception as exc:
            self.finished.emit(False, f"Erro: {exc}")


class UploaderThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        account_name: str,
        video_path: str,
        description: str,
        hashtags: list[str],
        browser: str,
        headless: bool = True,
    ):
        super().__init__()
        self.account_name = account_name
        self.video_path = video_path
        self.description = description
        self.hashtags = hashtags
        self.browser = browser
        self.headless = headless

    def run(self):
        uploader = TikTokUploader(self.account_name)
        try:
            self.progress.emit(f"🚀 Iniciando upload com conta '{self.account_name}'…")
            ok = uploader.upload(
                video_path=self.video_path,
                title=self.description,
                hashtags=self.hashtags,
                headless=self.headless,
                browser_name=self.browser,
            )
            if ok:
                self.finished.emit(True, "Upload realizado com sucesso!")
            else:
                self.finished.emit(False, "Falha no upload. Verifique os cookies e o arquivo.")
        except Exception as exc:
            self.finished.emit(False, f"Erro: {exc}")


# ---------------------------------------------------------------------------
# Scheduled post data class
# ---------------------------------------------------------------------------

class ScheduledPost:
    def __init__(self, account_name, video_path, description, hashtags, browser, scheduled_dt, timer):
        self.account_name = account_name
        self.video_path = video_path
        self.description = description
        self.hashtags = hashtags
        self.browser = browser
        self.scheduled_dt: datetime = scheduled_dt
        self.timer: QTimer = timer
        self.upload_thread: UploaderThread | None = None


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class UploadWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._scheduled_posts: list[ScheduledPost] = []
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._refresh_queue_labels)
        self._countdown_timer.start(1000)
        self.login_thread: LoginThread | None = None
        self.upload_thread: UploaderThread | None = None
        self._init_ui()
        self._refresh_accounts()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Accounts ──────────────────────────────────────────────────
        acc_group = QGroupBox("👤 Contas TikTok")
        acc_layout = QVBoxLayout(acc_group)

        # List of connected accounts
        self.account_list = QListWidget()
        self.account_list.setFixedHeight(110)
        self.account_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        acc_layout.addWidget(self.account_list)

        acc_btn_row = QHBoxLayout()
        self.btn_add_account = QPushButton("➕ Adicionar Conta")
        self.btn_add_account.clicked.connect(self._on_add_account)
        self.btn_remove_account = QPushButton("🗑️ Remover Selecionada")
        self.btn_remove_account.clicked.connect(self._on_remove_account)
        acc_btn_row.addWidget(self.btn_add_account)
        acc_btn_row.addWidget(self.btn_remove_account)
        acc_layout.addLayout(acc_btn_row)

        # Status label for selected account
        self.lbl_account_status = QLabel("Selecione uma conta na lista acima.")
        self.lbl_account_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        acc_layout.addWidget(self.lbl_account_status)

        root.addWidget(acc_group)

        # ── Browser ───────────────────────────────────────────────────
        browser_group = QGroupBox("🌐 Navegador para Automação")
        browser_row = QHBoxLayout(browser_group)
        browser_row.addWidget(QLabel("Navegador:"))
        self.combo_browser = QComboBox()
        self.combo_browser.addItems(["chrome", "brave", "firefox", "edge"])
        browser_row.addWidget(self.combo_browser)
        browser_row.addStretch()
        root.addWidget(browser_group)

        # ── Files ─────────────────────────────────────────────────────
        file_group = QGroupBox("🎬 Arquivos de Vídeo")
        file_layout = QVBoxLayout(file_group)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setMinimumHeight(80)
        file_layout.addWidget(self.file_list)

        file_btn_row = QHBoxLayout()
        btn_add_file = QPushButton("Adicionar Vídeos…")
        btn_add_file.clicked.connect(self._browse_files)
        btn_remove_file = QPushButton("Remover Selecionados")
        btn_remove_file.clicked.connect(self._remove_selected_files)
        btn_clear_files = QPushButton("Limpar Lista")
        btn_clear_files.clicked.connect(self._clear_files)
        file_btn_row.addWidget(btn_add_file)
        file_btn_row.addWidget(btn_remove_file)
        file_btn_row.addWidget(btn_clear_files)
        file_layout.addLayout(file_btn_row)
        root.addWidget(file_group)

        # ── Metadata ──────────────────────────────────────────────────
        meta_group = QGroupBox("📝 Detalhes do Vídeo")
        meta_layout = QVBoxLayout(meta_group)
        meta_layout.setSpacing(4)

        meta_layout.addWidget(QLabel("Título:"))
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Título curto do vídeo")
        meta_layout.addWidget(self.txt_title)

        meta_layout.addWidget(QLabel("Legenda / Descrição:"))
        self.txt_caption = QTextEdit()
        self.txt_caption.setPlaceholderText("Texto que aparece abaixo do vídeo")
        self.txt_caption.setMaximumHeight(72)
        meta_layout.addWidget(self.txt_caption)

        meta_layout.addWidget(QLabel("Hashtags (separadas por espaço):"))
        self.txt_hashtags = QLineEdit()
        self.txt_hashtags.setPlaceholderText("Ex: #fy #viral #darkagent")
        meta_layout.addWidget(self.txt_hashtags)

        root.addWidget(meta_group)

        # ── Schedule ──────────────────────────────────────────────────
        sched_group = QGroupBox("⏰ Agendamento")
        sched_layout = QVBoxLayout(sched_group)
        sched_layout.setSpacing(6)

        toggle_row = QHBoxLayout()
        self.radio_now = QRadioButton("Postar agora")
        self.radio_later = QRadioButton("Agendar para depois")
        self.radio_now.setChecked(True)
        mode_grp = QButtonGroup(self)
        mode_grp.addButton(self.radio_now)
        mode_grp.addButton(self.radio_later)
        toggle_row.addWidget(self.radio_now)
        toggle_row.addWidget(self.radio_later)
        toggle_row.addStretch()
        sched_layout.addLayout(toggle_row)

        self.dt_frame = QFrame()
        dt_row = QHBoxLayout(self.dt_frame)
        dt_row.setContentsMargins(0, 0, 0, 0)
        dt_row.addWidget(QLabel("Data e hora:"))
        self.dt_picker = QDateTimeEdit()
        self.dt_picker.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.dt_picker.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.dt_picker.setCalendarPopup(True)
        self.dt_picker.setMinimumDateTime(QDateTime.currentDateTime().addSecs(60))
        dt_row.addWidget(self.dt_picker)
        dt_row.addStretch()
        self.dt_frame.setVisible(False)
        self.radio_now.toggled.connect(lambda checked: self.dt_frame.setVisible(not checked))
        sched_layout.addWidget(self.dt_frame)

        root.addWidget(sched_group)

        # ── Scheduled queue ───────────────────────────────────────────
        self.queue_group = QGroupBox("📋 Fila de Agendamentos")
        queue_layout = QVBoxLayout(self.queue_group)

        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(60)
        self.queue_list.setMaximumHeight(120)
        queue_layout.addWidget(self.queue_list)

        btn_cancel = QPushButton("Cancelar Selecionado")
        btn_cancel.clicked.connect(self._cancel_selected)
        queue_layout.addWidget(btn_cancel)

        self.queue_group.setVisible(False)
        root.addWidget(self.queue_group)

        # ── Action button ─────────────────────────────────────────────
        self.btn_upload = QPushButton("🚀 Enviar para TikTok")
        self.btn_upload.setMinimumHeight(50)
        self.btn_upload.setStyleSheet(
            "font-size: 16px; font-weight: bold; background-color: #E91E63; color: white;"
        )
        self.btn_upload.clicked.connect(self._handle_action)
        root.addWidget(self.btn_upload)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_progress)

        root.addStretch()

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def _refresh_accounts(self):
        """Reload the account list from disk and update the UI."""
        self.account_list.clear()
        accounts = list_accounts()
        for acc in accounts:
            item = QListWidgetItem(f"✅  {acc['name']}")
            item.setData(Qt.ItemDataRole.UserRole, acc["name"])
            self.account_list.addItem(item)

        if accounts:
            self.account_list.setCurrentRow(0)
            self.lbl_account_status.setText(
                f"Conta ativa: {accounts[0]['name']}"
            )
        else:
            self.lbl_account_status.setText("Nenhuma conta conectada. Clique em '➕ Adicionar Conta'.")

        self.account_list.currentItemChanged.connect(self._on_account_selected)

    def _on_account_selected(self, current, _previous):
        if current:
            name = current.data(Qt.ItemDataRole.UserRole)
            self.lbl_account_status.setText(f"Conta ativa: {name}")

    def _selected_account_name(self) -> str | None:
        item = self.account_list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_add_account(self):
        name, ok = QInputDialog.getText(
            self,
            "Nova Conta",
            "Nome para identificar a conta (ex: conta_pessoal):",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        browser = self.combo_browser.currentText()

        self.btn_add_account.setEnabled(False)
        self.lbl_progress.setText(f"Abrindo {browser} para login de '{name}'…")

        self.login_thread = LoginThread(name, browser)
        self.login_thread.finished.connect(lambda ok, msg: self._login_done(ok, msg))
        self.login_thread.start()

    def _login_done(self, success: bool, msg: str):
        self.btn_add_account.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sucesso", msg)
            self.lbl_progress.setText("✅ Conta adicionada com sucesso!")
        else:
            QMessageBox.warning(self, "Aviso", msg)
            self.lbl_progress.setText("❌ Falha no login")
        self._refresh_accounts()

    def _on_remove_account(self):
        name = self._selected_account_name()
        if not name:
            QMessageBox.warning(self, "Aviso", "Selecione uma conta na lista.")
            return
        reply = QMessageBox.question(
            self,
            "Remover Conta",
            f"Remover a conta '{name}'?\nOs cookies serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            remove_account(name)
            self._refresh_accounts()
            self.lbl_progress.setText(f"🗑️ Conta '{name}' removida.")

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _browse_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Vídeos", "", "Video Files (*.mp4 *.mov *.avi *.mkv)"
        )
        if filenames:
            self.file_list.addItems(filenames)

    def _remove_selected_files(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _clear_files(self):
        self.file_list.clear()

    def get_selected_files(self) -> list[str]:
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]

    # ------------------------------------------------------------------
    # Action dispatcher
    # ------------------------------------------------------------------

    def _handle_action(self):
        account_name = self._selected_account_name()
        if not account_name:
            QMessageBox.warning(self, "Erro", "Adicione e selecione uma conta antes de enviar!")
            return

        files = self.get_selected_files()
        if not files:
            QMessageBox.warning(self, "Erro", "Selecione pelo menos um arquivo de vídeo!")
            return

        video = files[0]
        if not Path(video).exists():
            QMessageBox.warning(self, "Erro", "Arquivo de vídeo não encontrado!")
            return

        caption = self.txt_caption.toPlainText().strip()
        if not caption:
            QMessageBox.warning(self, "Erro", "Insira uma legenda/descrição!")
            return

        title = self.txt_title.text().strip()
        final_description = f"{title}. {caption}" if title else caption
        hashtags = [t.lstrip("#") for t in self.txt_hashtags.text().split() if t.strip()]
        browser = self.combo_browser.currentText()

        if self.radio_now.isChecked():
            self._start_upload(account_name, video, final_description, hashtags, browser)
        else:
            self._schedule_upload(account_name, video, final_description, hashtags, browser)

    # ------------------------------------------------------------------
    # Immediate upload
    # ------------------------------------------------------------------

    def _start_upload(self, account_name, video, description, hashtags, browser):
        self.btn_upload.setEnabled(False)
        self.lbl_progress.setText("🔄 Iniciando upload (browser oculto)…")

        self.upload_thread = UploaderThread(
            account_name=account_name,
            video_path=video,
            description=description,
            hashtags=hashtags,
            browser=browser,
            headless=True,
        )
        self.upload_thread.progress.connect(self.lbl_progress.setText)
        self.upload_thread.finished.connect(self._upload_done)
        self.upload_thread.start()

    def _upload_done(self, success: bool, msg: str):
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

    def _schedule_upload(self, account_name, video, description, hashtags, browser):
        qt_dt = self.dt_picker.dateTime()
        scheduled_dt = qt_dt.toPyDateTime()

        delta_ms = int((scheduled_dt - datetime.now()).total_seconds() * 1000)
        if delta_ms <= 0:
            QMessageBox.warning(self, "Aviso", "A data/hora agendada deve ser no futuro!")
            return

        timer = QTimer(self)
        timer.setSingleShot(True)
        post = ScheduledPost(account_name, video, description, hashtags, browser, scheduled_dt, timer)
        self._scheduled_posts.append(post)
        timer.timeout.connect(lambda p=post: self._fire_scheduled(p))
        timer.start(delta_ms)

        self._refresh_queue_ui()
        self.lbl_progress.setText(
            f"⏰ Agendado para {scheduled_dt.strftime('%d/%m/%Y %H:%M')} | conta: {account_name}"
        )

    def _fire_scheduled(self, post: ScheduledPost):
        logger.info(f"Firing scheduled upload: {post.video_path} (account={post.account_name})")
        post.upload_thread = UploaderThread(
            account_name=post.account_name,
            video_path=post.video_path,
            description=post.description,
            hashtags=post.hashtags,
            browser=post.browser,
            headless=True,
        )
        post.upload_thread.finished.connect(
            lambda ok, msg, p=post: self._scheduled_done(ok, msg, p)
        )
        post.upload_thread.start()
        self._refresh_queue_ui()

    def _scheduled_done(self, success: bool, msg: str, post: ScheduledPost):
        if post in self._scheduled_posts:
            self._scheduled_posts.remove(post)
        self._refresh_queue_ui()
        icon = "✅" if success else "❌"
        self.lbl_progress.setText(
            f"{icon} Upload agendado '{Path(post.video_path).name}' ({post.account_name}): {msg}"
        )

    def _cancel_selected(self):
        idx = self.queue_list.currentRow()
        if idx < 0 or idx >= len(self._scheduled_posts):
            return
        post = self._scheduled_posts[idx]
        post.timer.stop()
        self._scheduled_posts.pop(idx)
        self._refresh_queue_ui()
        self.lbl_progress.setText("🗑️ Agendamento cancelado.")

    def _refresh_queue_ui(self):
        self.queue_list.clear()
        for post in self._scheduled_posts:
            dt_str = post.scheduled_dt.strftime("%d/%m %H:%M")
            name = Path(post.video_path).name
            self.queue_list.addItem(f"📅 {dt_str}  —  [{post.account_name}]  {name}")
        self.queue_group.setVisible(bool(self._scheduled_posts))

    def _refresh_queue_labels(self):
        now = datetime.now()
        for i, post in enumerate(self._scheduled_posts):
            item = self.queue_list.item(i)
            if not item:
                continue
            delta = post.scheduled_dt - now
            total_s = int(delta.total_seconds())
            name = Path(post.video_path).name
            dt_str = post.scheduled_dt.strftime("%d/%m %H:%M")
            if total_s <= 0:
                item.setText(f"🔄 Enviando… — [{post.account_name}] {name}")
            else:
                h, rem = divmod(total_s, 3600)
                m, s = divmod(rem, 60)
                countdown = f"{h}h {m:02d}m" if h > 0 else f"{m:02d}m {s:02d}s"
                item.setText(f"📅 {dt_str}  —  [{post.account_name}] {name}  [{countdown}]")

    # ------------------------------------------------------------------
    # External API (called from MainWindow)
    # ------------------------------------------------------------------

    def set_file(self, path: str):
        """Add a file path programmatically (called after processing)."""
        self.file_list.addItem(str(path))
