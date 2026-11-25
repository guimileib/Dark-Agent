"""Página de Legendas em layout de editor: biblioteca de estilos, player, detalhes e fila."""

import copy
import logging
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QButtonGroup, QColorDialog,
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListView,
    QLayout, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ui import icons

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".m4v"}
CATEGORIAS = [
    ("todos", "Todos"),
    ("social", "Social"),
    ("profissional", "Profissional"),
    ("criativo", "Criativo"),
]
EXIBICAO = {
    "palavra": "Palavra a palavra",
    "frase": "Frase",
    "karaoke": "Karaokê",
    "palavra_destacada": "Palavra destacada",
}
TILE_W, TILE_H, TILE_GAP = 104, 92, 10


def ass_para_hex(cor_ass: str, padrao: str = "#FFFFFF") -> str:
    """Converte &HBBGGRR ou &HAABBGGRR para #RRGGBB."""
    h = (cor_ass or "").upper().replace("&H", "").rstrip("&")
    if len(h) == 8:
        h = h[2:]
    if len(h) != 6:
        return padrao
    return f"#{h[4:6]}{h[2:4]}{h[0:2]}"


def hex_para_ass(cor: QColor) -> str:
    return f"&H{cor.blue():02X}{cor.green():02X}{cor.red():02X}"


# ─── Threads de preview ─────────────────────────────────────────────────────
class SinglePreviewGeneratorThread(QThread):
    """Gera um único preview sob demanda."""

    preview_ready = pyqtSignal(str)  # caminho

    def __init__(self, renderer, estilo, tamanho, force=False, posicao="Embaixo"):
        super().__init__()
        self.renderer = renderer
        self.estilo = estilo
        self.tamanho = tamanho
        self.force = force
        self.posicao = posicao
        # Resultado obsoleto é descartado em vez de terminate(): matar o Pillow
        # no meio do render deixaria PNG corrompido no cache.
        self._discarded = False

    def discard(self):
        """Marca a thread como obsoleta — o resultado será ignorado."""
        self._discarded = True

    def run(self):
        try:
            path = self.renderer.gerar_preview(
                copy.deepcopy(self.estilo),
                tamanho=self.tamanho,
                force=self.force,
                posicao=self.posicao,
            )
            if path and not self._discarded:
                self.preview_ready.emit(str(path))
        except Exception as e:
            logger.error(f"Erro na thread de preview: {e}")


class PreviewGeneratorThread(QThread):
    """Gera previews em background (todos os tamanhos)."""

    preview_gerado = pyqtSignal(int, str)  # tamanho, caminho
    concluido = pyqtSignal()

    def __init__(self, estilo, renderer):
        super().__init__()
        self.estilo = estilo
        self.renderer = renderer

    def run(self):
        try:
            previews = self.renderer.gerar_previews_todos_tamanhos(self.estilo)
            for tamanho, caminho in previews.items():
                self.preview_gerado.emit(tamanho, str(caminho))
            self.concluido.emit()
        except Exception as e:
            logger.error(f"Erro ao gerar previews: {e}")


