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
# AI Generator Thread
# ---------------------------------------------------------------------------
class AIGeneratorThread(QThread):
    finished = pyqtSignal(bool, str, list)  # success, text, tags

    def __init__(self, api_key: str, context: str, language: str = "Português"):
        super().__init__()
        self.api_key = api_key
        self.context = context
        self.language = language

    def run(self):
        import urllib.request
        import urllib.error
        import json

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={self.api_key}"
        
        prompt = f"""
Você é um especialista em redes sociais (TikTok, Reels, Shorts).
O usuário quer uma descrição e hashtags virais para um vídeo.
Contexto do vídeo: {self.context}

Por favor, escreva o conteúdo inteiramente no idioma: {self.language}.

Responda SOMENTE em JSON no seguinte formato (sem bloco markdown):
{{
  "description": "Texto chamativo, envolvente (com emojis). Não inclua as hashtags aqui.",
  "hashtags": ["tag1", "tag2", "tag3"]
}}
"""
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                result_raw = response.read()
                result = json.loads(result_raw)
                
                text_response = result["candidates"][0]["content"]["parts"][0]["text"]
                text_response = text_response.strip()
                
                if text_response.startswith("```json"):
                    text_response = text_response[7:]
                if text_response.startswith("```"):
                    text_response = text_response[3:]
                if text_response.endswith("```"):
                    text_response = text_response[:-3]
                    
                data_json = json.loads(text_response.strip())
                desc = data_json.get("description", "")
                tags = data_json.get("hashtags", [])
                
                self.finished.emit(True, desc, tags)
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
                # Try to parse it as JSON to get the actual message
                err_json = json.loads(error_body)
                if "error" in err_json and "message" in err_json["error"]:
                    msg = f"HTTP {e.code}: {err_json['error']['message']}"
                else:
                    msg = f"HTTP {e.code}: {error_body}"
            except:
                msg = str(e)
            
            # Se for 403 e a chave estiver incorreta ou sem permissões
            if e.code == 403:
                msg += "\n\nDica: Mude sua chave de API nas configurações ou verifique se você possui os acessos necessários na conta do Google. Caso a chave esteja errada, apague-a no config.json gerado na pasta src/config para que o programa peça novamente."
                
            self.finished.emit(False, msg, [])
        except Exception as e:
            self.finished.emit(False, str(e), [])

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
            "QTimeEdit::up-button { width: 24px; border-radius: 4px; border: 1px solid #334155; background: #1e293b; margin-bottom: 1px; }"
            "QTimeEdit::down-button { width: 24px; border-radius: 4px; border: 1px solid #334155; background: #1e293b; margin-top: 1px; }"
            "QTimeEdit::up-button:hover, QTimeEdit::down-button:hover { background: #3b82f6; }"
            "QTimeEdit::up-arrow { width: 12px; height: 12px; }"
            "QTimeEdit::down-arrow { width: 12px; height: 12px; }"
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

        # Favorite times row
        fav_row = QHBoxLayout()
        fav_row.setSpacing(6)
        lbl_fav = QLabel("Horários favoritos:")
        lbl_fav.setStyleSheet("color: #64748b; font-size: 11px;")
        fav_row.addWidget(lbl_fav)
        
        for t in ["09:00", "12:00", "15:00", "18:00", "20:00"]:
            btn = QPushButton(t)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 8px; padding: 2px 8px; font-size: 11px; }"
                "QPushButton:hover { background: #334155; color: #e2e8f0; }"
            )
            btn.clicked.connect(lambda checked, time=t: self._set_favorite_time(time))
            fav_row.addWidget(btn)
        fav_row.addStretch()
        layout.addLayout(fav_row)

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

    def _set_favorite_time(self, time_str: str):
        h, m = map(int, time_str.split(':'))
        self._time_edit.setTime(QTime(h, m))

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
        tasks: list[dict],
        browser: str,
        headless: bool = True,
    ):
        super().__init__()
        self.account_name = account_name
        self.tasks = tasks
        self.browser = browser
        self.headless = headless

    def run(self):
        uploader = TikTokUploader(self.account_name)
        try:
            self.progress.emit(f"🚀 Iniciando envio em lote (conta '{self.account_name}')…")

            ok = uploader.upload_batch(
                tasks=self.tasks,
                headless=self.headless,
                browser_name=self.browser,
            )
            if ok:
                self.finished.emit(True, "Todos os uploads concluídos com sucesso!")
            else:
                self.finished.emit(False, "Falha em um ou mais uploads. Verifique os cookies e os arquivos.")
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
        self._video_metadata: dict[str, dict] = {}
        self._current_video: str | None = None
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

    # Palette constants — single source of truth for the Apple-style theme
    _BG_CARD     = "#111827"      # card background (near-black, slightly blue)
    _BG_FIELD    = "#0D1520"      # input field background
    _BORDER      = "#1F2D3D"      # subtle card border
    _BORDER_FOCUS= "#3B82F6"      # blue focus ring
    _TEXT_PRI    = "#F0F4FF"      # primary text (near-white, cool tint)
    _TEXT_SEC    = "#64748B"      # secondary / hint text
    _TEXT_DIM    = "#374151"      # very dim (placeholders)
    _ACCENT      = "#3B82F6"      # TikTok-blue accent
    _PINK        = "#EC4899"      # TikTok-pink CTA

    def _card_style(self, radius: int = 18) -> str:
        """Return a QGroupBox stylesheet that looks like an Apple card."""
        return f"""
            QGroupBox {{
                background: {self._BG_CARD};
                border: 1px solid {self._BORDER};
                border-radius: {radius}px;
                margin-top: 10px;
                padding: 18px 20px 16px 20px;
                color: {self._TEXT_PRI};
                font-size: 13px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 16px;
                padding: 0 6px;
                color: {self._TEXT_PRI};
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.5px;
                background: {self._BG_CARD};
            }}
        """

    def _field_style(self, radius: int = 12) -> str:
        return (
            f"background: {self._BG_FIELD}; border: 1.5px solid {self._BORDER};"
            f" border-radius: {radius}px; color: {self._TEXT_PRI};"
            f" padding: 9px 14px; font-size: 13px; selection-background-color: {self._ACCENT};"
        )

    def _label_style(self, size: int = 12, bold: bool = True, color: str | None = None) -> str:
        c = color or self._TEXT_PRI
        w = "700" if bold else "400"
        return f"color: {c}; font-size: {size}px; font-weight: {w}; background: transparent;"

    def _btn_secondary_style(self) -> str:
        return f"""
            QPushButton {{
                background: {self._BG_FIELD};
                color: {self._TEXT_PRI};
                border: 1.5px solid {self._BORDER};
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {self._BORDER};
                border-color: {self._ACCENT};
                color: {self._ACCENT};
            }}
            QPushButton:pressed {{ background: #0D1520; }}
        """

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {self._BORDER}; background: {self._BORDER}; border: none; max-height: 1px;")
        return line

    def _init_ui(self):
        # ── Outer layout: scroll area so nothing gets squished ────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                width: 6px; background: transparent; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #1F2D3D; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        root = QVBoxLayout(container)
        root.setContentsMargins(16, 12, 16, 20)
        root.setSpacing(12)

        scroll.setWidget(container)
        outer.addWidget(scroll)

        # ── 1. Accounts card ──────────────────────────────────────────
        acc_group = QGroupBox("  👤  Contas TikTok")
        acc_group.setStyleSheet(self._card_style())
        acc_layout = QVBoxLayout(acc_group)
        acc_layout.setSpacing(10)
        acc_layout.setContentsMargins(0, 10, 0, 0)

        self.account_list = QListWidget()
        self.account_list.setFixedHeight(88)
        self.account_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.account_list.setStyleSheet(f"""
            QListWidget {{
                background: {self._BG_FIELD};
                border: 1.5px solid {self._BORDER};
                border-radius: 12px;
                color: {self._TEXT_PRI};
                font-size: 13px;
                padding: 4px 8px;
                outline: 0;
            }}
            QListWidget::item {{ padding: 6px 8px; border-radius: 8px; }}
            QListWidget::item:selected {{
                background: {self._ACCENT};
                color: white;
            }}
            QListWidget::item:hover:!selected {{ background: {self._BORDER}; }}
        """)
        acc_layout.addWidget(self.account_list)

        acc_btn_row = QHBoxLayout()
        acc_btn_row.setSpacing(8)
        self.btn_add_account = QPushButton("  ＋  Adicionar Conta")
        self.btn_add_account.setStyleSheet(f"""
            QPushButton {{
                background: {self._ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 9px 16px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: #2563EB; }}
            QPushButton:pressed {{ background: #1D4ED8; }}
            QPushButton:disabled {{ background: #1F2D3D; color: {self._TEXT_SEC}; }}
        """)
        self.btn_add_account.clicked.connect(self._on_add_account)

        self.btn_remove_account = QPushButton("  🗑  Remover")
        self.btn_remove_account.setStyleSheet(self._btn_secondary_style())
        self.btn_remove_account.clicked.connect(self._on_remove_account)

        acc_btn_row.addWidget(self.btn_add_account)
        acc_btn_row.addWidget(self.btn_remove_account)
        acc_btn_row.addStretch()
        acc_layout.addLayout(acc_btn_row)

        self.lbl_account_status = QLabel("Selecione uma conta na lista acima.")
        self.lbl_account_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_account_status.setStyleSheet(
            self._label_style(11, bold=False, color=self._TEXT_SEC)
        )
        acc_layout.addWidget(self.lbl_account_status)
        root.addWidget(acc_group)

        # ── 2. Browser + Files  (side by side row) ────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        # Browser mini-card
        browser_card = QGroupBox("  🌐  Navegador")
        browser_card.setStyleSheet(self._card_style())
        browser_inner = QVBoxLayout(browser_card)
        browser_inner.setSpacing(8)
        browser_inner.setContentsMargins(0, 10, 0, 0)

        lbl_br = QLabel("Automação via:")
        lbl_br.setStyleSheet(self._label_style(11, bold=False, color=self._TEXT_SEC))
        browser_inner.addWidget(lbl_br)

        self.combo_browser = QComboBox()
        self.combo_browser.addItems(["chrome", "brave", "firefox", "edge"])
        self.combo_browser.setStyleSheet(f"""
            QComboBox {{
                background: {self._BG_FIELD};
                border: 1.5px solid {self._BORDER};
                border-radius: 10px;
                color: {self._TEXT_PRI};
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 600;
            }}
            QComboBox:hover {{ border-color: {self._ACCENT}; }}
            QComboBox::drop-down {{
                border: none; width: 28px;
                subcontrol-origin: padding;
                subcontrol-position: right center;
            }}
            QComboBox QAbstractItemView {{
                background: {self._BG_CARD};
                border: 1px solid {self._BORDER};
                color: {self._TEXT_PRI};
                selection-background-color: {self._ACCENT};
                border-radius: 10px;
            }}
        """)
        browser_inner.addWidget(self.combo_browser)
        browser_inner.addStretch()
        row2.addWidget(browser_card, 1)

        # Files mini-card
        files_card = QGroupBox("  🎬  Vídeos")
        files_card.setStyleSheet(self._card_style())
        files_inner = QVBoxLayout(files_card)
        files_inner.setSpacing(8)
        files_inner.setContentsMargins(0, 10, 0, 0)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setFixedHeight(82)
        self.file_list.setStyleSheet(f"""
            QListWidget {{
                background: {self._BG_FIELD};
                border: 1.5px solid {self._BORDER};
                border-radius: 10px;
                color: {self._TEXT_PRI};
                font-size: 12px;
                padding: 4px 6px;
                outline: 0;
            }}
            QListWidget::item {{ padding: 4px 6px; border-radius: 6px; }}
            QListWidget::item:selected {{ background: {self._ACCENT}; color: white; }}
        """)
        files_inner.addWidget(self.file_list)

        file_btn_row = QHBoxLayout()
        file_btn_row.setSpacing(6)
        btn_add_file = QPushButton("＋ Adicionar")
        btn_add_file.setStyleSheet(f"""
            QPushButton {{
                background: {self._ACCENT};
                color: white; border: none;
                border-radius: 8px;
                padding: 7px 10px;
                font-size: 11px; font-weight: 700;
            }}
            QPushButton:hover {{ background: #2563EB; }}
        """)
        btn_add_file.clicked.connect(self._browse_files)

        btn_remove_file = QPushButton("Remover")
        btn_remove_file.setStyleSheet(self._btn_secondary_style())
        btn_remove_file.clicked.connect(self._remove_selected_files)

        btn_clear_files = QPushButton("Limpar")
        btn_clear_files.setStyleSheet(self._btn_secondary_style())
        btn_clear_files.clicked.connect(self._clear_files)

        file_btn_row.addWidget(btn_add_file)
        file_btn_row.addWidget(btn_remove_file)
        file_btn_row.addWidget(btn_clear_files)
        files_inner.addLayout(file_btn_row)
        row2.addWidget(files_card, 2)

        root.addLayout(row2)

        # ── 3. Video details card ─────────────────────────────────────
        meta_card = QGroupBox("  📝  Detalhes do Vídeo")
        meta_card.setStyleSheet(self._card_style())
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setSpacing(14)
        meta_layout.setContentsMargins(0, 12, 0, 0)

        # Description field
        lbl_desc_row = QHBoxLayout()
        lbl_desc = QLabel("Descrição")
        lbl_desc.setStyleSheet(self._label_style(12))
        lbl_opt_desc = QLabel("opcional")
        lbl_opt_desc.setStyleSheet(
            f"color: {self._TEXT_SEC}; font-size: 10px; font-weight: 500;"
            f" background: {self._BORDER}; border-radius: 4px; padding: 1px 6px;"
        )
        lbl_desc_row.addWidget(lbl_desc)
        lbl_desc_row.addSpacing(6)
        lbl_desc_row.addWidget(lbl_opt_desc)
        lbl_desc_row.addStretch()
        
        self.combo_ai_lang = QComboBox()
        self.combo_ai_lang.addItems(["Português", "English", "Español", "Deutsch", "Français", "Italiano", "Русский", "中文"])
        self.combo_ai_lang.setStyleSheet(f"""
            QComboBox {{
                background: transparent; border: 1px solid {self._BORDER}; border-radius: 6px;
                color: {self._TEXT_SEC}; font-size: 11px; padding: 3px 6px;
            }}
            QComboBox::drop-down {{ width: 20px; border: none; }}
            QComboBox QAbstractItemView {{
                background: {self._BG_CARD}; color: {self._TEXT_PRI}; selection-background-color: {self._ACCENT};
            }}
        """)
        lbl_desc_row.addWidget(self.combo_ai_lang)
        
        self.btn_ai_desc = QPushButton("✨ Criar com IA")
        self.btn_ai_desc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_desc.setStyleSheet(f"""
            QPushButton {{
                background: rgba(139, 92, 246, 0.2);
                color: #C4B5FD;
                border: 1px solid #8B5CF6;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: #8B5CF6;
                color: white;
            }}
        """)
        self.btn_ai_desc.clicked.connect(self._generate_ai_desc)
        lbl_desc_row.addWidget(self.btn_ai_desc)

        self.btn_change_api_key = QPushButton("🔑")
        self.btn_change_api_key.setToolTip("Alterar API Key do Gemini")
        self.btn_change_api_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_api_key.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {self._TEXT_SEC};
                border: 1px solid {self._BORDER};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {self._BORDER};
                color: {self._TEXT_PRI};
            }}
        """)
        self.btn_change_api_key.clicked.connect(self._change_api_key)
        lbl_desc_row.addWidget(self.btn_change_api_key)

        self._char_counter = QLabel("0 / 4000")
        self._char_counter.setStyleSheet(self._label_style(10, bold=False, color=self._TEXT_SEC))
        lbl_desc_row.addWidget(self._char_counter)
        meta_layout.addLayout(lbl_desc_row)

        self.txt_caption = QTextEdit()
        self.txt_caption.setPlaceholderText("Texto que aparece abaixo do vídeo (opcional)…")
        self.txt_caption.setFixedHeight(88)
        self.txt_caption.setStyleSheet(
            f"QTextEdit {{ {self._field_style(12)} }}"
            f"QTextEdit:focus {{ border-color: {self._BORDER_FOCUS}; }}"
        )
        self.txt_caption.textChanged.connect(self._on_caption_changed)
        meta_layout.addWidget(self.txt_caption)

        meta_layout.addWidget(self._divider())

        # Hashtags
        lbl_ht = QLabel("# Hashtags")
        lbl_ht.setStyleSheet(self._label_style(12))
        meta_layout.addWidget(lbl_ht)

        self.hashtag_bar = HashtagBar()
        meta_layout.addWidget(self.hashtag_bar)

        root.addWidget(meta_card)

        # ── 4. Schedule card ──────────────────────────────────────────
        sched_card = QGroupBox("  ⏰  Quando Publicar")
        sched_card.setStyleSheet(self._card_style())
        sched_layout = QVBoxLayout(sched_card)
        sched_layout.setSpacing(10)
        sched_layout.setContentsMargins(0, 12, 0, 0)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)

        # Use QPushButton (checkable) instead of QRadioButton so the native
        # indicator dot never renders — the emoji stays perfectly centred.
        _pill_btn_base = f"""
            QPushButton {{
                font-size: 13px;
                font-weight: 600;
                padding: 9px 22px;
                border-radius: 10px;
                border: none;
                text-align: center;
            }}
            QPushButton:checked {{
                background: {self._ACCENT};
                color: white;
            }}
            QPushButton:!checked {{
                background: transparent;
                color: {self._TEXT_SEC};
            }}
            QPushButton:!checked:hover {{
                background: {self._BORDER};
                color: {self._TEXT_PRI};
            }}
        """

        self.radio_now = QPushButton("🟢  Agora")
        self.radio_now.setCheckable(True)
        self.radio_now.setChecked(True)
        self.radio_now.setStyleSheet(_pill_btn_base)
        self.radio_now.setCursor(Qt.CursorShape.PointingHandCursor)

        self.radio_later = QPushButton("📅  Programar")
        self.radio_later.setCheckable(True)
        self.radio_later.setChecked(False)
        self.radio_later.setStyleSheet(_pill_btn_base)
        self.radio_later.setCursor(Qt.CursorShape.PointingHandCursor)

        # Mutual exclusion via QButtonGroup
        mode_grp = QButtonGroup(self)
        mode_grp.setExclusive(True)
        mode_grp.addButton(self.radio_now)
        mode_grp.addButton(self.radio_later)

        pill_frame = QFrame()
        pill_frame.setStyleSheet(
            f"background: {self._BG_FIELD}; border-radius: 12px; border: 1.5px solid {self._BORDER};"
        )
        pill_row = QHBoxLayout(pill_frame)
        pill_row.setContentsMargins(4, 4, 4, 4)
        pill_row.setSpacing(4)
        pill_row.addWidget(self.radio_now)
        pill_row.addWidget(self.radio_later)
        toggle_row.addWidget(pill_frame)
        toggle_row.addStretch()
        sched_layout.addLayout(toggle_row)

        self.dt_picker = InlineDateTimePicker()
        self.dt_picker.setVisible(False)
        
        self.interval_widget = QWidget()
        interval_layout = QHBoxLayout(self.interval_widget)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        lbl_interval = QLabel("Intervalo entre posts (minutos):")
        lbl_interval.setStyleSheet(self._label_style(12))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(15, 1440)
        self.spin_interval.setValue(60)
        self.spin_interval.setStyleSheet(self._field_style(10))
        interval_layout.addWidget(lbl_interval)
        interval_layout.addWidget(self.spin_interval)
        interval_layout.addStretch()
        self.interval_widget.setVisible(False)

        # radio_now/later are now QPushButtons — use clicked instead of toggled
        self.radio_now.clicked.connect(lambda: self.dt_picker.setVisible(False))
        self.radio_now.clicked.connect(lambda: self.interval_widget.setVisible(False))
        self.radio_later.clicked.connect(lambda: self.dt_picker.setVisible(True))
        self.radio_later.clicked.connect(lambda: self.interval_widget.setVisible(True))
        sched_layout.addWidget(self.dt_picker)
        sched_layout.addWidget(self.interval_widget)
        root.addWidget(sched_card)

        # ── 5. Queue card (hidden until scheduled posts exist) ────────
        self.queue_group = QGroupBox("  📋  Fila de Agendamentos")
        self.queue_group.setStyleSheet(self._card_style())
        queue_layout = QVBoxLayout(self.queue_group)
        queue_layout.setSpacing(8)
        queue_layout.setContentsMargins(0, 10, 0, 0)

        self.queue_list = QListWidget()
        self.queue_list.setFixedHeight(80)
        self.queue_list.setStyleSheet(f"""
            QListWidget {{
                background: {self._BG_FIELD}; border: 1.5px solid {self._BORDER};
                border-radius: 10px; color: {self._TEXT_PRI};
                font-size: 12px; padding: 4px 8px; outline: 0;
            }}
            QListWidget::item {{ padding: 5px 6px; border-radius: 6px; }}
            QListWidget::item:selected {{ background: {self._ACCENT}; color: white; }}
        """)
        queue_layout.addWidget(self.queue_list)

        btn_cancel = QPushButton("Cancelar Selecionado")
        btn_cancel.setStyleSheet(self._btn_secondary_style())
        btn_cancel.clicked.connect(self._cancel_selected)
        queue_layout.addWidget(btn_cancel)

        self.queue_group.setVisible(False)
        root.addWidget(self.queue_group)

        # ── 6. CTA Upload button ──────────────────────────────────────
        self.btn_upload = QPushButton("🚀  Enviar para TikTok")
        self.btn_upload.setMinimumHeight(54)
        self.btn_upload.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_upload.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
                font-weight: 800;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #EC4899, stop:1 #8B5CF6
                );
                color: white;
                border: none;
                border-radius: 16px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #DB2777, stop:1 #7C3AED
                );
            }}
            QPushButton:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #BE185D, stop:1 #6D28D9
                );
            }}
            QPushButton:disabled {{
                background: {self._BORDER};
                color: {self._TEXT_SEC};
            }}
        """)
        self.btn_upload.clicked.connect(self._handle_action)
        root.addWidget(self.btn_upload)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_progress.setWordWrap(True)
        self.lbl_progress.setStyleSheet(self._label_style(12, bold=False, color=self._TEXT_SEC))
        root.addWidget(self.lbl_progress)

        root.addStretch()
        
        # Connect signals for per-video metadata
        self.file_list.currentItemChanged.connect(self._on_file_selected)
        self.txt_caption.textChanged.connect(self._on_meta_edited)
        self._update_meta_fields()

    # ------------------------------------------------------------------
    # Per-video metadata helpers
    # ------------------------------------------------------------------

    def _on_file_selected(self, current, previous):
        if current:
            self._current_video = current.text()
        else:
            self._current_video = None
        self._update_meta_fields()

    def _update_meta_fields(self):
        if not self._current_video:
            self.txt_caption.blockSignals(True)
            self.txt_caption.clear()
            self.txt_caption.setEnabled(False)
            self.txt_caption.blockSignals(False)
            return

        self.txt_caption.setEnabled(True)
        data = self._video_metadata.get(self._current_video, {"caption": ""})
        self.txt_caption.blockSignals(True)
        self.txt_caption.setPlainText(data.get("caption", ""))
        self.txt_caption.blockSignals(False)
        self._on_caption_changed()

    def _on_meta_edited(self):
        if self._current_video and self._current_video in self._video_metadata:
            self._video_metadata[self._current_video]["caption"] = self.txt_caption.toPlainText()

    def _change_api_key(self):
        try:
            from config.settings import settings
        except Exception:
            return
            
        current_key = getattr(settings, 'gemini_api_key', '')
        api_key, ok = QInputDialog.getText(
            self, "Alterar API Key do Gemini",
            "Insira sua nova chave de API do Google Gemini:\n(Se for inválida ou vazia, pediremos novamente no uso)",
            QLineEdit.EchoMode.Password,
            text=current_key
        )
        if ok:
            settings.gemini_api_key = api_key.strip()
            settings.save_config()
            QMessageBox.information(self, "Sucesso", "API Key salva com sucesso!")

    def _generate_ai_desc(self):
        if not self._current_video:
            QMessageBox.warning(self, "Aviso", "Selecione um vídeo na lista primeiro.")
            return

        try:
            from config.settings import settings
        except Exception:
            QMessageBox.warning(self, "Erro", "Erro ao carregar as configurações do sistema.")
            return
            
        if not hasattr(settings, 'gemini_api_key') or not settings.gemini_api_key:
            api_key, ok = QInputDialog.getText(
                self, "API Key do Gemini",
                "Para usar a IA, insira sua chave de API grátis do Google Gemini:\n(Ela será salva localmente)",
                QLineEdit.EchoMode.Password
            )
            if ok and api_key.strip():
                settings.gemini_api_key = api_key.strip()
                settings.save_config()
            else:
                return

        context, ok = QInputDialog.getText(
            self, "Contexto do Vídeo (IA)",
            "Diga brevemente sobre o que é o vídeo para a IA escrever a legenda\n(Ex: '10 dicas de marketing'): ",
        )
        if not ok or not context.strip():
            return

        self.btn_ai_desc.setEnabled(False)
        self.btn_ai_desc.setText("⏳ Gerando...")

        lang = self.combo_ai_lang.currentText()
        self._ai_thread = AIGeneratorThread(settings.gemini_api_key, context.strip(), language=lang)
        self._ai_thread.finished.connect(self._on_ai_desc_ready)
        self._ai_thread.start()

    def _on_ai_desc_ready(self, success, text, tags):
        self.btn_ai_desc.setEnabled(True)
        self.btn_ai_desc.setText("✨ Criar com IA")
        
        if not success:
            QMessageBox.critical(self, "Erro", f"Tivemos um problema com a resposta do Gemini:\n{text}")
            return

        self.txt_caption.setPlainText(text)
        
        if tags:
            self.hashtag_bar.clear()
            for t in tags:
                if not t.startswith("#"):
                    t = "#" + t
                self.hashtag_bar._add_tag(t)

    # ------------------------------------------------------------------
    # Caption char counter
    # ------------------------------------------------------------------

    def _on_caption_changed(self):
        n = len(self.txt_caption.toPlainText())
        self._char_counter.setText(f"{n} / 4000")
        if n > 4000:
            self._char_counter.setStyleSheet(f"color: #EF4444; font-size: 10px; font-weight: 400; background: transparent;")
        else:
            self._char_counter.setStyleSheet(self._label_style(10, bold=False, color=self._TEXT_SEC))

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
            for f in filenames:
                if f not in self._video_metadata:
                    self._video_metadata[f] = {"caption": ""}
            self.file_list.addItems(filenames)

    def _remove_selected_files(self):
        for item in self.file_list.selectedItems():
            text = item.text()
            if text in self._video_metadata:
                del self._video_metadata[text]
            self.file_list.takeItem(self.file_list.row(item))
        if self.file_list.count() == 0:
            self._current_video = None
            self._update_meta_fields()

    def _clear_files(self):
        self.file_list.clear()
        self._video_metadata.clear()
        self._current_video = None
        self._update_meta_fields()

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

        for video in files:
            if not Path(video).exists():
                QMessageBox.warning(self, "Erro", f"Arquivo de vídeo não encontrado: {video}")
                return

        hashtags = self.hashtag_bar.get_tags()
        browser = self.combo_browser.currentText()

        if self.radio_now.isChecked():
            self._start_batch_upload(account_name, files, hashtags, browser, scheduled=False)
        else:
            self._start_batch_upload(account_name, files, hashtags, browser, scheduled=True)

    # ------------------------------------------------------------------
    # Batch Upload
    # ------------------------------------------------------------------

    def _start_batch_upload(self, account_name, files, hashtags, browser, scheduled=False):
        tasks = []
        
        if scheduled:
            base_dt = self.dt_picker.selected_datetime()
            interval_min = self.spin_interval.value()

            # TikTok requirement validation for the very first video
            delta_s = (base_dt - datetime.now()).total_seconds()
            if delta_s < 15 * 60:
                QMessageBox.warning(
                    self,
                    "Aviso",
                    "O TikTok exige que o agendamento seja pelo menos 15 minutos no futuro!",
                )
                return

        for i, video in enumerate(files):
            data = self._video_metadata.get(video, {"caption": ""})
            caption = data.get("caption", "").strip()

            task = {
                "path": video,
                "title": caption,
                "hashtags": hashtags,
            }
            if scheduled:
                # Add interval for each subsequent video
                dt = base_dt + timedelta(minutes=interval_min * i)
                task["schedule_time"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                task["_raw_dt"] = dt # to populate local queue tracking
            else:
                task["schedule_time"] = None
                
            tasks.append(task)

        self.btn_upload.setEnabled(False)
        self.lbl_progress.setText(f"🚀 Iniciando upload de {len(tasks)} vídeo(s) com conta '{account_name}'…")

        self.upload_thread = UploaderThread(
            account_name=account_name,
            tasks=tasks,
            browser=browser,
            headless=True,
        )
        self.upload_thread.progress.connect(self.lbl_progress.setText)
        self.upload_thread.finished.connect(self._upload_done)
        self.upload_thread.start()

        if scheduled:
            # Add to local queue display
            for t in tasks:
                timer = QTimer(self)
                timer.setSingleShot(True)
                post = ScheduledPost(account_name, t["path"], t["title"], hashtags, browser, t["_raw_dt"], timer)
                self._scheduled_posts.append(post)
            self._refresh_queue_ui()

    def _upload_done(self, success: bool, msg: str):
        self.btn_upload.setEnabled(True)
        if success:
            QMessageBox.information(self, "Sucesso", msg)
            self.lbl_progress.setText("✅ Processo concluído!")
        else:
            QMessageBox.critical(self, "Erro", msg)
            self.lbl_progress.setText("❌ Falha no processo")

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
        if path not in self._video_metadata:
            self._video_metadata[path] = {"caption": ""}
        self.file_list.addItem(str(path))
