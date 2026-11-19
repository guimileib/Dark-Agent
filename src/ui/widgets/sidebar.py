"""Sidebar de navegação no estilo shadcn (port do dashboard-sidebar.tsx para Qt)."""

from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, Qt, pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import icons

# Tokens (espelham modern_theme.qss)
FG = "#fafafa"
MUTED = "#a1a1aa"
MUTED_ICON = "#71717a"
SIDEBAR_WIDTH = 260
ROW_INDENT = 12


@dataclass
class NavItemData:
    id: str
    title: str
    icon: str
    badge: Optional[str] = None
    shortcut: Optional[str] = None
    children: list["NavItemData"] = field(default_factory=list)


@dataclass
class NavGroupData:
    items: list[NavItemData]
    heading: Optional[str] = None


def flatten(items: list[NavItemData]) -> list[NavItemData]:
    """Lista plana (pais + filhos), na ordem de exibição."""
    out: list[NavItemData] = []
    for it in items:
        out.append(it)
        out.extend(flatten(it.children))
    return out


class _NavRow(QFrame):
    """Linha clicável: ícone, título, atalho (no hover), badge e chevron."""

    clicked = pyqtSignal()

    def __init__(self, item: NavItemData, level: int, parent=None):
        super().__init__(parent)
        self.item = item
        self._active = False
        self._hover = False
        self._open = False
        self.setObjectName("NavRow")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(level * ROW_INDENT + 10, 0, 10, 0)
        lay.setSpacing(10)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(16, 16)
        self.icon_lbl.setObjectName("NavIcon")
        lay.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(item.title)
        self.title_lbl.setObjectName("NavTitle")
        lay.addWidget(self.title_lbl, 1)

        self.kbd_lbl = QLabel(item.shortcut or "")
        self.kbd_lbl.setObjectName("Kbd")
        self.kbd_lbl.setFixedHeight(20)
        self.kbd_lbl.setVisible(False)
        lay.addWidget(self.kbd_lbl)

        self.badge_lbl = QLabel()
        self.badge_lbl.setObjectName("NavBadge")
        self.badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_lbl.setVisible(False)
        lay.addWidget(self.badge_lbl)

        self.chevron_lbl = QLabel()
        self.chevron_lbl.setFixedSize(14, 14)
        self.chevron_lbl.setObjectName("NavIcon")
        self.chevron_lbl.setVisible(bool(item.children))
        lay.addWidget(self.chevron_lbl)

        self.set_badge(item.badge)
        self._refresh()

    def set_active(self, active: bool):
        self._active = active
        self._refresh()

    def set_open(self, is_open: bool):
        self._open = is_open
        self._refresh()

    def set_badge(self, text: Optional[str]):
        self.badge_lbl.setText(text or "")
        self.badge_lbl.setVisible(bool(text))

    def _refresh(self):
        self.setProperty("active", self._active)
        self.setProperty("hover", self._hover)
        self.title_lbl.setProperty("active", self._active)
        for w in (self, self.title_lbl):
            w.style().unpolish(w)
            w.style().polish(w)
        color = FG if self._active else ("#d4d4d8" if self._hover else MUTED_ICON)
        self.icon_lbl.setPixmap(icons.pixmap(self.item.icon, color, 16))
        chev = "chevron-down" if self._open else "chevron-right"
        self.chevron_lbl.setPixmap(icons.pixmap(chev, MUTED_ICON, 14, 2))
        self.kbd_lbl.setVisible(self._hover and bool(self.item.shortcut))

    def enterEvent(self, e):
        self._hover = True
        self._refresh()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._refresh()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class _ChildrenContainer(QWidget):
    """Container dos filhos com a linha-guia vertical à esquerda."""

    def __init__(self, guide_x: float, parent=None):
        super().__init__(parent)
        self._guide_x = guide_x

    def paintEvent(self, e):
        p = QPainter(self)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        x = int(self._guide_x)
        p.drawLine(x, 2, x, self.height() - 2)
        p.end()