# ─── Tile de estilo ("Abc" renderizado nas cores do estilo) ─────────────────
class StyleTile(QAbstractButton):
    """Card quadrado da biblioteca com o "Abc" desenhado no estilo real."""

    def __init__(self, estilo, parent=None):
        super().__init__(parent)
        self.estilo = estilo
        self.setCheckable(True)
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(estilo.nome)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.filtrado = False  # fora da categoria ativa

    @staticmethod
    def nome_curto(nome: str) -> str:
        for p in ("TikTok ", "Instagram ", "YouTube "):
            nome = nome.replace(p, "")
        return nome

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        hover = self.underMouse()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1c1c20" if hover or self.isChecked() else "#151518"))
        p.drawRoundedRect(r, 8, 8)

        self._desenhar_abc(p, QRectF(r.x(), r.y() + 4, r.width(), r.height() - 24))

        p.setPen(QColor("#fafafa" if self.isChecked() else "#71717a"))
        f = QFont("Segoe UI")
        f.setPixelSize(10)
        f.setWeight(QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Normal)
        p.setFont(f)
        p.drawText(QRectF(r.x() + 4, r.bottom() - 20, r.width() - 8, 16),
                   Qt.AlignmentFlag.AlignCenter, self.nome_curto(self.estilo.nome))

        if self.isChecked():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#3b82f6"), 2))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        elif hover:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#3f3f46"), 1))
            p.drawRoundedRect(r, 8, 8)
        p.end()

    def _desenhar_abc(self, p: QPainter, area: QRectF):
        e = self.estilo
        font = QFont(e.fonte or "Arial")
        font.setPixelSize(int(area.height() * 0.56))
        font.setBold(bool(getattr(e, "bold", True)))
        font.setItalic(bool(getattr(e, "italic", False)))
        texto = "Abc"
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(texto)
        base = QPointF(area.center().x() - tw / 2,
                       area.center().y() + (fm.ascent() - fm.descent()) / 2)
        path = QPainterPath()
        path.addText(base, font, texto)

        primaria = QColor(ass_para_hex(e.cor_primaria))
        secundaria = QColor(ass_para_hex(getattr(e, "cor_secundaria", ""), "#FFFF00"))
        borda = QColor(ass_para_hex(getattr(e, "cor_borda", ""), "#000000"))
        espessura = getattr(e, "borda_espessura", 0) or 0
        sombra = getattr(e, "sombra_offset", 0) or 0
        join = Qt.PenJoinStyle.RoundJoin

        if e.id == "neon_glow":
            for w, a in ((9, 40), (6, 70), (3, 130)):
                c = QColor(secundaria)
                c.setAlpha(a)
                p.strokePath(path, QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, join))
        if sombra:
            p.fillPath(path.translated(min(sombra, 3), min(sombra, 3)), QColor(0, 0, 0, 170))
        if espessura:
            pen = QPen(borda, min(2 + espessura * 0.8, 6), Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, join)
            p.strokePath(path, pen)
            if borda.rgb() == primaria.rgb():
                # Borda da mesma cor do texto viraria um borrão no tile.
                p.strokePath(path, QPen(QColor(0, 0, 0, 200), 2, Qt.PenStyle.SolidLine,
                                        Qt.PenCapStyle.RoundCap, join))
        if e.id == "gradient_wave":
            g = QLinearGradient(path.boundingRect().topLeft(), path.boundingRect().topRight())
            g.setColorAt(0, primaria)
            g.setColorAt(1, secundaria)
            p.fillPath(path, QBrush(g))
        else:
            p.fillPath(path, primaria)
        if getattr(e, "tipo_exibicao", "") in ("palavra_destacada", "karaoke") and e.id != "gradient_wave":
            # Simula a palavra em destaque pintando o "A" na cor secundária.
            a_path = QPainterPath()
            a_path.addText(base, font, "A")
            p.fillPath(a_path, secundaria)


