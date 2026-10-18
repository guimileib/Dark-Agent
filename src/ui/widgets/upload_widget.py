"""
UploadWidget — multiple TikTok accounts, multi-browser, post-now / scheduled.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QDate, QThread, QTimer, pyqtSignal, QSize,
)
from PyQt6.QtGui import QBrush, QColor, QFont, QTextCharFormat, QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCalendarWidget, QComboBox,
    QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QRadioButton, QScrollArea, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget, QSpinBox, QTimeEdit,
    QDateEdit, QSplitter, QToolButton, QCheckBox,
)
from PyQt6.QtCore import QTime

from core.uploader import (
    TikTokUploader,
    add_account,
    list_accounts,
    remove_account,
)

logger = logging.getLogger(__name__)

# TikTok caption character limit (may vary by region)
TIKTOK_CAPTION_LIMIT = 4000

# Janela aceita pelo agendador do TikTok (tiktok-uploader descarta fora disso)
SCHEDULE_MIN_LEAD = timedelta(minutes=20)
SCHEDULE_MAX_AHEAD = timedelta(days=10)


def build_daily_schedule(
    n: int, times: list[str], start_date: date, now: datetime | None = None
) -> list[datetime]:
    """Distribui n vídeos nos horários diários ('HH:MM'), dia após dia, a partir de start_date.

    Horários a menos de 20 min de agora são pulados (TikTok rejeitaria).
    """
    now = now or datetime.now()
    clock = sorted({tuple(map(int, t.split(":"))) for t in times})
    if n <= 0 or not clock:
        return []
    slots: list[datetime] = []
    day = start_date
    while len(slots) < n:
        for h, m in clock:
            dt = datetime(day.year, day.month, day.day, h, m)
            if dt - now >= SCHEDULE_MIN_LEAD:
                slots.append(dt)
                if len(slots) == n:
                    break
        day += timedelta(days=1)
    return slots


# ---------------------------------------------------------------------------
# AI Generator Thread
# ---------------------------------------------------------------------------
# 2.0-flash foi desligado em 06/2026; o alias "latest" é fallback se o 1º também sair do ar.
_GEMINI_MODELS = ("gemini-3.8-flash", "gemini-flash-latest")


# Teto de vídeos por request: lotes maiores são divididos (limite de tokens de saída).
_GEMINI_BATCH_SIZE = 20


@dataclass
class CaptionResult:
    """Descrição + hashtags (sem '#') geradas para um vídeo."""
    description: str
    hashtags: list[str] = field(default_factory=list)


# Structured output: o Gemini devolve JSON validado contra este schema.
_CAPTIONS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "videos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER"},
                    "description": {"type": "STRING"},
                    "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["id", "description", "hashtags"],
            },
        },
    },
    "required": ["videos"],
}


def _gemini_request(api_key: str, body: dict) -> dict:
    """POST no generateContent, caindo para o próximo modelo em 404. Retorna o JSON da resposta."""
    import json
    import urllib.error
    import urllib.request

    for i, model in enumerate(_GEMINI_MODELS):
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
        )
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            # 404 = modelo desligado/inexistente: tenta o próximo
            if e.code != 404 or i == len(_GEMINI_MODELS) - 1:
                raise
            logger.warning(f"Gemini model '{model}' indisponível (404), tentando o próximo.")
    raise RuntimeError("Nenhum modelo Gemini disponível.")


def _gemini_captions_batch(
    api_key: str, contexts: list[str], language: str
) -> dict[int, CaptionResult]:
    """Gera descrição + hashtags de N vídeos num único request.

    Retorna {índice em contexts: CaptionResult}; índices ausentes = a IA pulou o vídeo.
    """
    import json

    videos_txt = "\n".join(f"- id {i}: {ctx}" for i, ctx in enumerate(contexts))
    prompt = f"""
Você é um especialista em redes sociais (TikTok, Reels, Shorts).
Escreva uma descrição e hashtags virais para CADA um dos {len(contexts)} vídeos abaixo.
Cada vídeo deve ter texto próprio, sem repetir a mesma descrição entre vídeos.

Vídeos (id: contexto):
{videos_txt}