class NavItem(QWidget):
    """Item de navegação; com filhos, vira um grupo colapsável animado."""

    selected = pyqtSignal(str)

    def __init__(self, item: NavItemData, level: int = 0, parent=None):
        super().__init__(parent)
        self.item = item
        self._open = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.row = _NavRow(item, level)
        self.row.clicked.connect(self._on_click)
        lay.addWidget(self.row)

        self.child_items: list[NavItem] = []
        self.children_box: Optional[_ChildrenContainer] = None
        if item.children:
            self.children_box = _ChildrenContainer(level * ROW_INDENT + 17.5)
            cl = QVBoxLayout(self.children_box)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)
            for child in item.children:
                ni = NavItem(child, level + 1)
                ni.selected.connect(self.selected)
                cl.addWidget(ni)
                self.child_items.append(ni)
            self.children_box.setMaximumHeight(0)
            self._anim = QPropertyAnimation(self.children_box, b"maximumHeight", self)
            self._anim.setDuration(220)
            self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            lay.addWidget(self.children_box)

    def _on_click(self):
        if self.item.children:
            self.set_open(not self._open)
        else:
            self.selected.emit(self.item.id)

    def set_open(self, is_open: bool, animate: bool = True):
        if not self.children_box or is_open == self._open:
            return
        self._open = is_open
        self.row.set_open(is_open)
        target = self.children_box.sizeHint().height() if is_open else 0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self.children_box.maximumHeight())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.children_box.setMaximumHeight(target)

    def all_items(self) -> list["NavItem"]:
        out = [self]
        for c in self.child_items:
            out.extend(c.all_items())
        return out


class SidebarNav(QFrame):
    """Sidebar completa: marca, grupos de navegação e itens de rodapé.

    Emite `selected(id)` para itens folha; `set_active(id)` só muda o destaque.
    """

    selected = pyqtSignal(str)

    def __init__(self, groups: list[NavGroupData], bottom: list[NavItemData],
                 title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._active_id: Optional[str] = None
        self._items: dict[str, NavItem] = {}
        self._parents: dict[str, NavItem] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)
        root.addWidget(self._build_brand(title, subtitle))
        root.addSpacing(16)

        scroll = QScrollArea()
        scroll.setObjectName("SidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("SidebarBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(16)
        for group in groups:
            gw = QWidget()
            gl = QVBoxLayout(gw)
            gl.setContentsMargins(0, 0, 0, 0)
            gl.setSpacing(2)
            if group.heading:
                h = QLabel(group.heading.upper())
                h.setObjectName("NavHeading")
                gl.addWidget(h)
            for it in group.items:
                gl.addWidget(self._add_item(it))
            bl.addWidget(gw)
        bl.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("SidebarFooter")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(0, 12, 0, 0)
        fl.setSpacing(2)
        for it in bottom:
            fl.addWidget(self._add_item(it))
        root.addWidget(footer)

    def _build_brand(self, title: str, subtitle: str) -> QWidget:
        w = QFrame()
        w.setObjectName("SidebarBrand")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)
        logo = QLabel()
        logo.setObjectName("BrandLogo")
        logo.setFixedSize(32, 32)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(icons.pixmap("sparkles", "#ffffff", 16, 1.75))
        lay.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("BrandTitle")
        s = QLabel(subtitle)
        s.setObjectName("BrandSubtitle")
        col.addWidget(t)
        col.addWidget(s)
        lay.addLayout(col, 1)
        return w

    def _add_item(self, data: NavItemData) -> NavItem:
        ni = NavItem(data)
        ni.selected.connect(self.selected)
        for sub in ni.all_items():
            self._items[sub.item.id] = sub
            for child in sub.child_items:
                self._parents[child.item.id] = sub
        return ni

    def set_active(self, item_id: str):
        """Destaca o item e abre o grupo-pai, se houver."""
        if self._active_id in self._items:
            self._items[self._active_id].row.set_active(False)
        self._active_id = item_id
        if item_id in self._items:
            self._items[item_id].row.set_active(True)
        parent = self._parents.get(item_id)
        if parent:
            parent.set_open(True)

    def set_badge(self, item_id: str, text: Optional[str]):
        if item_id in self._items:
            self._items[item_id].row.set_badge(text)
