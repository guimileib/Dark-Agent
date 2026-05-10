"""Editor Widget — overlay editor for placing text/images on video with timing."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from config.paths import TEMP_DIR
from core.overlay_renderer import OverlayRenderer
from models.overlay import OverlayElemento, OverlayTemplate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Render thread
# ---------------------------------------------------------------------------

class OverlayRenderThread(QThread):
    progresso = pyqtSignal(str)
    concluido = pyqtSignal(bool, str)  # success, path_or_error

    def __init__(self, video_path: Path, elementos: list[OverlayElemento], output_path: Path):
        super().__init__()
        self.video_path = video_path
        self.elementos = elementos
        self.output_path = output_path

    def run(self):
        self.progresso.emit("Renderizando overlays...")
        renderer = OverlayRenderer()
        ok = renderer.renderizar(self.video_path, self.elementos, self.output_path)
        if ok:
            self.concluido.emit(True, str(self.output_path))
        else:
            self.concluido.emit(False, "Falha na renderizacao. Verifique os logs.")


class FrameExtractThread(QThread):
    frame_ready = pyqtSignal(str)  # path to PNG

    def __init__(self, video_path: Path, timestamp: float, output_path: Path):
        super().__init__()
        self.video_path = video_path
        self.timestamp = timestamp
        self.output_path = output_path

    def run(self):
        renderer = OverlayRenderer()
        if renderer.extrair_frame(self.video_path, self.timestamp, self.output_path):
            self.frame_ready.emit(str(self.output_path))


# ---------------------------------------------------------------------------
# Position grid helper
# ---------------------------------------------------------------------------

_POSITION_LABELS = {
    (0, 0): ("top_left",      "TL"),
    (0, 1): ("top_center",    "TC"),
    (0, 2): ("top_right",     "TR"),
    (1, 0): ("center_left",   "CL"),
    (1, 1): ("center",        "C"),
    (1, 2): ("center_right",  "CR"),
    (2, 0): ("bottom_left",   "BL"),
    (2, 1): ("bottom_center", "BC"),
    (2, 2): ("bottom_right",  "BR"),
}


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class EditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._elementos: list[OverlayElemento] = []
        self._current_idx: int = -1
        self._video_path: Path | None = None
        self._render_thread: OverlayRenderThread | None = None
        self._frame_thread: FrameExtractThread | None = None
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self._frame_tmp = TEMP_DIR / "darkagent_editor_frame.png"
        self._updating_ui = False  # guard against feedback loops
        self._init_ui()

    # ==================================================================
    # UI Construction
    # ==================================================================

    def _init_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(8, 8, 8, 8)

        # ── LEFT PANEL ───────────────────────────────────────────────
        left = QFrame()
        left.setObjectName("GlassContainer")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(20, 16, 20, 20)
        left_lay.setSpacing(12)

        # Video selector
        lbl_video = QLabel("Video de Origem")
        lbl_video.setObjectName("SectionTitle")
        left_lay.addWidget(lbl_video)

        vid_row = QHBoxLayout()
        vid_row.setSpacing(8)
        self._lbl_video = QLabel("Nenhum video selecionado")
        self._lbl_video.setStyleSheet("color: #64748b; font-size: 12px; background: transparent;")
        self._lbl_video.setWordWrap(True)
        vid_row.addWidget(self._lbl_video, 1)
        btn_browse = QPushButton("Selecionar")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.clicked.connect(self._browse_video)
        vid_row.addWidget(btn_browse)
        left_lay.addLayout(vid_row)

        # Separator
        left_lay.addWidget(self._sep())

        # Element list
        lbl_elems = QLabel("Elementos")
        lbl_elems.setObjectName("SectionTitle")
        left_lay.addWidget(lbl_elems)

        self._elem_list = QListWidget()
        self._elem_list.setMinimumHeight(160)
        self._elem_list.currentRowChanged.connect(self._on_element_selected)
        left_lay.addWidget(self._elem_list)

        elem_btn = QHBoxLayout()
        elem_btn.setSpacing(6)

        btn_add_txt = QPushButton("+ Texto")
        btn_add_txt.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_txt.setStyleSheet(self._btn_accent_style())
        btn_add_txt.clicked.connect(lambda: self._add_element("texto"))
        elem_btn.addWidget(btn_add_txt)

        btn_add_img = QPushButton("+ Imagem")
        btn_add_img.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_img.setStyleSheet(self._btn_accent_style())
        btn_add_img.clicked.connect(lambda: self._add_element("imagem"))
        elem_btn.addWidget(btn_add_img)

        btn_dup = QPushButton("Duplicar")
        btn_dup.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dup.setStyleSheet(self._btn_secondary_style())
        btn_dup.clicked.connect(self._duplicate_element)
        elem_btn.addWidget(btn_dup)

        btn_remove = QPushButton("Remover")
        btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_remove.setStyleSheet(self._btn_danger_style())
        btn_remove.clicked.connect(self._remove_element)
        elem_btn.addWidget(btn_remove)

        left_lay.addLayout(elem_btn)

        # Separator
        left_lay.addWidget(self._sep())

        # Templates
        lbl_tpl = QLabel("Templates")
        lbl_tpl.setObjectName("SectionTitle")
        left_lay.addWidget(lbl_tpl)

        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(8)
        btn_save = QPushButton("Salvar Template")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(self._btn_secondary_style())
        btn_save.clicked.connect(self._save_template)
        tpl_row.addWidget(btn_save)

        btn_load = QPushButton("Carregar Template")
        btn_load.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_load.setStyleSheet(self._btn_secondary_style())
        btn_load.clicked.connect(self._load_template)
        tpl_row.addWidget(btn_load)
        left_lay.addLayout(tpl_row)

        left_lay.addStretch()
        root.addWidget(left, 4)

        # ── RIGHT PANEL ──────────────────────────────────────────────
        right = QFrame()
        right.setObjectName("GlassContainer")
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        right_inner = QWidget()
        right_inner.setStyleSheet("background: transparent;")
        right_lay = QVBoxLayout(right_inner)
        right_lay.setContentsMargins(20, 16, 20, 20)
        right_lay.setSpacing(14)

        # -- Frame preview --
        lbl_preview = QLabel("Preview")
        lbl_preview.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_preview)

        self._preview_canvas = QLabel("Selecione um video e um elemento")
        self._preview_canvas.setMinimumHeight(180)
        self._preview_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_canvas.setStyleSheet("""
            QLabel {
                background: rgba(15, 23, 42, 0.6);
                border-radius: 14px;
                border: 1.5px solid rgba(59, 130, 246, 0.2);
                color: #64748b;
                font-size: 13px;
            }
        """)
        right_lay.addWidget(self._preview_canvas)

        # -- Properties form --
        lbl_props = QLabel("Propriedades")
        lbl_props.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_props)

        self._props_container = QWidget()
        self._props_container.setStyleSheet("background: transparent;")
        self._props_layout = QVBoxLayout(self._props_container)
        self._props_layout.setContentsMargins(0, 0, 0, 0)
        self._props_layout.setSpacing(10)

        # Type
        row_type = QHBoxLayout()
        row_type.addWidget(self._lbl("Tipo:"))
        self._combo_type = QComboBox()
        self._combo_type.addItems(["Texto", "Imagem"])
        self._combo_type.currentTextChanged.connect(self._on_type_changed)
        row_type.addWidget(self._combo_type, 1)
        self._props_layout.addLayout(row_type)

        # Timing
        row_time = QHBoxLayout()
        row_time.addWidget(self._lbl("Inicio (s):"))
        self._spin_start = QDoubleSpinBox()
        self._spin_start.setRange(0, 99999)
        self._spin_start.setDecimals(1)
        self._spin_start.setSingleStep(0.5)
        self._spin_start.valueChanged.connect(self._on_prop_changed)
        row_time.addWidget(self._spin_start)
        row_time.addWidget(self._lbl("Fim (s):"))
        self._spin_end = QDoubleSpinBox()
        self._spin_end.setRange(0, 99999)
        self._spin_end.setDecimals(1)
        self._spin_end.setSingleStep(0.5)
        self._spin_end.setValue(5.0)
        self._spin_end.valueChanged.connect(self._on_prop_changed)
        row_time.addWidget(self._spin_end)
        self._props_layout.addLayout(row_time)

        # Position grid
        self._props_layout.addWidget(self._lbl("Posicao:"))
        self._build_position_grid()
        self._props_layout.addLayout(self._pos_grid_layout)

        # Custom X/Y (hidden by default)
        self._custom_pos_row = QHBoxLayout()
        self._custom_pos_row_widget = QWidget()
        cxy = QHBoxLayout(self._custom_pos_row_widget)
        cxy.setContentsMargins(0, 0, 0, 0)
        cxy.addWidget(self._lbl("X:"))
        self._spin_x = QSpinBox()
        self._spin_x.setRange(0, 9999)
        self._spin_x.valueChanged.connect(self._on_prop_changed)
        cxy.addWidget(self._spin_x)
        cxy.addWidget(self._lbl("Y:"))
        self._spin_y = QSpinBox()
        self._spin_y.setRange(0, 9999)
        self._spin_y.valueChanged.connect(self._on_prop_changed)
        cxy.addWidget(self._spin_y)
        self._custom_pos_row_widget.setVisible(False)
        self._props_layout.addWidget(self._custom_pos_row_widget)

        # ── Text properties group ────────────────────────────────────
        self._group_text = QWidget()
        self._group_text.setStyleSheet("background: transparent;")
        gt = QVBoxLayout(self._group_text)
        gt.setContentsMargins(0, 0, 0, 0)
        gt.setSpacing(8)

        gt.addWidget(self._lbl("Conteudo:"))
        self._txt_content = QLineEdit()
        self._txt_content.setPlaceholderText("Texto do overlay...")
        self._txt_content.textChanged.connect(self._on_prop_changed)
        gt.addWidget(self._txt_content)

        row_font = QHBoxLayout()
        row_font.addWidget(self._lbl("Fonte:"))
        self._combo_font = QComboBox()
        self._combo_font.addItems(["Arial", "Impact", "Verdana", "Calibri", "Trebuchet MS", "Courier New"])
        self._combo_font.currentTextChanged.connect(self._on_prop_changed)
        row_font.addWidget(self._combo_font, 1)
        row_font.addWidget(self._lbl("Tamanho:"))
        self._spin_fontsize = QSpinBox()
        self._spin_fontsize.setRange(8, 200)
        self._spin_fontsize.setValue(48)
        self._spin_fontsize.valueChanged.connect(self._on_prop_changed)
        row_font.addWidget(self._spin_fontsize)
        self._chk_bold = QCheckBox("Bold")
        self._chk_bold.setChecked(True)
        self._chk_bold.toggled.connect(self._on_prop_changed)
        row_font.addWidget(self._chk_bold)
        gt.addLayout(row_font)

        row_colors = QHBoxLayout()
        self._btn_cor_texto = QPushButton("Cor Texto")
        self._btn_cor_texto.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cor_texto.clicked.connect(self._pick_text_color)
        row_colors.addWidget(self._btn_cor_texto)
        self._btn_cor_borda = QPushButton("Cor Borda")
        self._btn_cor_borda.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cor_borda.clicked.connect(self._pick_border_color)
        row_colors.addWidget(self._btn_cor_borda)
        row_colors.addWidget(self._lbl("Espessura:"))
        self._spin_border = QSpinBox()
        self._spin_border.setRange(0, 20)
        self._spin_border.setValue(2)
        self._spin_border.valueChanged.connect(self._on_prop_changed)
        row_colors.addWidget(self._spin_border)
        gt.addLayout(row_colors)
        self._props_layout.addWidget(self._group_text)

        # ── Image properties group ───────────────────────────────────
        self._group_image = QWidget()
        self._group_image.setStyleSheet("background: transparent;")
        gi = QVBoxLayout(self._group_image)
        gi.setContentsMargins(0, 0, 0, 0)
        gi.setSpacing(8)

        row_img = QHBoxLayout()
        self._lbl_img_path = QLabel("Nenhuma imagem")
        self._lbl_img_path.setStyleSheet("color: #64748b; font-size: 12px; background: transparent;")
        row_img.addWidget(self._lbl_img_path, 1)
        btn_browse_img = QPushButton("Selecionar Imagem")
        btn_browse_img.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_img.clicked.connect(self._browse_image)
        row_img.addWidget(btn_browse_img)
        gi.addLayout(row_img)

        row_img2 = QHBoxLayout()
        row_img2.addWidget(self._lbl("Largura (px):"))
        self._spin_img_w = QSpinBox()
        self._spin_img_w.setRange(0, 9999)
        self._spin_img_w.setValue(200)
        self._spin_img_w.setSpecialValueText("Original")
        self._spin_img_w.valueChanged.connect(self._on_prop_changed)
        row_img2.addWidget(self._spin_img_w)
        row_img2.addWidget(self._lbl("Opacidade:"))
        self._slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self._slider_opacity.setRange(0, 100)
        self._slider_opacity.setValue(100)
        self._slider_opacity.valueChanged.connect(self._on_prop_changed)
        row_img2.addWidget(self._slider_opacity)
        self._lbl_opacity_val = QLabel("100%")
        self._lbl_opacity_val.setFixedWidth(40)
        self._lbl_opacity_val.setStyleSheet("color: #94a3b8; font-size: 12px; background: transparent;")
        row_img2.addWidget(self._lbl_opacity_val)
        gi.addLayout(row_img2)

        self._group_image.setVisible(False)
        self._props_layout.addWidget(self._group_image)

        right_lay.addWidget(self._props_container)

        # -- Render button --
        right_lay.addWidget(self._sep())

        self._btn_render = QPushButton("RENDERIZAR VIDEO")
        self._btn_render.setObjectName("ProcessButton")
        self._btn_render.setMinimumHeight(52)
        self._btn_render.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_render.clicked.connect(self._render)
        right_lay.addWidget(self._btn_render)

        self._lbl_status = QLabel("")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setStyleSheet("color: #94a3b8; font-size: 12px; background: transparent;")
        right_lay.addWidget(self._lbl_status)

        right_lay.addStretch()

        right_scroll.setWidget(right_inner)
        right_container_lay = QVBoxLayout(right)
        right_container_lay.setContentsMargins(0, 0, 0, 0)
        right_container_lay.addWidget(right_scroll)
        root.addWidget(right, 6)

        # Initial state
        self._props_container.setEnabled(False)

    # ==================================================================
    # Position grid builder
    # ==================================================================

    def _build_position_grid(self):
        self._pos_grid_layout = QGridLayout()
        self._pos_grid_layout.setSpacing(4)
        self._pos_btn_group = QButtonGroup(self)
        self._pos_btn_group.setExclusive(True)
        self._pos_buttons: dict[str, QPushButton] = {}

        _style = """
            QPushButton {
                background: rgba(15, 23, 42, 0.6);
                color: #94a3b8;
                border: 1.5px solid rgba(51, 65, 85, 0.5);
                border-radius: 8px;
                font-size: 11px;
                font-weight: 700;
                min-width: 38px; min-height: 32px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.15);
                border-color: rgba(59, 130, 246, 0.4);
                color: #e2e8f0;
            }
            QPushButton:checked {
                background: rgba(59, 130, 246, 0.25);
                border: 2px solid #3b82f6;
                color: #60a5fa;
            }
        """

        for (r, c), (preset, label) in _POSITION_LABELS.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_style)
            btn.setProperty("preset", preset)
            btn.clicked.connect(lambda _, p=preset: self._on_pos_changed(p))
            self._pos_btn_group.addButton(btn)
            self._pos_grid_layout.addWidget(btn, r, c)
            self._pos_buttons[preset] = btn

        # Custom button below the grid
        btn_custom = QPushButton("Custom X/Y")
        btn_custom.setCheckable(True)
        btn_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_custom.setStyleSheet(_style)
        btn_custom.setProperty("preset", "custom")
        btn_custom.clicked.connect(lambda: self._on_pos_changed("custom"))
        self._pos_btn_group.addButton(btn_custom)
        self._pos_grid_layout.addWidget(btn_custom, 3, 0, 1, 3)
        self._pos_buttons["custom"] = btn_custom

        # Default
        self._pos_buttons["bottom_center"].setChecked(True)

    # ==================================================================
    # Style helpers
    # ==================================================================

    @staticmethod
    def _sep() -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet("background: rgba(255,255,255,0.06); max-height: 1px; border: none;")
        return s

    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600; background: transparent;")
        return l

    @staticmethod
    def _btn_accent_style() -> str:
        return """
            QPushButton {
                background: #3b82f6; color: white; border: none; border-radius: 10px;
                padding: 8px 14px; font-size: 12px; font-weight: 700;
            }
            QPushButton:hover { background: #2563eb; }
            QPushButton:pressed { background: #1d4ed8; }
        """

    @staticmethod
    def _btn_secondary_style() -> str:
        return """
            QPushButton {
                background: rgba(15,23,42,0.5); color: #94a3b8;
                border: 1.5px solid rgba(51,65,85,0.5); border-radius: 10px;
                padding: 8px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton:hover { background: rgba(51,65,85,0.5); color: #e2e8f0; border-color: rgba(59,130,246,0.3); }
        """

    @staticmethod
    def _btn_danger_style() -> str:
        return """
            QPushButton {
                background: rgba(239,68,68,0.15); color: #fca5a5;
                border: 1px solid rgba(239,68,68,0.3); border-radius: 10px;
                padding: 8px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton:hover { background: rgba(239,68,68,0.3); }
        """

    def _update_color_btn(self, btn: QPushButton, hex_color: str, label: str):
        c = QColor(hex_color)
        fg = "#000000" if c.lightness() > 128 else "#ffffff"
        btn.setText(f"{label}: {hex_color}")
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {hex_color}; color: {fg};
                border: 2px solid rgba(255,255,255,0.3); border-radius: 10px;
                padding: 8px; font-weight: 700; font-size: 12px;
            }}
            QPushButton:hover {{ border-color: #3b82f6; }}
        """)

    # ==================================================================
    # Element management
    # ==================================================================

    def _add_element(self, tipo: str):
        elem = OverlayElemento(tipo=tipo)
        self._elementos.append(elem)
        self._refresh_list()
        self._elem_list.setCurrentRow(len(self._elementos) - 1)

    def _duplicate_element(self):
        if self._current_idx < 0:
            return
        import copy
        original = self._elementos[self._current_idx]
        clone = copy.deepcopy(original)
        clone.id = str(__import__("uuid").uuid4())[:8]
        self._elementos.append(clone)
        self._refresh_list()
        self._elem_list.setCurrentRow(len(self._elementos) - 1)

    def _remove_element(self):
        if self._current_idx < 0:
            return
        self._elementos.pop(self._current_idx)
        self._current_idx = -1
        self._refresh_list()
        self._props_container.setEnabled(False)

    def _refresh_list(self):
        self._elem_list.clear()
        for elem in self._elementos:
            item = QListWidgetItem(str(elem))
            self._elem_list.addItem(item)

    # ==================================================================
    # Property binding (UI ↔ model)
    # ==================================================================

    def _on_element_selected(self, row: int):
        self._current_idx = row
        if row < 0 or row >= len(self._elementos):
            self._props_container.setEnabled(False)
            return
        self._props_container.setEnabled(True)
        self._load_props(self._elementos[row])
        self._request_frame_preview()

    def _load_props(self, elem: OverlayElemento):
        """Populate the property form from an OverlayElemento."""
        self._updating_ui = True

        self._combo_type.setCurrentText("Texto" if elem.tipo == "texto" else "Imagem")
        self._spin_start.setValue(elem.inicio)
        self._spin_end.setValue(elem.fim)

        # Position
        preset = elem.posicao_preset
        btn = self._pos_buttons.get(preset)
        if btn:
            btn.setChecked(True)
        self._custom_pos_row_widget.setVisible(preset == "custom")
        self._spin_x.setValue(elem.x_custom)
        self._spin_y.setValue(elem.y_custom)

        # Text
        self._txt_content.setText(elem.texto)
        idx = self._combo_font.findText(elem.fonte, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self._combo_font.setCurrentIndex(idx)
        self._spin_fontsize.setValue(elem.tamanho_fonte)
        self._chk_bold.setChecked(elem.bold)
        self._spin_border.setValue(elem.borda_espessura)
        self._update_color_btn(self._btn_cor_texto, elem.cor_texto, "Cor Texto")
        self._update_color_btn(self._btn_cor_borda, elem.cor_borda, "Cor Borda")

        # Image
        self._lbl_img_path.setText(Path(elem.caminho_imagem).name if elem.caminho_imagem else "Nenhuma imagem")
        self._spin_img_w.setValue(elem.largura_imagem)
        self._slider_opacity.setValue(int(elem.opacidade * 100))
        self._lbl_opacity_val.setText(f"{int(elem.opacidade * 100)}%")

        # Show/hide groups
        is_text = elem.tipo == "texto"
        self._group_text.setVisible(is_text)
        self._group_image.setVisible(not is_text)

        self._updating_ui = False

    def _on_prop_changed(self, *_):
        """Write current form values back into the selected element."""
        if self._updating_ui or self._current_idx < 0:
            return
        elem = self._elementos[self._current_idx]

        elem.tipo = "texto" if self._combo_type.currentText() == "Texto" else "imagem"
        elem.inicio = self._spin_start.value()
        elem.fim = self._spin_end.value()
        elem.x_custom = self._spin_x.value()
        elem.y_custom = self._spin_y.value()

        # Text
        elem.texto = self._txt_content.text()
        elem.fonte = self._combo_font.currentText()
        elem.tamanho_fonte = self._spin_fontsize.value()
        elem.bold = self._chk_bold.isChecked()
        elem.borda_espessura = self._spin_border.value()

        # Image
        elem.largura_imagem = self._spin_img_w.value()
        elem.opacidade = self._slider_opacity.value() / 100.0
        self._lbl_opacity_val.setText(f"{self._slider_opacity.value()}%")

        # Refresh list text
        item = self._elem_list.item(self._current_idx)
        if item:
            item.setText(str(elem))

    def _on_type_changed(self, text: str):
        is_text = text == "Texto"
        self._group_text.setVisible(is_text)
        self._group_image.setVisible(not is_text)
        self._on_prop_changed()

    def _on_pos_changed(self, preset: str):
        self._custom_pos_row_widget.setVisible(preset == "custom")
        if self._current_idx >= 0:
            self._elementos[self._current_idx].posicao_preset = preset
            self._on_prop_changed()

    # ==================================================================
    # Color pickers
    # ==================================================================

    def _pick_text_color(self):
        if self._current_idx < 0:
            return
        elem = self._elementos[self._current_idx]
        color = QColorDialog.getColor(QColor(elem.cor_texto), self, "Cor do Texto")
        if color.isValid():
            elem.cor_texto = color.name()
            self._update_color_btn(self._btn_cor_texto, elem.cor_texto, "Cor Texto")

    def _pick_border_color(self):
        if self._current_idx < 0:
            return
        elem = self._elementos[self._current_idx]
        color = QColorDialog.getColor(QColor(elem.cor_borda), self, "Cor da Borda")
        if color.isValid():
            elem.cor_borda = color.name()
            self._update_color_btn(self._btn_cor_borda, elem.cor_borda, "Cor Borda")

    # ==================================================================
    # File browsers
    # ==================================================================

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Video", "",
            "Videos (*.mp4 *.mov *.avi *.mkv *.webm *.wmv *.flv *.m4v)",
        )
        if path:
            self._video_path = Path(path)
            self._lbl_video.setText(self._video_path.name)
            self._lbl_video.setStyleSheet("color: #22c55e; font-size: 12px; font-weight: 600; background: transparent;")
            self._request_frame_preview()

    def _browse_image(self):
        if self._current_idx < 0:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Imagem", "",
            "Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.svg)",
        )
        if path:
            self._elementos[self._current_idx].caminho_imagem = path
            self._lbl_img_path.setText(Path(path).name)
            self._lbl_img_path.setStyleSheet("color: #22c55e; font-size: 12px; font-weight: 600; background: transparent;")

    # ==================================================================
    # Frame preview
    # ==================================================================

    def _request_frame_preview(self):
        if not self._video_path or not self._video_path.exists():
            return
        ts = self._spin_start.value() if self._current_idx >= 0 else 0.0
        if self._frame_thread and self._frame_thread.isRunning():
            return  # Don't stack requests
        self._frame_thread = FrameExtractThread(self._video_path, ts, self._frame_tmp)
        self._frame_thread.frame_ready.connect(self._on_frame_ready)
        self._frame_thread.start()

    def _on_frame_ready(self, path: str):
        pix = QPixmap(path)
        if not pix.isNull():
            scaled = pix.scaled(
                self._preview_canvas.width(), self._preview_canvas.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_canvas.setPixmap(scaled)

    # ==================================================================
    # Templates
    # ==================================================================

    def _save_template(self):
        if not self._elementos:
            QMessageBox.warning(self, "Aviso", "Adicione pelo menos um elemento antes de salvar.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Template", "meu_template.json", "JSON (*.json)",
        )
        if not path:
            return
        tpl = OverlayTemplate(nome=Path(path).stem, elementos=list(self._elementos))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tpl.to_dict(), f, indent=2, ensure_ascii=False)
        self._lbl_status.setText(f"Template salvo: {Path(path).name}")

    def _load_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Carregar Template", "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tpl = OverlayTemplate.from_dict(data)
            self._elementos = tpl.elementos
            self._refresh_list()
            self._current_idx = -1
            self._props_container.setEnabled(False)
            self._lbl_status.setText(f"Template carregado: {tpl.nome} ({len(tpl.elementos)} elementos)")
        except Exception as exc:
            QMessageBox.critical(self, "Erro", f"Falha ao carregar template:\n{exc}")

    # ==================================================================
    # Render
    # ==================================================================

    def _render(self):
        if not self._video_path or not self._video_path.exists():
            QMessageBox.warning(self, "Aviso", "Selecione um video de origem primeiro.")
            return
        if not self._elementos:
            QMessageBox.warning(self, "Aviso", "Adicione pelo menos um elemento.")
            return
        if self._render_thread and self._render_thread.isRunning():
            QMessageBox.warning(self, "Aguarde", "Ja existe uma renderizacao em andamento.")
            return

        # Validate
        for elem in self._elementos:
            if elem.inicio >= elem.fim:
                QMessageBox.warning(self, "Erro", f"Elemento '{elem}' tem inicio >= fim.")
                return
            if elem.tipo == "imagem" and not Path(elem.caminho_imagem).exists():
                QMessageBox.warning(self, "Erro", f"Imagem nao encontrada: {elem.caminho_imagem}")
                return

        # Output path
        out_dir = self._video_path.parent
        out_name = f"{self._video_path.stem}_overlay{self._video_path.suffix}"
        output_path = out_dir / out_name

        self._btn_render.setEnabled(False)
        self._lbl_status.setText("Renderizando...")

        self._render_thread = OverlayRenderThread(self._video_path, list(self._elementos), output_path)
        self._render_thread.progresso.connect(lambda msg: self._lbl_status.setText(msg))
        self._render_thread.concluido.connect(self._on_render_done)
        self._render_thread.start()

    def _on_render_done(self, success: bool, result: str):
        self._btn_render.setEnabled(True)
        if success:
            self._lbl_status.setText(f"Salvo: {Path(result).name}")
            QMessageBox.information(self, "Sucesso", f"Video renderizado:\n{result}")
        else:
            self._lbl_status.setText("Falha na renderizacao")
            QMessageBox.critical(self, "Erro", result)
