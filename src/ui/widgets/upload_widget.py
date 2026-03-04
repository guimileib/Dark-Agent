"""
UploadWidget — multiple TikTok accounts, multi-browser, post-now / scheduled.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QDate, QThread, QTimer, pyqtSignal, QSize,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCalendarWidget, QComboBox,
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget, QSpinBox, QTimeEdit,
    QDateEdit, QSplitter, QToolButton, QCheckBox,
)
from PyQt6.QtCore import QTime, QDate

from core.uploader import (
    TikTokUploader,
    add_account,
    list_accounts,
    remove_account,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom drum-roll widget (kept for standalone use)
# ---------------------------------------------------------------------------

class DrumRoll(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, values: list[int], initial: int | None = None, fmt: str = "{:02d}"):
        super().__init__()
        self._values = values
        self._fmt = fmt
        self._idx = 0
        if initial is not None and initial in values:
            self._idx = values.index(initial)

        self.setFixedWidth(72)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._btn_up = QPushButton("▲")
        self._btn_up.setFixedHeight(28)
        self._btn_up.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_up.clicked.connect(self._step_up)

        self._lbl = QLabel(self._formatted())
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setFixedHeight(44)
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self._lbl.setFont(font)
        self._lbl.setStyleSheet(
            "color: #ffffff; background: #1e293b; border: 2px solid #3b82f6;"
            " border-radius: 8px;"
        )

        self._btn_down = QPushButton("▼")
        self._btn_down.setFixedHeight(28)
        self._btn_down.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_down.clicked.connect(self._step_down)

        lay.addWidget(self._btn_up)
        lay.addWidget(self._lbl)
        lay.addWidget(self._btn_down)

        for btn in (self._btn_up, self._btn_down):
            btn.setStyleSheet(
                "QPushButton { background: #334155; color: #94a3b8; border: none;"
                " border-radius: 6px; font-size: 13px; }"
                "QPushButton:hover { background: #3b82f6; color: white; }"
                "QPushButton:pressed { background: #2563eb; }"
            )

    def _formatted(self) -> str:
        return self._fmt.format(self._values[self._idx])

    def _step_up(self):
        self._idx = (self._idx - 1) % len(self._values)
        self._lbl.setText(self._formatted())
        self.valueChanged.emit(self._values[self._idx])

    def _step_down(self):
        self._idx = (self._idx + 1) % len(self._values)
        self._lbl.setText(self._formatted())
        self.valueChanged.emit(self._values[self._idx])

    def wheelEvent(self, event: QWheelEvent):
        if event.angleDelta().y() > 0:
            self._step_up()
        else:
            self._step_down()

    def value(self) -> int:
        return self._values[self._idx]

    def set_value(self, v: int):
        if v in self._values:
            self._idx = self._values.index(v)
            self._lbl.setText(self._formatted())


# ---------------------------------------------------------------------------
# Compact inline date+time picker (like TikTok Studio)
# ---------------------------------------------------------------------------

class InlineDateTimePicker(QWidget):
    """
    Compact date + time picker — two QSpinBox-style rows mimicking TikTok Studio.
    Shows: [🕐 HH:MM] [📅 DD/MM/YYYY]
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        now = datetime.now()
        default = now + timedelta(hours=1)
        rem = default.minute % 5
        if rem:
            default = default + timedelta(minutes=5 - rem)
        default = default.replace(second=0, microsecond=0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)

        # ── Row: time + date side by side (like TikTok) ──────────────
        row = QHBoxLayout()
        row.setSpacing(12)

        # Time picker
        time_frame = QFrame()
        time_frame.setStyleSheet(
            "QFrame { background: #1e293b; border: 1px solid #334155; border-radius: 8px; }"
        )
        time_layout = QHBoxLayout(time_frame)
        time_layout.setContentsMargins(10, 6, 10, 6)
        time_layout.setSpacing(4)

        lbl_t = QLabel("🕐")
        lbl_t.setStyleSheet("color: #94a3b8; background: transparent; border: none; font-size: 16px;")
        time_layout.addWidget(lbl_t)

        self._time_edit = QTimeEdit()
        self._time_edit.setTime(QTime(default.hour, default.minute))
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setStyleSheet(
            "QTimeEdit { background: transparent; border: none; color: #e2e8f0;"
            " font-size: 16px; font-weight: bold; }"
            "QTimeEdit::up-button { width: 16px; }"
            "QTimeEdit::down-button { width: 16px; }"
        )
        time_layout.addWidget(self._time_edit)
        row.addWidget(time_frame)

        # Date picker
        date_frame = QFrame()
        date_frame.setStyleSheet(
            "QFrame { background: #1e293b; border: 1px solid #334155; border-radius: 8px; }"
        )
        date_layout = QHBoxLayout(date_frame)
        date_layout.setContentsMargins(10, 6, 10, 6)
        date_layout.setSpacing(4)

        lbl_d = QLabel("📅")
        lbl_d.setStyleSheet("color: #94a3b8; background: transparent; border: none; font-size: 16px;")
        date_layout.addWidget(lbl_d)

        self._date_edit = QDateEdit()
        self._date_edit.setDate(QDate(default.year, default.month, default.day))
        self._date_edit.setDisplayFormat("dd/MM/yyyy")
        self._date_edit.setMinimumDate(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setStyleSheet(
            "QDateEdit { background: transparent; border: none; color: #e2e8f0;"
            " font-size: 16px; font-weight: bold; }"
            "QDateEdit::up-button { width: 16px; }"
            "QDateEdit::down-button { width: 16px; }"
            "QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: right center;"
            " width: 20px; border: none; }"
        )
        date_layout.addWidget(self._date_edit)
        row.addWidget(date_frame)
        row.addStretch()

        layout.addLayout(row)

        # Summary label
        self._lbl_summary = QLabel()
        self._lbl_summary.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._lbl_summary.setStyleSheet(
            "color: #60a5fa; font-size: 12px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(self._lbl_summary)
        self._update_summary()

        self._time_edit.timeChanged.connect(lambda _: self._update_summary())
        self._date_edit.dateChanged.connect(lambda _: self._update_summary())

    def _update_summary(self):
        dt = self.selected_datetime()
        self._lbl_summary.setText(
            f"📌  Agendado para: {dt.strftime('%A, %d/%m/%Y às %H:%M')}"
        )

    def selected_datetime(self) -> datetime:
        qd = self._date_edit.date()
        qt = self._time_edit.time()
        return datetime(qd.year(), qd.month(), qd.day(), qt.hour(), qt.minute(), 0)


# ---------------------------------------------------------------------------
# Hashtag chip widget
# ---------------------------------------------------------------------------

class HashtagBar(QWidget):
    """
    Shows added hashtags as removable chips — like TikTok Studio.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tags: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText("# Adicionar hashtag  (Enter para confirmar)")
        self._input.setStyleSheet(
            "QLineEdit { background: #0f172a; border: 1px solid #334155; border-radius: 8px;"
            " color: #e2e8f0; padding: 6px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #3b82f6; }"
        )
        self._input.returnPressed.connect(self._add_from_input)
        input_row.addWidget(self._input)

        btn_add = QPushButton("+ Add")
        btn_add.setFixedWidth(60)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(
            "QPushButton { background: #3b82f6; color: white; border: none;"
            " border-radius: 8px; padding: 6px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #2563eb; }"
        )
        btn_add.clicked.connect(self._add_from_input)
        input_row.addWidget(btn_add)
        outer.addLayout(input_row)

        # Chips scroll area
        self._chip_area = QWidget()
        self._chip_layout = QHBoxLayout(self._chip_area)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(6)
        self._chip_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._chip_area)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(46)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:horizontal { height: 4px; background: #1e293b; border-radius: 2px; }"
            "QScrollBar::handle:horizontal { background: #334155; border-radius: 2px; }"
        )
        outer.addWidget(scroll)

        # Predefined suggestions
        suggestion_row = QHBoxLayout()
        suggestion_row.setSpacing(4)
        lbl_sug = QLabel("Sugestões:")
        lbl_sug.setStyleSheet("color: #64748b; font-size: 11px; background: transparent;")
        suggestion_row.addWidget(lbl_sug)
        for tag in ["#fyp", "#viral", "#foryou", "#trending", "#fy"]:
            btn = QPushButton(tag)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: #1e293b; color: #94a3b8; border: 1px solid #334155;"
                " border-radius: 12px; padding: 2px 8px; font-size: 11px; }"
                "QPushButton:hover { background: #334155; color: #e2e8f0; }"
            )
            btn.clicked.connect(lambda checked, t=tag: self._add_tag(t))
            suggestion_row.addWidget(btn)
        suggestion_row.addStretch()
        outer.addLayout(suggestion_row)

    def _add_from_input(self):
        text = self._input.text().strip()
        if text:
            for t in text.split():
                self._add_tag(t)
            self._input.clear()

    def _add_tag(self, raw: str):
        tag = "#" + raw.lstrip("#")
        if tag in self._tags:
            return
        self._tags.append(tag)
        self._rebuild_chips()

    def _rebuild_chips(self):
        # Remove all except the stretch at end
        while self._chip_layout.count() > 1:
            item = self._chip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for tag in self._tags:
            chip = QFrame()
            chip.setStyleSheet(
                "QFrame { background: #1e3a5f; border: 1px solid #3b82f6;"
                " border-radius: 12px; padding: 2px 4px; }"
            )
            chip_row = QHBoxLayout(chip)
            chip_row.setContentsMargins(6, 2, 2, 2)
            chip_row.setSpacing(2)

            lbl = QLabel(tag)
            lbl.setStyleSheet("color: #93c5fd; font-size: 12px; font-weight: bold; border: none; background: transparent;")
            chip_row.addWidget(lbl)

            close_btn = QPushButton("✕")
            close_btn.setFixedSize(16, 16)
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; color: #64748b; font-size: 10px; }"
                "QPushButton:hover { color: #ef4444; }"
            )
            close_btn.clicked.connect(lambda _, t=tag: self._remove_tag(t))
            chip_row.addWidget(close_btn)

            # Insert before the stretch
            self._chip_layout.insertWidget(self._chip_layout.count() - 1, chip)

    def _remove_tag(self, tag: str):
        if tag in self._tags:
            self._tags.remove(tag)
            self._rebuild_chips()

    def get_tags(self) -> list[str]:
        """Return list of hashtag strings without the '#' prefix."""
        return [t.lstrip("#") for t in self._tags]

    def clear(self):
        self._tags.clear()
        self._rebuild_chips()


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
        schedule_time: str | None = None,
    ):
        super().__init__()
        self.account_name = account_name
        self.video_path = video_path
        self.description = description
        self.hashtags = hashtags
        self.browser = browser
        self.headless = headless
        self.schedule_time = schedule_time

    def run(self):
        uploader = TikTokUploader(self.account_name)
        try:
            if self.schedule_time:
                self.progress.emit(f"⏰ Agendando upload com conta '{self.account_name}' para {self.schedule_time}…")
            else:
                self.progress.emit(f"🚀 Iniciando upload com conta '{self.account_name}'…")

            ok = uploader.upload(
                video_path=self.video_path,
                title=self.description,
                hashtags=self.hashtags,
                headless=self.headless,
                browser_name=self.browser,
                schedule_time=self.schedule_time,
            )
            if ok:
                if self.schedule_time:
                    self.finished.emit(True, f"Post agendado com sucesso para {self.schedule_time}!")
                else:
                    self.finished.emit(True, "Upload realizado com sucesso!")
            else:
                self.finished.emit(False, "Falha no upload. Verifique os cookies e o arquivo.")
        except Exception as exc:
            self.finished.emit(False, f"Erro: {exc}")


# ---------------------------------------------------------------------------
# Scheduled post data class (kept for local-timer fallback)
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

        self.account_list = QListWidget()
        self.account_list.setFixedHeight(100)
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
        self.file_list.setMinimumHeight(70)
        self.file_list.setMaximumHeight(100)
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
        meta_layout.setSpacing(8)
        meta_layout.setContentsMargins(10, 14, 10, 10)

        # Title (optional note)
        title_row = QHBoxLayout()
        lbl_title = QLabel("Título:")
        lbl_title.setStyleSheet("font-weight: bold;")
        title_row.addWidget(lbl_title)
        lbl_optional_title = QLabel("(opcional)")
        lbl_optional_title.setStyleSheet("color: #64748b; font-size: 11px;")
        title_row.addWidget(lbl_optional_title)
        title_row.addStretch()
        meta_layout.addLayout(title_row)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Título curto do vídeo…")
        self.txt_title.setStyleSheet(
            "QLineEdit { background: #0f172a; border: 1px solid #334155; border-radius: 8px;"
            " color: #e2e8f0; padding: 6px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #3b82f6; }"
        )
        meta_layout.addWidget(self.txt_title)

        # Description (optional — TikTok doesn't require it)
        desc_row = QHBoxLayout()
        lbl_desc = QLabel("Descrição:")
        lbl_desc.setStyleSheet("font-weight: bold;")
        desc_row.addWidget(lbl_desc)
        lbl_optional = QLabel("(opcional — até 4000 caracteres)")
        lbl_optional.setStyleSheet("color: #64748b; font-size: 11px;")
        desc_row.addWidget(lbl_optional)
        desc_row.addStretch()
        self._char_counter = QLabel("0/4000")
        self._char_counter.setStyleSheet("color: #64748b; font-size: 11px;")
        desc_row.addWidget(self._char_counter)
        meta_layout.addLayout(desc_row)

        self.txt_caption = QTextEdit()
        self.txt_caption.setPlaceholderText("Texto que aparece abaixo do vídeo (opcional)…")
        self.txt_caption.setMinimumHeight(68)
        self.txt_caption.setMaximumHeight(90)
        self.txt_caption.setStyleSheet(
            "QTextEdit { background: #0f172a; border: 1px solid #334155; border-radius: 8px;"
            " color: #e2e8f0; padding: 6px 10px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #3b82f6; }"
        )
        self.txt_caption.textChanged.connect(self._on_caption_changed)
        meta_layout.addWidget(self.txt_caption)

        # Hashtags chip bar
        lbl_ht = QLabel("# Hashtags:")
        lbl_ht.setStyleSheet("font-weight: bold;")
        meta_layout.addWidget(lbl_ht)

        self.hashtag_bar = HashtagBar()
        meta_layout.addWidget(self.hashtag_bar)

        root.addWidget(meta_group)

        # ── Schedule ──────────────────────────────────────────────────
        sched_group = QGroupBox("⏰ Quando Publicar")
        sched_layout = QVBoxLayout(sched_group)
        sched_layout.setSpacing(8)

        toggle_row = QHBoxLayout()
        self.radio_now = QRadioButton("🟢  Agora")
        self.radio_later = QRadioButton("📅  Programar")
        self.radio_now.setChecked(True)
        mode_grp = QButtonGroup(self)
        mode_grp.addButton(self.radio_now)
        mode_grp.addButton(self.radio_later)
        self.radio_now.setStyleSheet("QRadioButton { font-size: 13px; font-weight: bold; }")
        self.radio_later.setStyleSheet("QRadioButton { font-size: 13px; font-weight: bold; }")
        toggle_row.addWidget(self.radio_now)
        toggle_row.addSpacing(20)
        toggle_row.addWidget(self.radio_later)
        toggle_row.addStretch()
        sched_layout.addLayout(toggle_row)

        # Inline date+time picker (hidden until "Programar" selected)
        self.dt_picker = InlineDateTimePicker()
        self.dt_picker.setVisible(False)
        self.radio_now.toggled.connect(lambda checked: self.dt_picker.setVisible(not checked))
        sched_layout.addWidget(self.dt_picker)

        root.addWidget(sched_group)

        # ── Scheduled queue ───────────────────────────────────────────
        self.queue_group = QGroupBox("📋 Fila de Agendamentos")
        queue_layout = QVBoxLayout(self.queue_group)

        self.queue_list = QListWidget()
        self.queue_list.setMinimumHeight(50)
        self.queue_list.setMaximumHeight(100)
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
            "QPushButton { font-size: 16px; font-weight: bold; background-color: #E91E63;"
            " color: white; border-radius: 10px; }"
            "QPushButton:hover { background-color: #c2185b; }"
            "QPushButton:disabled { background-color: #4a4a4a; color: #888; }"
        )
        self.btn_upload.clicked.connect(self._handle_action)
        root.addWidget(self.btn_upload)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_progress.setWordWrap(True)
        self.lbl_progress.setStyleSheet("font-size: 12px; color: #94a3b8;")
        root.addWidget(self.lbl_progress)

        root.addStretch()

    # ------------------------------------------------------------------
    # Caption char counter
    # ------------------------------------------------------------------

    def _on_caption_changed(self):
        n = len(self.txt_caption.toPlainText())
        self._char_counter.setText(f"{n}/4000")
        if n > 4000:
            self._char_counter.setStyleSheet("color: #ef4444; font-size: 11px;")
        else:
            self._char_counter.setStyleSheet("color: #64748b; font-size: 11px;")

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def _refresh_accounts(self):
        self.account_list.clear()
        accounts = list_accounts()
        for acc in accounts:
            item = QListWidgetItem(f"✅  {acc['name']}")
            item.setData(Qt.ItemDataRole.UserRole, acc["name"])
            self.account_list.addItem(item)

        if accounts:
            self.account_list.setCurrentRow(0)
            self.lbl_account_status.setText(f"Conta ativa: {accounts[0]['name']}")
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

        # Description is OPTIONAL on TikTok
        caption = self.txt_caption.toPlainText().strip()
        title = self.txt_title.text().strip()

        # Build final description: title (if any) + caption (if any)
        if title and caption:
            final_description = f"{title}. {caption}"
        elif title:
            final_description = title
        else:
            final_description = caption  # may be empty — TikTok allows it

        hashtags = self.hashtag_bar.get_tags()
        browser = self.combo_browser.currentText()

        if self.radio_now.isChecked():
            self._start_upload(account_name, video, final_description, hashtags, browser)
        else:
            # Use TikTok-native scheduling (send to TikTok Studio with schedule time)
            self._start_scheduled_upload(account_name, video, final_description, hashtags, browser)

    # ------------------------------------------------------------------
    # Immediate upload
    # ------------------------------------------------------------------

    def _start_upload(self, account_name, video, description, hashtags, browser):
        self.btn_upload.setEnabled(False)
        self.lbl_progress.setText("🔄 Iniciando upload…")

        self.upload_thread = UploaderThread(
            account_name=account_name,
            video_path=video,
            description=description,
            hashtags=hashtags,
            browser=browser,
            headless=True,
            schedule_time=None,
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
    # TikTok-native scheduling (sends to TikTok Studio to be published)
    # ------------------------------------------------------------------

    def _start_scheduled_upload(self, account_name, video, description, hashtags, browser):
        """Upload the video to TikTok Studio with the native schedule date."""
        scheduled_dt = self.dt_picker.selected_datetime()

        # Validate: must be at least 15 minutes in the future (TikTok requirement)
        delta_s = (scheduled_dt - datetime.now()).total_seconds()
        if delta_s < 15 * 60:
            QMessageBox.warning(
                self,
                "Aviso",
                "O TikTok exige que o agendamento seja pelo menos 15 minutos no futuro!",
            )
            return

        # Format for tiktok_uploader: 'YYYY-MM-DD HH:MM:SS'
        schedule_str = scheduled_dt.strftime("%Y-%m-%d %H:%M:%S")

        self.btn_upload.setEnabled(False)
        self.lbl_progress.setText(f"⏰ Enviando e agendando para {scheduled_dt.strftime('%d/%m/%Y %H:%M')}…")

        self.upload_thread = UploaderThread(
            account_name=account_name,
            video_path=video,
            description=description,
            hashtags=hashtags,
            browser=browser,
            headless=True,
            schedule_time=schedule_str,
        )
        self.upload_thread.progress.connect(self.lbl_progress.setText)
        self.upload_thread.finished.connect(self._upload_done)
        self.upload_thread.start()

        # Also add to local queue display so user can track it
        timer = QTimer(self)   # dummy timer (won't fire, TikTok handles it)
        timer.setSingleShot(True)
        post = ScheduledPost(account_name, video, description, hashtags, browser, scheduled_dt, timer)
        self._scheduled_posts.append(post)
        self._refresh_queue_ui()

    # ------------------------------------------------------------------
    # Queue display helpers
    # ------------------------------------------------------------------

    def _cancel_selected(self):
        idx = self.queue_list.currentRow()
        if idx < 0 or idx >= len(self._scheduled_posts):
            return
        post = self._scheduled_posts[idx]
        post.timer.stop()
        self._scheduled_posts.pop(idx)
        self._refresh_queue_ui()
        self.lbl_progress.setText("🗑️ Entrada removida da fila.")

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
                item.setText(f"✅ Agendado no TikTok — [{post.account_name}] {name}")
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