Regras:
- Idioma: {language}.
- "description": texto chamativo, envolvente (com emojis), sem hashtags.
- "hashtags": 3 a 8 hashtags relevantes, sem o caractere '#'.
- Devolva exatamente um item por id recebido, usando o mesmo id.
"""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _CAPTIONS_SCHEMA,
        },
    }
    result = _gemini_request(api_key, body)

    text_response = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    # Defensivo: alguns modelos ainda embrulham em ```json mesmo com responseMimeType
    text_response = re.sub(r"^```(?:json)?\s*|\s*```$", "", text_response)

    captions: dict[int, CaptionResult] = {}
    for v in json.loads(text_response).get("videos", []):
        idx = v.get("id")
        if isinstance(idx, int) and 0 <= idx < len(contexts) and idx not in captions:
            captions[idx] = CaptionResult(
                description=str(v.get("description", "")).strip(),
                hashtags=[str(t).strip().lstrip("#") for t in v.get("hashtags", []) if str(t).strip()],
            )
    return captions


def _http_error_message(e) -> str:
    """Extrai a mensagem útil de um HTTPError do Gemini (com dica no 403)."""
    import json

    try:
        error_body = e.read().decode("utf-8")
        # Try to parse it as JSON to get the actual message
        err_json = json.loads(error_body)
        if "error" in err_json and "message" in err_json["error"]:
            msg = f"HTTP {e.code}: {err_json['error']['message']}"
        else:
            msg = f"HTTP {e.code}: {error_body}"
    except Exception:
        msg = str(e)

    # Se for 403 e a chave estiver incorreta ou sem permissões
    if e.code == 403:
        from config.paths import get_user_config_file
        config_path = get_user_config_file()
        msg += f"\n\nDica: Mude sua chave de API nas configurações ou verifique se você possui os acessos necessários na conta do Google. Caso a chave esteja errada, apague-a no {config_path} para que o programa peça novamente."
    return msg


class AIGeneratorThread(QThread):
    """Gera descrição + hashtags para (path, contexto): um request por lote de vídeos."""
    item_done = pyqtSignal(str, str, list)   # path, description, tags
    item_failed = pyqtSignal(str, str)       # path, error message
    progress = pyqtSignal(int, int)          # done, total

    def __init__(self, api_key: str, items: list[tuple[str, str]], language: str = "Português"):
        super().__init__()
        self.api_key = api_key
        self.items = items
        self.language = language

    def run(self):
        import urllib.error

        total = len(self.items)
        for start in range(0, total, _GEMINI_BATCH_SIZE):
            if self.isInterruptionRequested():
                return
            chunk = self.items[start:start + _GEMINI_BATCH_SIZE]
            try:
                captions = _gemini_captions_batch(
                    self.api_key, [ctx for _, ctx in chunk], self.language
                )
            except urllib.error.HTTPError as e:
                msg = _http_error_message(e)
                for path, _ in chunk:
                    self.item_failed.emit(path, msg)
                if e.code in (401, 403):
                    return  # chave inválida: não adianta tentar os próximos
                continue
            except Exception as e:
                for path, _ in chunk:
                    self.item_failed.emit(path, str(e))
                continue

            for i, (path, _) in enumerate(chunk):
                cap = captions.get(i)
                if cap is None:
                    self.item_failed.emit(path, "A IA não retornou legenda para este vídeo.")
                else:
                    self.item_done.emit(path, cap.description, cap.hashtags)
            self.progress.emit(min(start + len(chunk), total), total)

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
    """Seletor de data e hora com cards e horários rápidos."""
    changed = pyqtSignal()  # só em edição pelo usuário (não em set_datetime)

    def __init__(self, parent=None):
        super().__init__(parent)
        now = datetime.now()
        default = now + timedelta(hours=1)
        rem = default.minute % 5
        if rem:
            default = default + timedelta(minutes=5 - rem)
        default = default.replace(second=0, microsecond=0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        # ── Row: time + date cards side by side ──────────────────────
        row = QHBoxLayout()
        row.setSpacing(14)

        # ── Time card ────────────────────────────────────────────────
        time_frame = QFrame()
        time_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 41, 59, 0.9), stop:1 rgba(15, 23, 42, 0.9));
                border: 1.5px solid rgba(59, 130, 246, 0.25);
                border-radius: 14px;
            }
        """)
        time_card = QVBoxLayout(time_frame)
        time_card.setContentsMargins(16, 12, 16, 12)
        time_card.setSpacing(6)

        lbl_t = QLabel("HORA")
        lbl_t.setStyleSheet(
            "color: #60a5fa; font-size: 10px; font-weight: 800;"
            " letter-spacing: 1.5px; background: transparent; border: none;"
        )
        time_card.addWidget(lbl_t)

        self._time_edit = QTimeEdit()
        self._time_edit.setTime(QTime(default.hour, default.minute))
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setStyleSheet("""
            QTimeEdit {
                background: transparent; border: none; color: #f0f4ff;
                font-size: 28px; font-weight: 800; font-family: 'Segoe UI', sans-serif;
            }
            QTimeEdit::up-button {
                width: 22px; border-radius: 5px;
                border: 1px solid rgba(59, 130, 246, 0.2);
                background: rgba(30, 41, 59, 0.6); margin-bottom: 1px;
            }
            QTimeEdit::down-button {
                width: 22px; border-radius: 5px;
                border: 1px solid rgba(59, 130, 246, 0.2);
                background: rgba(30, 41, 59, 0.6); margin-top: 1px;
            }
            QTimeEdit::up-button:hover, QTimeEdit::down-button:hover {
                background: rgba(59, 130, 246, 0.4);
                border-color: #3b82f6;
            }
        """)
        time_card.addWidget(self._time_edit)
        row.addWidget(time_frame)

        # ── Date card ────────────────────────────────────────────────
        date_frame = QFrame()
        date_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 41, 59, 0.9), stop:1 rgba(15, 23, 42, 0.9));
                border: 1.5px solid rgba(139, 92, 246, 0.25);
                border-radius: 14px;
            }
        """)
        date_card = QVBoxLayout(date_frame)
        date_card.setContentsMargins(16, 12, 16, 12)
        date_card.setSpacing(6)

        lbl_d = QLabel("DATA")
        lbl_d.setStyleSheet(
            "color: #a78bfa; font-size: 10px; font-weight: 800;"
            " letter-spacing: 1.5px; background: transparent; border: none;"
        )
        date_card.addWidget(lbl_d)

        self._date_edit = QDateEdit()
        self._date_edit.setDate(QDate(default.year, default.month, default.day))
        self._date_edit.setDisplayFormat("dd/MM/yyyy")
        self._date_edit.setMinimumDate(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setStyleSheet("""
            QDateEdit {
                background: transparent; border: none; color: #f0f4ff;
                font-size: 22px; font-weight: 800; font-family: 'Segoe UI', sans-serif;
            }
            QDateEdit::up-button {
                width: 20px; border-radius: 5px;
                border: 1px solid rgba(139, 92, 246, 0.2);
                background: rgba(30, 41, 59, 0.6);
            }
            QDateEdit::down-button {
                width: 20px; border-radius: 5px;
                border: 1px solid rgba(139, 92, 246, 0.2);
                background: rgba(30, 41, 59, 0.6);
            }
            QDateEdit::up-button:hover, QDateEdit::down-button:hover {
                background: rgba(139, 92, 246, 0.4);
                border-color: #8b5cf6;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding; subcontrol-position: right center;
                width: 22px; border: none;
            }
        """)
        self._style_calendar_popup(self._date_edit.calendarWidget())
        date_card.addWidget(self._date_edit)
        row.addWidget(date_frame)
        row.addStretch()

        layout.addLayout(row)

        # ── Favorite times row — pill buttons + pencil editor ────────
        self._shortcut_times: list[str] = ["15:00", "19:00", "23:00"]

        self._fav_row_container = QWidget()
        self._fav_row = QHBoxLayout(self._fav_row_container)
        self._fav_row.setContentsMargins(0, 0, 0, 0)
        self._fav_row.setSpacing(6)
        self._build_favorites_row()
        layout.addWidget(self._fav_row_container)

        # ── Summary label ────────────────────────────────────────────
        summary_frame = QFrame()
        summary_frame.setStyleSheet("""
            QFrame {
                background: rgba(59, 130, 246, 0.08);
                border: 1px solid rgba(59, 130, 246, 0.15);
                border-radius: 10px;
            }
        """)
        summary_inner = QHBoxLayout(summary_frame)
        summary_inner.setContentsMargins(14, 8, 14, 8)

        self._lbl_summary = QLabel()
        self._lbl_summary.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._lbl_summary.setStyleSheet(
            "color: #93c5fd; font-size: 12px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        summary_inner.addWidget(self._lbl_summary)
        layout.addWidget(summary_frame)

        self._update_summary()

        self._time_edit.timeChanged.connect(lambda _: self._on_edited())
        self._date_edit.dateChanged.connect(lambda _: self._on_edited())

    def _on_edited(self):
        self._update_summary()
        self.changed.emit()

    def set_datetime(self, dt: datetime | None):
        """Mostra dt sem emitir `changed`; None = vídeo ainda sem horário."""
        if dt is not None:
            for w in (self._time_edit, self._date_edit):
                w.blockSignals(True)
            self._date_edit.setDate(QDate(dt.year, dt.month, dt.day))
            self._time_edit.setTime(QTime(dt.hour, dt.minute))
            for w in (self._time_edit, self._date_edit):
                w.blockSignals(False)
            self._update_summary()
        else:
            self._lbl_summary.setText(
                "⚠ Este vídeo ainda não tem horário — ajuste acima ou use o Padrão diário."
            )

    def shortcut_times(self) -> list[str]:
        return list(self._shortcut_times)

    def set_shortcut_times(self, times: list[str]):
        self._shortcut_times = sorted(times)
        self._build_favorites_row()

    def _update_summary(self):
        dt = self.selected_datetime()
        self._lbl_summary.setText(
            f"Agendado para: {dt.strftime('%A, %d/%m/%Y')}  \u2022  {dt.strftime('%H:%M')}"
        )

    def _set_favorite_time(self, time_str: str):
        h, m = map(int, time_str.split(':'))
        self._time_edit.setTime(QTime(h, m))

    # ── Shortcut chips + editor ──────────────────────────────────────
    _FAV_BTN_STYLE = """
        QPushButton {
            background: rgba(30, 41, 59, 0.5);
            color: #94a3b8;
            border: 1px solid rgba(51, 65, 85, 0.5);
            border-radius: 14px;
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: rgba(59, 130, 246, 0.15);
            color: #e2e8f0;
            border-color: rgba(59, 130, 246, 0.4);
        }
        QPushButton:pressed {
            background: rgba(59, 130, 246, 0.3);
            color: #ffffff;
        }
    """

    _PENCIL_BTN_STYLE = """
        QPushButton {
            background: transparent;
            color: #64748b;
            border: 1px solid rgba(51, 65, 85, 0.5);
            border-radius: 14px;
            padding: 3px 10px;
            font-size: 13px;
        }
        QPushButton:hover {
            background: rgba(139, 92, 246, 0.15);
            color: #e2e8f0;
            border-color: rgba(139, 92, 246, 0.5);
        }
    """

    def _build_favorites_row(self) -> None:
        """Reconstrói a linha de atalhos conforme `self._shortcut_times`."""
        while self._fav_row.count():
            item = self._fav_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        lbl_fav = QLabel("Atalhos:")
        lbl_fav.setStyleSheet(
            "color: #475569; font-size: 11px; font-weight: 600;"
            " background: transparent; border: none;"
        )
        self._fav_row.addWidget(lbl_fav)

        for t in self._shortcut_times:
            btn = QPushButton(t)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._FAV_BTN_STYLE)
            btn.clicked.connect(lambda checked=False, time=t: self._set_favorite_time(time))
            self._fav_row.addWidget(btn)

        pencil = QPushButton("\u270e")  # ✎ pencil glyph
        pencil.setCursor(Qt.CursorShape.PointingHandCursor)
        pencil.setToolTip("Editar atalhos de horário")
        pencil.setStyleSheet(self._PENCIL_BTN_STYLE)
        pencil.clicked.connect(self._open_shortcuts_editor)
        self._fav_row.addWidget(pencil)

        self._fav_row.addStretch()

    def _open_shortcuts_editor(self) -> None:
        dlg = ShortcutsEditorDialog(self._shortcut_times, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._shortcut_times = dlg.result_times()
            self._build_favorites_row()

    # ── Calendar popup styling ───────────────────────────────────────
    def _style_calendar_popup(self, cal: QCalendarWidget) -> None:
        """Tema escuro para o popup de calendário do QDateEdit."""
        cal.setGridVisible(False)
        cal.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        cal.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames
        )
        cal.setFirstDayOfWeek(Qt.DayOfWeek.Sunday)

        weekday_fmt = QTextCharFormat()
        weekday_fmt.setForeground(QBrush(QColor("#e2e8f0")))
        weekend_fmt = QTextCharFormat()
        weekend_fmt.setForeground(QBrush(QColor("#cbd5e1")))
        for day in (
            Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
            Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday,
        ):
            cal.setWeekdayTextFormat(day, weekday_fmt)
        cal.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, weekend_fmt)
        cal.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, weekend_fmt)

        cal.setStyleSheet("""
            QCalendarWidget QWidget {
                background-color: #0f172a;
                color: #e2e8f0;
                alternate-background-color: #0f172a;
            }
            QCalendarWidget QAbstractItemView {
                background-color: #0f172a;
                color: #e2e8f0;
                selection-background-color: #3b82f6;
                selection-color: #ffffff;
                outline: 0;
                border: none;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }
            QCalendarWidget QAbstractItemView:enabled {
                color: #e2e8f0;
            }
            QCalendarWidget QAbstractItemView:disabled {
                color: #475569;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e293b, stop:1 #0f172a);
                border-bottom: 1px solid rgba(59, 130, 246, 0.25);
                min-height: 36px;
            }
            QCalendarWidget QToolButton {
                color: #e2e8f0;
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 10px;
                border-radius: 6px;
            }
            QCalendarWidget QToolButton:hover {
                background: rgba(59, 130, 246, 0.2);
                color: #ffffff;
            }
            QCalendarWidget QToolButton::menu-indicator {
                image: none;
                width: 0;
            }
            QCalendarWidget QToolButton#qt_calendar_prevmonth,
            QCalendarWidget QToolButton#qt_calendar_nextmonth {
                qproperty-icon: none;
                font-size: 16px;
                padding: 0 8px;
            }
            QCalendarWidget QMenu {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid rgba(59, 130, 246, 0.3);
            }
            QCalendarWidget QSpinBox {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 4px;
                padding: 2px 6px;
                selection-background-color: #3b82f6;
            }
            QCalendarWidget QTableView {
                selection-background-color: #3b82f6;
                selection-color: #ffffff;
            }
        """)

    def selected_datetime(self) -> datetime:
        qd = self._date_edit.date()
        qt = self._time_edit.time()
        return datetime(qd.year(), qd.month(), qd.day(), qt.hour(), qt.minute(), 0)


class ShortcutsEditorDialog(QDialog):
    """Pequeno diálogo para adicionar/remover horários de atalho."""

    def __init__(self, times: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar atalhos de horário")
        self.setModal(True)
        self.setMinimumWidth(340)
        self._times: list[str] = list(times)

        self.setStyleSheet("""
            QDialog { background: #0f172a; }
            QLabel { color: #e2e8f0; font-size: 12px; background: transparent; }
            QListWidget {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid rgba(59, 130, 246, 0.25);
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
            }
            QListWidget::item { padding: 6px 8px; border-radius: 4px; }
            QListWidget::item:selected {
                background: rgba(59, 130, 246, 0.3);
                color: #ffffff;
            }
            QTimeEdit {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid rgba(59, 130, 246, 0.25);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton {
                background: rgba(59, 130, 246, 0.15);
                color: #e2e8f0;
                border: 1px solid rgba(59, 130, 246, 0.35);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(59, 130, 246, 0.3); }
            QPushButton#danger {
                background: rgba(239, 68, 68, 0.12);
                border-color: rgba(239, 68, 68, 0.4);
                color: #fca5a5;
            }
            QPushButton#danger:hover { background: rgba(239, 68, 68, 0.25); }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        outer.addWidget(QLabel("Horários atuais:"))

        self._list = QListWidget()
        self._refresh_list()
        outer.addWidget(self._list)

        btn_remove = QPushButton("Excluir selecionado")
        btn_remove.setObjectName("danger")
        btn_remove.clicked.connect(self._remove_selected)
        outer.addWidget(btn_remove)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        add_row.addWidget(QLabel("Adicionar:"))
        self._new_time = QTimeEdit()
        self._new_time.setDisplayFormat("HH:mm")
        self._new_time.setTime(QTime(12, 0))
        add_row.addWidget(self._new_time)
        btn_add = QPushButton("+ Adicionar")
        btn_add.clicked.connect(self._add_new)
        add_row.addWidget(btn_add)
        add_row.addStretch()
        outer.addLayout(add_row)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    def _refresh_list(self) -> None:
        self._list.clear()
        for t in sorted(self._times):
            self._list.addItem(t)

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        t = self._list.item(row).text()
        if t in self._times:
            self._times.remove(t)
        self._refresh_list()

    def _add_new(self) -> None:
        qt = self._new_time.time()
        new = f"{qt.hour():02d}:{qt.minute():02d}"
        if new not in self._times:
            self._times.append(new)
            self._refresh_list()

    def result_times(self) -> list[str]:
        return sorted(self._times)


class DailyPatternDialog(ShortcutsEditorDialog):
    """Escolhe data inicial + horários do dia e prévia da distribuição dos vídeos."""

    def __init__(self, times: list[str], n_videos: int, parent=None):
        self._n_videos = n_videos
        self._lbl_preview: QLabel | None = None
        super().__init__(times, parent)
        self.setWindowTitle("Padrão diário de postagem")
        self.setMinimumWidth(380)

        outer = self.layout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Começar em:"))
        self._start = QDateEdit(QDate.currentDate())
        self._start.setDisplayFormat("dd/MM/yyyy")
        self._start.setMinimumDate(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._start.setStyleSheet(
            "QDateEdit { background: #1e293b; color: #e2e8f0; border: 1px solid rgba(59,130,246,0.25);"
            " border-radius: 6px; padding: 4px 8px; font-size: 13px; font-weight: 700; }"
        )
        self._start.dateChanged.connect(lambda _: self._update_preview())
        top.addWidget(self._start)
        top.addStretch()
        outer.insertLayout(0, top)

        intro = QLabel(f"{n_videos} vídeo(s) serão distribuídos nestes horários, um dia após o outro.")
        intro.setWordWrap(True)
        outer.insertWidget(1, intro)

        self._lbl_preview = QLabel()
        self._lbl_preview.setWordWrap(True)
        outer.insertWidget(outer.count() - 1, self._lbl_preview)
        self._update_preview()

    def _refresh_list(self) -> None:
        super()._refresh_list()
        self._update_preview()

    def _update_preview(self) -> None:
        if self._lbl_preview is None:
            return
        slots = build_daily_schedule(self._n_videos, self._times, self.start_date())
        if not slots:
            self._lbl_preview.setText("Adicione pelo menos um horário.")
            self._lbl_preview.setStyleSheet("color: #fca5a5;")
            return
        days = len({d.date() for d in slots})
        txt = (f"{len(self._times)} por dia → {days} dia(s).\n"
               f"1º: {slots[0]:%d/%m %H:%M}   ·   último: {slots[-1]:%d/%m %H:%M}")
        if slots[-1] - datetime.now() > SCHEDULE_MAX_AHEAD:
            txt += "\n⚠ Passa do limite de 10 dias do TikTok — adicione horários ou envie menos vídeos."
            self._lbl_preview.setStyleSheet("color: #fca5a5;")
        else:
            self._lbl_preview.setStyleSheet("color: #93c5fd;")
        self._lbl_preview.setText(txt)

    def start_date(self) -> date:
        return self._start.date().toPyDate()


# ---------------------------------------------------------------------------
# Hashtag chip widget
# ---------------------------------------------------------------------------

class HashtagBar(QWidget):
    """Hashtags como chips removíveis (estilo TikTok Studio)."""
    changed = pyqtSignal()  # só em edição pelo usuário (não em set_tags)

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
        tag = "#" + raw.strip().lstrip("#")
        if tag == "#" or tag in self._tags:
            return
        self._tags.append(tag)
        self._rebuild_chips()
        self.changed.emit()

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
            self.changed.emit()

    def get_tags(self) -> list[str]:
        """Lista de hashtags sem o prefixo '#'."""
        return [t.lstrip("#") for t in self._tags]

    def set_tags(self, tags: list[str]):
        """Substitui as hashtags sem emitir `changed`."""
        self._tags = []
        for t in tags:
            tag = "#" + t.strip().lstrip("#")
            if tag != "#" and tag not in self._tags:
                self._tags.append(tag)
        self._rebuild_chips()

    def clear(self):
        self.set_tags([])


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
    done = pyqtSignal(list)  # paths que falharam ([] = tudo ok)

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
        self.progress.emit(
            f"🚀 Enviando {len(self.tasks)} vídeo(s) em lote (conta '{self.account_name}')…"
        )
        try:
            failed = uploader.upload_batch(
                tasks=self.tasks,
                headless=self.headless,
                browser_name=self.browser,
            )
        except Exception as exc:
            logger.error(f"Upload thread error: {exc}", exc_info=True)
            failed = [t["path"] for t in self.tasks]
        self.done.emit(failed)


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
        self._ai_thread: AIGeneratorThread | None = None
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
        """Stylesheet de QGroupBox no estilo card."""
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

        self.lbl_current_video = QLabel()
        self.lbl_current_video.setWordWrap(True)
        self.lbl_current_video.setStyleSheet(self._label_style(11, bold=False, color=self._TEXT_SEC))
        meta_layout.addWidget(self.lbl_current_video)

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

        self.btn_ai_all = QPushButton("✨ IA p/ todos")
        self.btn_ai_all.setToolTip("Gera descrição + hashtags para todos os vídeos da lista")
        self.btn_ai_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_all.setStyleSheet(self.btn_ai_desc.styleSheet())
        self.btn_ai_all.clicked.connect(self._generate_ai_all)
        lbl_desc_row.addWidget(self.btn_ai_all)

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

        self._char_counter = QLabel(f"0 / {TIKTOK_CAPTION_LIMIT}")
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
        ht_row = QHBoxLayout()
        lbl_ht = QLabel("# Hashtags")
        lbl_ht.setStyleSheet(self._label_style(12))
        ht_row.addWidget(lbl_ht)
        ht_row.addStretch()
        self.btn_tags_all = QPushButton("Aplicar a todos")
        self.btn_tags_all.setToolTip("Copia as hashtags deste vídeo para todos os vídeos da lista")
        self.btn_tags_all.setStyleSheet(self._btn_secondary_style())
        self.btn_tags_all.clicked.connect(self._apply_tags_to_all)
        ht_row.addWidget(self.btn_tags_all)
        meta_layout.addLayout(ht_row)

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

        self.sched_panel = QWidget()
        sched_panel_layout = QVBoxLayout(self.sched_panel)
        sched_panel_layout.setContentsMargins(0, 0, 0, 0)
        sched_panel_layout.setSpacing(8)

        pattern_row = QHBoxLayout()
        self.btn_daily_pattern = QPushButton("📆  Padrão diário…")
        self.btn_daily_pattern.setToolTip(
            "Distribui os vídeos da lista em horários fixos por dia (ex.: 15h, 19h, 23h)"
        )
        self.btn_daily_pattern.setStyleSheet(self._btn_secondary_style())
        self.btn_daily_pattern.clicked.connect(self._open_daily_pattern)
        pattern_row.addWidget(self.btn_daily_pattern)
        self.lbl_sched_info = QLabel()
        self.lbl_sched_info.setStyleSheet(self._label_style(11, bold=False, color=self._TEXT_SEC))
        pattern_row.addWidget(self.lbl_sched_info)
        pattern_row.addStretch()
        sched_panel_layout.addLayout(pattern_row)

        self.lbl_sched_video = QLabel()
        self.lbl_sched_video.setStyleSheet(self._label_style(11, bold=False, color=self._TEXT_SEC))
        sched_panel_layout.addWidget(self.lbl_sched_video)

        self.dt_picker = InlineDateTimePicker()
        self.dt_picker.changed.connect(self._on_schedule_edited)
        sched_panel_layout.addWidget(self.dt_picker)
        self.sched_panel.setVisible(False)

        # radio_now/later are now QPushButtons — use clicked instead of toggled
        self.radio_now.clicked.connect(lambda: self.sched_panel.setVisible(False))
        self.radio_later.clicked.connect(lambda: self.sched_panel.setVisible(True))
        sched_layout.addWidget(self.sched_panel)
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

        btn_cancel = QPushButton("Remover da lista")
        btn_cancel.setToolTip(
            "Só tira da lista local. O agendamento já está no TikTok — "
            "para cancelar, exclua o post agendado no TikTok Studio."
        )
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
        self.hashtag_bar.changed.connect(self._on_meta_edited)
        self._update_meta_fields()

    # ------------------------------------------------------------------
    # Per-video metadata helpers
    # ------------------------------------------------------------------

    _PATH_ROLE = Qt.ItemDataRole.UserRole

    def _item_path(self, item: QListWidgetItem) -> str:
        return item.data(self._PATH_ROLE)

    def _find_item(self, path: str) -> QListWidgetItem | None:
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if self._item_path(item) == path:
                return item
        return None

    def _add_video(self, path: str) -> None:
        """Adiciona o vídeo à lista (ignora duplicados) com metadados vazios."""
        if path in self._video_metadata:
            return
        self._video_metadata[path] = {"caption": "", "hashtags": [], "status": None, "schedule": None}
        item = QListWidgetItem()
        item.setData(self._PATH_ROLE, path)
        item.setToolTip(path)
        self.file_list.addItem(item)
        self._refresh_item(path)
        if self.file_list.currentItem() is None:
            self.file_list.setCurrentItem(item)

    def _refresh_item(self, path: str) -> None:
        """Atualiza o texto do item: status do envio + se já tem legenda/hashtags."""
        item = self._find_item(path)
        data = self._video_metadata.get(path)
        if item is None or data is None:
            return
        status = {"ok": "🚀", "fail": "❌"}.get(data.get("status"), "")
        filled = "📝" if data["caption"].strip() or data["hashtags"] else "⬜"
        n_tags = len(data["hashtags"])
        tags = f"  · {n_tags} #" if n_tags else ""
        when = f"  · 🕒 {data['schedule']:%d/%m %H:%M}" if data.get("schedule") else ""
        item.setText(f"{status}{filled}  {Path(path).name}{tags}{when}")

    def _on_file_selected(self, current, previous):
        self._current_video = self._item_path(current) if current else None
        self._update_meta_fields()

    def _update_meta_fields(self):
        if not self._current_video:
            self.txt_caption.blockSignals(True)
            self.txt_caption.clear()
            self.txt_caption.setEnabled(False)
            self.txt_caption.blockSignals(False)
            self.hashtag_bar.set_tags([])
            self.hashtag_bar.setEnabled(False)
            self.lbl_current_video.setText("Selecione um vídeo na lista para editar descrição e hashtags.")
            self.dt_picker.setEnabled(False)
            self.lbl_sched_video.setText("Selecione um vídeo para definir o horário dele.")
            self._update_sched_info()
            return

        self.txt_caption.setEnabled(True)
        self.hashtag_bar.setEnabled(True)
        self.lbl_current_video.setText(f"Editando: {Path(self._current_video).name}")
        data = self._video_metadata.get(self._current_video, {"caption": "", "hashtags": []})
        self.txt_caption.blockSignals(True)
        self.txt_caption.setPlainText(data.get("caption", ""))
        self.txt_caption.blockSignals(False)
        self.hashtag_bar.set_tags(data.get("hashtags", []))
        self._on_caption_changed()

        self.dt_picker.setEnabled(True)
        self.lbl_sched_video.setText(f"Horário de: {Path(self._current_video).name}")
        self.dt_picker.set_datetime(data.get("schedule"))
        self._update_sched_info()

    def _on_schedule_edited(self):
        if self._current_video and self._current_video in self._video_metadata:
            self._video_metadata[self._current_video]["schedule"] = self.dt_picker.selected_datetime()
            self._refresh_item(self._current_video)
            self._update_sched_info()

    def _update_sched_info(self):
        pending = [d for d in self._video_metadata.values() if d.get("status") != "ok"]
        with_time = sum(1 for d in pending if d.get("schedule"))
        self.lbl_sched_info.setText(f"{with_time} de {len(pending)} vídeo(s) com horário")

    def _open_daily_pattern(self):
        targets = [f for f in self.get_selected_files()
                   if self._video_metadata[f].get("status") != "ok"]
        if not targets:
            QMessageBox.warning(self, "Aviso", "Adicione vídeos na lista primeiro.")
            return
        dlg = DailyPatternDialog(self.dt_picker.shortcut_times(), len(targets), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        times = dlg.result_times()
        slots = build_daily_schedule(len(targets), times, dlg.start_date())
        if not slots:
            return
        self.dt_picker.set_shortcut_times(times)
        for path, dt in zip(targets, slots):
            self._video_metadata[path]["schedule"] = dt
            self._refresh_item(path)
        self._update_meta_fields()
        self.lbl_progress.setText(
            f"📆 {len(slots)} vídeo(s) programados de {slots[0]:%d/%m %H:%M} até {slots[-1]:%d/%m %H:%M}."
        )

    def _on_meta_edited(self):
        if self._current_video and self._current_video in self._video_metadata:
            data = self._video_metadata[self._current_video]
            data["caption"] = self.txt_caption.toPlainText()
            data["hashtags"] = self.hashtag_bar.get_tags()
            self._refresh_item(self._current_video)

    def _apply_tags_to_all(self):
        if not self._current_video:
            QMessageBox.warning(self, "Aviso", "Selecione um vídeo na lista primeiro.")
            return
        tags = self.hashtag_bar.get_tags()
        for path, data in self._video_metadata.items():
            data["hashtags"] = list(tags)
            self._refresh_item(path)
        self.lbl_progress.setText(f"# Hashtags aplicadas a {len(self._video_metadata)} vídeo(s).")

    def _change_api_key(self):
        from config.settings import settings
        current_key = getattr(settings, 'gemini_api_key', '')
        # Não pré-preenche a chave: só mostra os 4 últimos caracteres
        hint = f"Chave atual: ••••{current_key[-4:]}\n" if current_key else "Nenhuma chave salva.\n"
        api_key, ok = QInputDialog.getText(
            self, "Alterar API Key do Gemini",
            hint + "Insira sua nova chave de API do Google Gemini:\n(Se for inválida ou vazia, pediremos novamente no uso)",
            QLineEdit.EchoMode.Password,
        )
        if ok:
            settings.gemini_api_key = api_key.strip()
            settings.save_config()
            QMessageBox.information(self, "Sucesso", "API Key salva com sucesso!")

    def _ensure_api_key(self) -> str | None:
        """Retorna a API key do Gemini, pedindo ao usuário se ainda não houver."""
        from config.settings import settings

        if getattr(settings, 'gemini_api_key', ''):
            return settings.gemini_api_key
        api_key, ok = QInputDialog.getText(
            self, "API Key do Gemini",
            "Para usar a IA, insira sua chave de API grátis do Google Gemini:\n(Ela será salva localmente)",
            QLineEdit.EchoMode.Password
        )
        if ok and api_key.strip():
            settings.gemini_api_key = api_key.strip()
            settings.save_config()
            return settings.gemini_api_key
        return None

    def _ai_busy(self) -> bool:
        return self._ai_thread is not None and self._ai_thread.isRunning()

    def _generate_ai_desc(self):
        if not self._current_video:
            QMessageBox.warning(self, "Aviso", "Selecione um vídeo na lista primeiro.")
            return
        if self._ai_busy():
            return
        api_key = self._ensure_api_key()
        if not api_key:
            return

        context, ok = QInputDialog.getText(
            self, "Contexto do Vídeo (IA)",
            "Diga brevemente sobre o que é o vídeo para a IA escrever a legenda\n(Ex: '10 dicas de marketing'): ",
        )
        if not ok or not context.strip():
            return
        self._start_ai(api_key, [(self._current_video, context.strip())])

    def _generate_ai_all(self):
        paths = self.get_selected_files()
        if not paths:
            QMessageBox.warning(self, "Aviso", "Adicione vídeos na lista primeiro.")
            return
        if self._ai_busy():
            return
        api_key = self._ensure_api_key()
        if not api_key:
            return

        context, ok = QInputDialog.getText(
            self, "Contexto dos Vídeos (IA)",
            f"Vai gerar descrição + hashtags para {len(paths)} vídeo(s).\n"
            "Contexto geral (opcional — o nome de cada arquivo também é usado):",
        )
        if not ok:
            return
        general = context.strip()
        items = []
        for path in paths:
            name = re.sub(r"[_\-.]+", " ", Path(path).stem).strip()
            ctx = f"Título/arquivo do vídeo: {name}"
            items.append((path, f"{general}. {ctx}" if general else ctx))
        self._start_ai(api_key, items)

    def _start_ai(self, api_key: str, items: list[tuple[str, str]]):
        self.btn_ai_desc.setEnabled(False)
        self.btn_ai_all.setEnabled(False)
        self.btn_ai_desc.setText("⏳ Gerando...")
        self._ai_errors: list[str] = []

        lang = self.combo_ai_lang.currentText()
        self._ai_thread = AIGeneratorThread(api_key, items, language=lang)
        self._ai_thread.item_done.connect(self._on_ai_item_done)
        self._ai_thread.item_failed.connect(self._on_ai_item_failed)
        self._ai_thread.progress.connect(
            lambda done, total: self.lbl_progress.setText(f"✨ IA: {done}/{total} vídeo(s) processado(s)…")
        )
        self._ai_thread.finished.connect(self._on_ai_finished)
        self._ai_thread.start()

    def _on_ai_item_done(self, path: str, text: str, tags: list):
        data = self._video_metadata.get(path)
        if data is None:  # removido da lista enquanto a IA rodava
            return
        data["caption"] = text
        data["hashtags"] = [str(t).strip().lstrip("#") for t in tags if str(t).strip()]
        self._refresh_item(path)
        if path == self._current_video:
            self._update_meta_fields()

    def _on_ai_item_failed(self, path: str, msg: str):
        self._ai_errors.append(f"{Path(path).name}: {msg}")

    def _on_ai_finished(self):
        self.btn_ai_desc.setEnabled(True)
        self.btn_ai_all.setEnabled(True)
        self.btn_ai_desc.setText("✨ Criar com IA")
        if self._ai_errors:
            QMessageBox.critical(
                self, "Erro",
                "Tivemos um problema com a resposta do Gemini:\n\n" + "\n\n".join(self._ai_errors[:5]),
            )
            self.lbl_progress.setText(f"⚠️ IA terminou com {len(self._ai_errors)} erro(s).")
        else:
            self.lbl_progress.setText("✨ Descrições e hashtags geradas!")

    # ------------------------------------------------------------------
    # Caption char counter
    # ------------------------------------------------------------------

    def _on_caption_changed(self):
        n = len(self.txt_caption.toPlainText())
        self._char_counter.setText(f"{n} / {TIKTOK_CAPTION_LIMIT}")
        if n > TIKTOK_CAPTION_LIMIT:
            self._char_counter.setStyleSheet(f"color: #EF4444; font-size: 10px; font-weight: 400; background: transparent;")
        else:
            self._char_counter.setStyleSheet(self._label_style(10, bold=False, color=self._TEXT_SEC))

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def _refresh_accounts(self):
        # Disconnect before clearing to avoid stale signal accumulation
        try:
            self.account_list.currentItemChanged.disconnect(self._on_account_selected)
        except TypeError:
            pass  # Not connected yet (first call)

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
            self.lbl_account_status.setText("Nenhuma conta conectada. Clique em '+ Adicionar Conta'.")

        # Reconnect once (cleanly)
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
        for f in filenames:
            self._add_video(f)

    def _remove_selected_files(self):
        for item in self.file_list.selectedItems():
            self._video_metadata.pop(self._item_path(item), None)
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
        return [self._item_path(self.file_list.item(i)) for i in range(self.file_list.count())]

    # ------------------------------------------------------------------
    # Action dispatcher
    # ------------------------------------------------------------------

    def _handle_action(self):
        if self.upload_thread is not None and self.upload_thread.isRunning():
            return

        account_name = self._selected_account_name()
        if not account_name:
            QMessageBox.warning(self, "Erro", "Adicione e selecione uma conta antes de enviar!")
            return

        # Já enviados com sucesso ficam de fora (evita postar duplicado ao reenviar falhas)
        files = [f for f in self.get_selected_files()
                 if self._video_metadata[f].get("status") != "ok"]
        if not files:
            QMessageBox.warning(self, "Erro", "Adicione pelo menos um vídeo que ainda não foi enviado!")
            return

        for video in files:
            if not Path(video).exists():
                QMessageBox.warning(self, "Erro", f"Arquivo de vídeo não encontrado: {video}")
                return

        browser = self.combo_browser.currentText()
        self._start_batch_upload(account_name, files, browser, scheduled=self.radio_later.isChecked())

    # ------------------------------------------------------------------
    # Batch Upload
    # ------------------------------------------------------------------

    def _start_batch_upload(self, account_name, files, browser, scheduled=False):
        if scheduled:
            now = datetime.now()
            sem_horario = [f for f in files if not self._video_metadata[f].get("schedule")]
            if sem_horario:
                QMessageBox.warning(
                    self, "Aviso",
                    f"{len(sem_horario)} vídeo(s) sem horário. Selecione cada um e defina o horário, "
                    "ou use o botão 'Padrão diário'.",
                )
                return
            fora = [
                f"• {Path(f).name} — {self._video_metadata[f]['schedule']:%d/%m %H:%M}"
                for f in files
                if not (SCHEDULE_MIN_LEAD
                        <= self._video_metadata[f]["schedule"] - now
                        <= SCHEDULE_MAX_AHEAD)
            ]
            if fora:
                QMessageBox.warning(
                    self, "Aviso",
                    "O TikTok só aceita agendamentos entre 20 minutos e 10 dias à frente. "
                    "Ajuste estes vídeos:\n" + "\n".join(fora[:15]),
                )
                return

        tasks = []
        for video in files:
            data = self._video_metadata[video]
            tasks.append({
                "path": video,
                "title": data["caption"].strip(),
                "hashtags": list(data["hashtags"]),
                "schedule_time": data["schedule"] if scheduled else None,
            })
        # Mais cedo primeiro: o TikTok Studio fica na ordem de publicação
        if scheduled:
            tasks.sort(key=lambda t: t["schedule_time"])

        self._pending_tasks = tasks
        self._pending_account = account_name
        self._pending_browser = browser
        self.btn_upload.setEnabled(False)
        self.lbl_progress.setText(f"🚀 Iniciando upload de {len(tasks)} vídeo(s) com conta '{account_name}'…")

        self.upload_thread = UploaderThread(
            account_name=account_name,
            tasks=tasks,
            browser=browser,
            headless=True,
        )
        self.upload_thread.progress.connect(self.lbl_progress.setText)
        self.upload_thread.done.connect(self._upload_done)
        self.upload_thread.start()

    def _upload_done(self, failed: list):
        self.btn_upload.setEnabled(True)
        failed_set = set(failed)
        tasks = self._pending_tasks
        for t in tasks:
            path = t["path"]
            if path in self._video_metadata:
                self._video_metadata[path]["status"] = "fail" if path in failed_set else "ok"
                self._refresh_item(path)

        self._update_sched_info()
        ok_tasks = [t for t in tasks if t["path"] not in failed_set]
        for t in ok_tasks:
            if t["schedule_time"]:
                timer = QTimer(self)
                timer.setSingleShot(True)
                self._scheduled_posts.append(ScheduledPost(
                    self._pending_account, t["path"], t["title"], t["hashtags"],
                    self._pending_browser, t["schedule_time"], timer,
                ))
        self._refresh_queue_ui()

        if not failed_set:
            QMessageBox.information(self, "Sucesso", f"{len(tasks)} vídeo(s) enviado(s) com sucesso!")
            self.lbl_progress.setText("✅ Processo concluído!")
        else:
            names = "\n".join(f"• {Path(p).name}" for p in failed)
            QMessageBox.critical(
                self, "Erro",
                f"{len(failed_set)} de {len(tasks)} vídeo(s) falharam:\n{names}\n\n"
                "Verifique os cookies da conta e clique em Enviar de novo — "
                "só os que falharam serão reenviados.",
            )
            self.lbl_progress.setText(f"⚠️ {len(ok_tasks)} enviado(s), {len(failed_set)} com falha (❌)")

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
        """Adiciona um arquivo programaticamente (chamado após o processamento)."""
        self._add_video(str(path))