class _TileGrid(QWidget):
    """Grade responsiva: recalcula colunas conforme a largura."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles: list[StyleTile] = []
        self._cols = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setSpacing(TILE_GAP)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        # Sem constraint: a largura mínima da grade não pode travar o scroll
        # (senão o nº de colunas nunca diminui); a altura é fixada à mão.
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

    def set_tiles(self, tiles: list[StyleTile]):
        self.tiles = tiles
        self._cols = 0
        self._relayout()

    def minimumSizeHint(self):
        return QSize(TILE_W, self.minimumHeight())

    def sizeHint(self):
        return self.minimumSizeHint()

    def _relayout(self):
        vp = self.parentWidget()
        largura = vp.width() if vp is not None else self.width()
        cols = max(1, (largura - 4 + TILE_GAP) // (TILE_W + TILE_GAP))
        visiveis = [t for t in self.tiles if not t.filtrado]
        if cols == self._cols and all(self.grid.indexOf(t) >= 0 for t in visiveis):
            return
        self._cols = cols
        for t in self.tiles:
            self.grid.removeWidget(t)
            t.setVisible(not t.filtrado)
        for i, t in enumerate(visiveis):
            self.grid.addWidget(t, i // cols, i % cols)
        rows = (len(visiveis) + cols - 1) // cols
        self.setMinimumHeight(max(0, rows * (TILE_H + TILE_GAP) - TILE_GAP))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def showEvent(self, e):
        super().showEvent(e)
        self._relayout()


def _panel(titulo: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    """Card de painel com cabeçalho fino (título à esquerda, ações à direita)."""
    card = QFrame()
    card.setObjectName("EditorPanel")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    head = QFrame()
    head.setObjectName("EditorPanelHead")
    head.setFixedHeight(40)
    hl = QHBoxLayout(head)
    hl.setContentsMargins(14, 0, 10, 0)
    hl.setSpacing(6)
    t = QLabel(titulo)
    t.setObjectName("EditorPanelTitle")
    hl.addWidget(t)
    hl.addStretch(1)
    lay.addWidget(head)
    return card, lay, hl


def _icon_button(nome: str, tooltip: str, slot) -> QPushButton:
    b = QPushButton()
    b.setObjectName("GhostIconButton")
    b.setIcon(icons.icon(nome, "#a1a1aa", 16))
    b.setIconSize(QSize(16, 16))
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(slot)
    return b


# ─── Widget principal ───────────────────────────────────────────────────────
class SubtitleWidget(QWidget):
    """Seleção de estilo de legenda, preview, ajustes e fila de vídeos."""

    estilo_selecionado = pyqtSignal(str)  # ID do estilo

    def __init__(self, estilos, preview_renderer=None):
        super().__init__()
        self.estilos = estilos
        self.estilo_atual = None
        self.preview_renderer = preview_renderer
        self.previews_cache = {}  # {estilo_id: {tamanho: caminho}}
        self.preview_thread = None
        self._current_pixmap = None
        self.botoes_estilos: dict[str, StyleTile] = {}
        self.setAcceptDrops(True)
        self.init_ui()
        self._toggle_placeholder()
        self.carregar_previews_existentes()
        if self.estilos:
            self.selecionar_estilo(self.estilos[0])

    # ── UI ──────────────────────────────────────────────────────────────────
    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self._build_library(), 6)
        top.addWidget(self._build_player(), 4)
        top.addWidget(self._build_details(), 3)
        root.addLayout(top, 1)
        root.addWidget(self._build_queue())

    def _build_library(self) -> QWidget:
        card, lay, head = _panel("Estilos de legenda")
        self.lbl_count_estilos = QLabel()
        self.lbl_count_estilos.setObjectName("MutedSmall")
        head.addWidget(self.lbl_count_estilos)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Coluna de navegação: ações + categorias
        nav = QFrame()
        nav.setObjectName("LibraryNav")
        nav.setFixedWidth(168)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(10, 10, 10, 10)
        nl.setSpacing(2)

        acoes = QFrame()
        acoes.setObjectName("LibraryActions")
        al = QVBoxLayout(acoes)
        al.setContentsMargins(4, 4, 4, 4)
        al.setSpacing(4)
        self.btn_add_videos = QPushButton("Adicionar vídeos")
        self.btn_add_videos.setObjectName("LibraryActionPrimary")
        self.btn_add_videos.setIcon(icons.icon("plus", "#60a5fa", 14, 2))
        self.btn_add_videos.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_videos.clicked.connect(self.browse_videos)
        al.addWidget(self.btn_add_videos)
        nl.addWidget(acoes)
        nl.addSpacing(10)

        self._cat_group = QButtonGroup(self)
        self._cat_group.setExclusive(True)
        for cid, nome in CATEGORIAS:
            b = QPushButton(nome)
            b.setObjectName("CategoryButton")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("cat", cid)
            b.clicked.connect(lambda _=False, c=cid: self._filtrar_categoria(c))
            self._cat_group.addButton(b)
            nl.addWidget(b)
            if cid == "todos":
                b.setChecked(True)
        nl.addStretch(1)
        body.addWidget(nav)

        # Grade de estilos
        grid_col = QVBoxLayout()
        grid_col.setContentsMargins(14, 10, 8, 10)
        grid_col.setSpacing(8)
        self.lbl_categoria = QLabel("Todos")
        self.lbl_categoria.setObjectName("LibrarySection")
        grid_col.addWidget(self.lbl_categoria)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tile_grid = _TileGrid()
        tiles = []
        for estilo in self.estilos:
            t = StyleTile(estilo)
            t.clicked.connect(lambda _=False, e=estilo: self.selecionar_estilo(e))
            self.botoes_estilos[estilo.id] = t
            tiles.append(t)
        self.tile_grid.set_tiles(tiles)
        scroll.setWidget(self.tile_grid)
        grid_col.addWidget(scroll, 1)
        body.addLayout(grid_col, 1)

        lay.addLayout(body, 1)
        self._atualizar_contagem()
        card.setMinimumWidth(168 + TILE_W + 40)
        return card

    def _build_player(self) -> QWidget:
        card, lay, head = _panel("Player")
        self.preview_canvas = QLabel("Selecione um estilo")
        self.preview_canvas.setObjectName("PlayerCanvas")
        self.preview_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_canvas.setMinimumSize(240, 135)
        self.preview_canvas.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview_canvas.installEventFilter(self)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(10, 10, 10, 6)
        wrap.addWidget(self.preview_canvas, 1)
        lay.addLayout(wrap, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(14, 0, 14, 10)
        self.lbl_player_estilo = QLabel("")
        self.lbl_player_estilo.setObjectName("PlayerAccent")
        bar.addWidget(self.lbl_player_estilo)
        self.lbl_player_info = QLabel("")
        self.lbl_player_info.setObjectName("MutedSmall")
        bar.addWidget(self.lbl_player_info)
        bar.addStretch(1)
        ratio = QLabel("16:9")
        ratio.setObjectName("RatioPill")
        bar.addWidget(ratio)
        lay.addLayout(bar)
        return card

    def _build_details(self) -> QWidget:
        card, lay, _head = _panel("Detalhes")
        card.setMinimumWidth(210)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        g = QGridLayout(body)
        g.setContentsMargins(14, 12, 14, 12)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        g.setColumnStretch(1, 1)

        def row(i: int, label: str, widget: QWidget):
            lb = QLabel(label)
            lb.setObjectName("DetailLabel")
            g.addWidget(lb, i, 0, Qt.AlignmentFlag.AlignVCenter)
            g.addWidget(widget, i, 1)

        self.det_nome = QLabel("—")
        self.det_categoria = QLabel("—")
        self.det_fonte = QLabel("—")
        self.det_exibicao = QLabel("—")
        for w in (self.det_nome, self.det_categoria, self.det_fonte, self.det_exibicao):
            w.setObjectName("DetailValue")
        row(0, "Estilo", self.det_nome)
        row(1, "Categoria", self.det_categoria)
        row(2, "Fonte", self.det_fonte)
        row(3, "Exibição", self.det_exibicao)

        sep = QFrame()
        sep.setObjectName("DetailSep")
        sep.setFixedHeight(1)
        g.addWidget(sep, 4, 0, 1, 2)

        self.tamanho_combo = QComboBox()
        self.tamanho_combo.addItems([str(s) for s in [12, 18, 24, 28, 32, 36, 40, 44, 48]])
        self.tamanho_combo.setCurrentText("18")
        self.tamanho_combo.currentTextChanged.connect(self.atualizar_tamanho)
        row(5, "Tamanho", self.tamanho_combo)

        self.posicao_combo = QComboBox()
        self.posicao_combo.addItems(["Embaixo", "Centro", "Topo"])
        self.posicao_combo.currentTextChanged.connect(lambda _: self.atualizar_preview(force=True))
        row(6, "Posição", self.posicao_combo)

        self.btn_cor = QPushButton("#FFFFFF")
        self.btn_cor.setObjectName("SwatchButton")
        self.btn_cor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cor.clicked.connect(self.selecionar_cor)
        row(7, "Cor do texto", self.btn_cor)

        self.lbl_cor_borda = QLabel("Cor da borda")
        self.lbl_cor_borda.setObjectName("DetailLabel")
        self.btn_cor_borda = QPushButton("#000000")
        self.btn_cor_borda.setObjectName("SwatchButton")
        self.btn_cor_borda.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cor_borda.clicked.connect(self.selecionar_cor_borda)
        g.addWidget(self.lbl_cor_borda, 8, 0)
        g.addWidget(self.btn_cor_borda, 8, 1)
        g.setRowStretch(9, 1)

        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        self._action_slot = QVBoxLayout()
        self._action_slot.setContentsMargins(14, 8, 14, 14)
        lay.addLayout(self._action_slot)
        return card

    def set_action_button(self, btn: QPushButton):
        """Encaixa o botão de processar (dono: MainWindow) no rodapé de Detalhes."""
        self._action_slot.addWidget(btn)

    def _build_queue(self) -> QWidget:
        card = QFrame()
        card.setObjectName("EditorPanel")
        card.setFixedHeight(150)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("EditorPanelHead")
        bar.setFixedHeight(40)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 12, 0)
        bl.setSpacing(2)
        bl.addWidget(_icon_button("plus", "Adicionar vídeos", self.browse_videos))
        self.btn_remove_videos = _icon_button("trash-2", "Remover selecionados",
                                              self.remove_selected_videos)
        bl.addWidget(self.btn_remove_videos)
        div = QFrame()
        div.setObjectName("ToolbarDivider")
        div.setFixedSize(1, 18)
        bl.addSpacing(4)
        bl.addWidget(div)
        bl.addSpacing(4)
        self.btn_check_all = _icon_button("square-check", "Marcar todos", self.check_all_videos)
        self.btn_uncheck_all = _icon_button("square", "Desmarcar todos", self.uncheck_all_videos)
        bl.addWidget(self.btn_check_all)
        bl.addWidget(self.btn_uncheck_all)
        bl.addSpacing(8)
        t = QLabel("Fila de vídeos")
        t.setObjectName("EditorPanelTitle")
        bl.addWidget(t)
        bl.addStretch(1)
        self.lbl_fila_info = QLabel("")
        self.lbl_fila_info.setObjectName("MutedSmall")
        bl.addWidget(self.lbl_fila_info)
        lay.addWidget(bar)

        track = QHBoxLayout()
        track.setContentsMargins(10, 10, 10, 10)
        track.setSpacing(10)
        lane = QLabel()
        lane.setPixmap(icons.pixmap("video", "#52525b", 16))
        lane.setFixedWidth(22)
        lane.setAlignment(Qt.AlignmentFlag.AlignCenter)
        track.addWidget(lane)

        self.video_list = QListWidget()
        self.video_list.setObjectName("QueueTrack")
        self.video_list.setFlow(QListView.Flow.LeftToRight)
        self.video_list.setWrapping(False)
        self.video_list.setSpacing(3)
        self.video_list.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.video_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.video_list.itemChanged.connect(lambda _: self._atualizar_fila_info())
        track.addWidget(self.video_list, 1)

        self.lbl_no_videos = QLabel("Arraste vídeos para cá ou clique em +")
        self.lbl_no_videos.setObjectName("QueueEmpty")
        self.lbl_no_videos.setAlignment(Qt.AlignmentFlag.AlignCenter)
        track.addWidget(self.lbl_no_videos, 1)
        lay.addLayout(track, 1)
        return card

    # ── Biblioteca ──────────────────────────────────────────────────────────
    def _filtrar_categoria(self, cat: str):
        for estilo_id, tile in self.botoes_estilos.items():
            tile.filtrado = cat != "todos" and tile.estilo.categoria != cat
        self.lbl_categoria.setText(dict(CATEGORIAS)[cat])
        self.tile_grid.set_tiles(self.tile_grid.tiles)
        self._atualizar_contagem()

    def _atualizar_contagem(self):
        n = sum(1 for t in self.botoes_estilos.values() if not t.filtrado)
        self.lbl_count_estilos.setText(f"{n} estilos")

    # ── Fila de vídeos ──────────────────────────────────────────────────────
    def _toggle_placeholder(self):
        has_items = self.video_list.count() > 0
        self.video_list.setVisible(has_items)
        self.lbl_no_videos.setVisible(not has_items)
        self._atualizar_fila_info()

    def _atualizar_fila_info(self):
        total = self.video_list.count()
        marcados = len(self.get_selected_videos())
        self.lbl_fila_info.setText(f"{marcados}/{total} marcados" if total else "")

    def browse_videos(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Vídeos para Legendar", "",
            "Arquivos de Vídeo (*.mp4 *.mov *.avi *.mkv *.webm *.wmv *.flv *.m4v)",
        )
        self._adicionar_caminhos(caminhos)

    def _adicionar_caminhos(self, caminhos):
        existentes = {self.video_list.item(i).data(Qt.ItemDataRole.UserRole)
                      for i in range(self.video_list.count())}
        for c in caminhos:
            if c not in existentes:
                self._add_video_item(c)
                existentes.add(c)
        self._toggle_placeholder()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        caminhos = [u.toLocalFile() for u in e.mimeData().urls()
                    if Path(u.toLocalFile()).suffix.lower() in VIDEO_EXTS]
        self._adicionar_caminhos(caminhos)

    def remove_selected_videos(self):
        for item in self.video_list.selectedItems():
            self.video_list.takeItem(self.video_list.row(item))
        self._toggle_placeholder()

    def _add_video_item(self, text: str):
        """Adiciona um clipe (checkável) à trilha da fila."""
        item = QListWidgetItem()
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        item.setToolTip(text)
        p = Path(text)
        item.setText(text if "://" in text else p.name)
        item.setData(Qt.ItemDataRole.UserRole, text)
        item.setSizeHint(QSize(220, 64))
        self.video_list.addItem(item)

    def update_video_list(self, items):
        self.video_list.clear()
        for item in items:
            self._add_video_item(str(item))
        self._toggle_placeholder()

    def get_selected_videos(self):
        """Retorna os caminhos marcados na fila."""
        return [self.video_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.video_list.count())
                if self.video_list.item(i).checkState() == Qt.CheckState.Checked]

    def check_all_videos(self):
        for i in range(self.video_list.count()):
            self.video_list.item(i).setCheckState(Qt.CheckState.Checked)

    def uncheck_all_videos(self):
        for i in range(self.video_list.count()):
            self.video_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    # ── Previews em disco ───────────────────────────────────────────────────
    def carregar_previews_existentes(self):
        """Indexa previews já renderizados ({estilo}_size{N}...png) do cache."""
        from config.paths import CACHE_DIR
        preview_dir = CACHE_DIR / "previews"
        if not preview_dir.exists():
            return
        for f in preview_dir.glob("*.png"):
            if "_size" not in f.stem:
                continue
            estilo_id, resto = f.stem.split("_size", 1)
            try:
                tamanho = int(resto.split("_")[0])
            except ValueError:
                continue
            self.previews_cache.setdefault(estilo_id, {})[tamanho] = str(f)
        self.atualizar_icones_botoes()

    def atualizar_icones_botoes(self):
        """Redesenha os tiles (cores podem ter mudado)."""
        for tile in self.botoes_estilos.values():
            tile.update()

    # ── Seleção / ajustes ───────────────────────────────────────────────────
    def selecionar_estilo(self, estilo):
        self.estilo_atual = estilo
        self.estilo_selecionado.emit(estilo.id)
        for eid, tile in self.botoes_estilos.items():
            tile.setChecked(eid == estilo.id)

        if getattr(estilo, "size_options", None):
            self.tamanho_combo.blockSignals(True)
            self.tamanho_combo.clear()
            self.tamanho_combo.addItems([str(s) for s in estilo.size_options])
            preferido = 18
            if preferido not in estilo.size_options:
                preferido = min(estilo.size_options, key=lambda s: abs(s - 18))
            estilo.tamanho = preferido
            self.tamanho_combo.setCurrentText(str(preferido))
            self.tamanho_combo.blockSignals(False)

        self.det_nome.setText(estilo.nome)
        self.det_categoria.setText(str(estilo.categoria).capitalize())
        self.det_fonte.setText(estilo.fonte)
        self.det_exibicao.setText(EXIBICAO.get(estilo.tipo_exibicao, estilo.tipo_exibicao))
        self.lbl_player_estilo.setText(estilo.nome)

        self._pintar_swatch(self.btn_cor, QColor(ass_para_hex(estilo.cor_primaria)))
        tem_borda = getattr(estilo, "borda_espessura", 0) > 0 or estilo.id == "neon_glow"
        self._pintar_swatch(self.btn_cor_borda, QColor(ass_para_hex(estilo.cor_borda, "#000000")))
        self.btn_cor_borda.setVisible(tem_borda)
        self.lbl_cor_borda.setVisible(tem_borda)
        self.atualizar_preview()

    @staticmethod
    def _pintar_swatch(btn: QPushButton, cor: QColor):
        pm = QPixmap(14, 14)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(cor)
        p.drawRoundedRect(QRectF(0.5, 0.5, 13, 13), 3, 3)
        p.end()
        btn.setIcon(QIcon(pm))
        btn.setIconSize(QSize(14, 14))
        btn.setText(cor.name().upper())

    def atualizar_tamanho(self, texto):
        if self.estilo_atual and texto.isdigit():
            self.estilo_atual.tamanho = int(texto)
            self.atualizar_preview()

    def selecionar_cor(self):
        if not self.estilo_atual:
            return
        atual = QColor(ass_para_hex(self.estilo_atual.cor_primaria))
        nova = QColorDialog.getColor(atual, self, "Selecione a Cor do Texto")
        if nova.isValid():
            self.estilo_atual.cor_primaria = hex_para_ass(nova)
            self._pintar_swatch(self.btn_cor, nova)
            self.atualizar_icones_botoes()
            self.atualizar_preview(force=True)

    def selecionar_cor_borda(self):
        if not self.estilo_atual:
            return
        atual = QColor(ass_para_hex(self.estilo_atual.cor_borda, "#000000"))
        nova = QColorDialog.getColor(atual, self, "Selecione a Cor da Borda")
        if nova.isValid():
            self.estilo_atual.cor_borda = hex_para_ass(nova)
            self._pintar_swatch(self.btn_cor_borda, nova)
            self.atualizar_icones_botoes()
            self.atualizar_preview(force=True)

    # ── Player ──────────────────────────────────────────────────────────────
    def atualizar_preview(self, force=False):
        if not self.estilo_atual:
            self.preview_canvas.setText("Selecione um estilo de legenda")
            return
        tamanho = self.estilo_atual.tamanho
        posicao = self.posicao_combo.currentText()
        self.lbl_player_info.setText(f"· {tamanho}px · {posicao}")
        if not self.preview_renderer:
            self.preview_canvas.setText(self.estilo_atual.nome)
            return
        if self._current_pixmap is None:
            self.preview_canvas.setText("Gerando preview...")
        # Thread anterior: só descarta o resultado (ver SinglePreviewGeneratorThread).
        if self.preview_thread and self.preview_thread.isRunning():
            self.preview_thread.discard()
            try:
                self.preview_thread.preview_ready.disconnect(self._on_preview_ready)
            except (TypeError, RuntimeError):
                pass
        self.preview_thread = SinglePreviewGeneratorThread(
            self.preview_renderer, self.estilo_atual, tamanho, force=force, posicao=posicao,
        )
        self.preview_thread.preview_ready.connect(self._on_preview_ready)
        self.preview_thread.start()

    def _exibir_pixmap(self, pixmap):
        cw = max(self.preview_canvas.width() - 4, 160)
        ch = max(self.preview_canvas.height() - 4, 90)
        self.preview_canvas.setPixmap(pixmap.scaled(
            cw, ch, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self._current_pixmap = pixmap

    def eventFilter(self, obj, event):
        # Reescala no resize do próprio canvas (o layout assenta depois do widget).
        if obj is self.preview_canvas and event.type() == event.Type.Resize and self._current_pixmap:
            self._exibir_pixmap(self._current_pixmap)
        return super().eventFilter(obj, event)

    def _on_preview_ready(self, path):
        if not self.estilo_atual:
            return
        self.previews_cache.setdefault(self.estilo_atual.id, {})[self.estilo_atual.tamanho] = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self._exibir_pixmap(pixmap)

    def recarregar_previews(self):
        self.carregar_previews_existentes()
        if self.estilo_atual:
            self.atualizar_preview()

    def get_estilo_atual(self):
        return self.estilo_atual
