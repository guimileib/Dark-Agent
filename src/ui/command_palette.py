"""Paleta de comandos (Ctrl+K) sobreposta à janela principal."""

from typing import Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from ui import icons


class CommandPalette(QWidget):
    """Overlay com backdrop escuro; Enter executa, Esc/clique fora fecha.

    `entries` = [(id, título, ícone, caminho)]; emite `chosen(id)`.
    """

    chosen = pyqtSignal(str)

    def __init__(self, parent: QWidget, entries: list[tuple[str, str, str, str]]):
        super().__init__(parent)
        self.setObjectName("PaletteOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._entries = entries
        self.hide()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 0, 16, 0)
        parent.installEventFilter(self)

        self.card = QFrame()
        self.card.setObjectName("PaletteCard")
        self.card.setMaximumWidth(576)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("PaletteBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 10, 0)
        bl.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("search", "#71717a", 18))
        bl.addWidget(ic)
        self.input = QLineEdit()
        self.input.setObjectName("PaletteInput")
        self.input.setPlaceholderText("Buscar seções ou ações...")
        self.input.textChanged.connect(self._filter)
        self.input.returnPressed.connect(self._activate_current)
        self.input.installEventFilter(self)
        bl.addWidget(self.input, 1)
        esc = QLabel("ESC")
        esc.setObjectName("Kbd")
        esc.setFixedHeight(20)
        bl.addWidget(esc)
        close = QPushButton()
        close.setObjectName("GhostIconButton")
        close.setIcon(icons.icon("x", "#a1a1aa", 18))
        close.setIconSize(QSize(18, 18))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.close_palette)
        bl.addWidget(close)
        cl.addWidget(bar)

        self.list = QListWidget()
        self.list.setObjectName("PaletteList")
        self.list.setIconSize(QSize(16, 16))
        self.list.itemActivated.connect(lambda it: self._choose(it.data(Qt.ItemDataRole.UserRole)))
        self.list.itemClicked.connect(lambda it: self._choose(it.data(Qt.ItemDataRole.UserRole)))
        cl.addWidget(self.list)

        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setContentsMargins(0, 32, 0, 32)
        el.setSpacing(8)
        cmd = QLabel()
        cmd.setPixmap(icons.pixmap("command", "#3f3f46", 24))
        cmd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(cmd)
        msg = QLabel("Nada encontrado. Tente outro termo.")
        msg.setObjectName("MutedLabel")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(msg)
        cl.addWidget(self.empty)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card, 100)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    # ── abrir/fechar ────────────────────────────────────────────────────────
    def open_palette(self):
        p = self.parentWidget()
        self.setGeometry(p.rect())
        lay = self.layout()
        lay.setContentsMargins(16, int(p.height() * 0.15), 16, 0)
        self.input.clear()
        self._filter("")
        self.show()
        self.raise_()
        self.input.setFocus()

    def close_palette(self):
        self.hide()

    # ── filtro/seleção ──────────────────────────────────────────────────────
    def _filter(self, text: str):
        q = text.strip().lower()
        self.list.clear()
        for eid, title, icon_name, path in self._entries:
            if q and q not in title.lower() and q not in path.lower():
                continue
            it = QListWidgetItem(icons.icon(icon_name, "#a1a1aa", 16), f"{title}")
            it.setData(Qt.ItemDataRole.UserRole, eid)
            it.setToolTip(path)
            self.list.addItem(it)
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        if has:
            self.list.setCurrentRow(0)
            self.list.setFixedHeight(min(self.list.count(), 7) * 38 + 12)

    def _activate_current(self):
        it = self.list.currentItem()
        if it:
            self._choose(it.data(Qt.ItemDataRole.UserRole))

    def _choose(self, eid: Optional[str]):
        if eid:
            self.close_palette()
            self.chosen.emit(eid)

    def eventFilter(self, obj, e):
        if obj is self.parentWidget() and e.type() == e.Type.Resize and self.isVisible():
            self.setGeometry(obj.rect())
        if obj is self.input and e.type() == e.Type.KeyPress:
            k = e.key()
            if k == Qt.Key.Key_Escape:
                self.close_palette()
                return True
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.list.count():
                step = 1 if k == Qt.Key.Key_Down else -1
                r = (self.list.currentRow() + step) % self.list.count()
                self.list.setCurrentRow(r)
                return True
        return super().eventFilter(obj, e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(9, 9, 11, 150))
        p.end()

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self.close_palette()
        super().mousePressEvent(e)
