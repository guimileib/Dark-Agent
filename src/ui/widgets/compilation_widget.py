"""Widget de compilação — monta vídeos "Adivinhe a Música" / rankings.

Fluxo: usuário adiciona 2–5 clipes (um por música / momento), define rótulo
opcional por clipe, escolhe o PNG do canal e a transição; o widget junta
tudo via core.compilation e salva em output/final.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
    QWidget,
)

from config.paths import output_subdir, OUTPUT_FINAL
from config.settings import settings
from core.compilation import (
    MAX_CLIPES, MIN_CLIPES, TRANSICOES, SegmentoCompilacao, montar_compilacao,
)

_PATH_ROLE = int(Qt.ItemDataRole.UserRole)
_ROTULO_ROLE = int(Qt.ItemDataRole.UserRole) + 1

_VIDEO_FILTER = "Vídeos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)"


class CompilacaoThread(QThread):
    """Renderiza a compilação em background (padrão do projeto: run() puro)."""

    progresso = pyqtSignal(int)
    concluido = pyqtSignal(bool, str)  # sucesso, caminho_ou_erro

    def __init__(self, segmentos, output_path, **opcoes):
        super().__init__()
        self.segmentos = segmentos
        self.output_path = output_path
        self.opcoes = opcoes

    def run(self):
        ok = montar_compilacao(
            self.segmentos,
            self.output_path,
            progress_callback=lambda pct: self.progresso.emit(int(pct)),
            **self.opcoes,
        )
        if ok:
            self.concluido.emit(True, str(self.output_path))
        else:
            self.concluido.emit(False, "Falha ao montar a compilação. Verifique os logs.")


class CompilationWidget(QWidget):
    """UI do montador de compilações."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: CompilacaoThread | None = None
        self._init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Painel esquerdo: clipes ──────────────────────────────────────
        left = QFrame()
        left.setObjectName("GlassContainer")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(20, 16, 20, 16)
        left_lay.setSpacing(10)

        titulo = QLabel("🎵  Clipes da Compilação")
        titulo.setObjectName("SectionTitle")
        left_lay.addWidget(titulo)

        subtitulo = QLabel(
            f"Adicione de {MIN_CLIPES} a {MAX_CLIPES} vídeos (3 a 5 recomendado) — "
            "um por música ou momento. A ordem da lista é a ordem no vídeo final."
        )
        subtitulo.setStyleSheet("color: #64748b; font-size: 12px;")
        subtitulo.setWordWrap(True)
        left_lay.addWidget(subtitulo)

        self.clip_list = QListWidget()
        self.clip_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.clip_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(10, 15, 30, 0.9);
                border: 1px solid rgba(59, 130, 246, 0.25);
                border-radius: 10px;
                color: white;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }
            QListWidget::item:selected { background-color: rgba(59, 130, 246, 0.2); }
            QListWidget::item:hover { background-color: rgba(255,255,255,0.05); }
        """)
        left_lay.addWidget(self.clip_list, 1)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.btn_add = QPushButton("➕ Adicionar Vídeo(s)")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._adicionar_clipes)
        row1.addWidget(self.btn_add, 1)

        self.btn_rotulo = QPushButton("🏷 Rótulo")
        self.btn_rotulo.setToolTip('Texto queimado no topo do clipe (ex.: "Música 1", "#3")')
        self.btn_rotulo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rotulo.clicked.connect(self._editar_rotulo)
        row1.addWidget(self.btn_rotulo)
        left_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        for texto, tooltip, handler in (
            ("⬆", "Mover para cima", lambda: self._mover(-1)),
            ("⬇", "Mover para baixo", lambda: self._mover(1)),
            ("✕ Remover", "Remover clipe selecionado", self._remover),
        ):
            btn = QPushButton(texto)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(handler)
            row2.addWidget(btn, 1 if texto.startswith("✕") else 0)
        left_lay.addLayout(row2)

        root.addWidget(left, 5)

        # ── Painel direito: logo, transição, formato, ação ───────────────
        right = QFrame()
        right.setObjectName("GlassContainer")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(20, 16, 20, 16)
        right_lay.setSpacing(10)

        lbl_logo = QLabel("Logo do Canal (PNG)")
        lbl_logo.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_logo)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)
        self.logo_edit = QLineEdit()
        self.logo_edit.setReadOnly(True)
        self.logo_edit.setPlaceholderText("Opcional — fica visível o vídeo inteiro")
        logo_row.addWidget(self.logo_edit, 1)
        self.btn_logo = QPushButton("Escolher...")
        self.btn_logo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logo.clicked.connect(self._escolher_logo)
        logo_row.addWidget(self.btn_logo)
        self.logo_preview = QLabel()
        self.logo_preview.setFixedSize(42, 42)
        self.logo_preview.setScaledContents(True)
        logo_row.addWidget(self.logo_preview)
        right_lay.addLayout(logo_row)

        logo_opts = QHBoxLayout()
        logo_opts.setSpacing(8)
        self.logo_pos_combo = QComboBox()
        self.logo_pos_combo.addItem("Topo Direita", "top_right")
        self.logo_pos_combo.addItem("Topo Esquerda", "top_left")
        self.logo_pos_combo.addItem("Embaixo Direita", "bottom_right")
        self.logo_pos_combo.addItem("Embaixo Esquerda", "bottom_left")
        logo_opts.addWidget(self.logo_pos_combo, 1)
        self.logo_tam_combo = QComboBox()
        self.logo_tam_combo.addItem("Pequeno", 0.10)
        self.logo_tam_combo.addItem("Médio", 0.14)
        self.logo_tam_combo.addItem("Grande", 0.20)
        self.logo_tam_combo.setCurrentIndex(1)
        logo_opts.addWidget(self.logo_tam_combo, 1)
        right_lay.addLayout(logo_opts)

        lbl_trans = QLabel("Transição entre Clipes")
        lbl_trans.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_trans)

        trans_row = QHBoxLayout()
        trans_row.setSpacing(8)
        self.trans_combo = QComboBox()
        for chave, label in TRANSICOES.items():
            self.trans_combo.addItem(label, chave)
        trans_row.addWidget(self.trans_combo, 2)
        self.trans_dur = QDoubleSpinBox()
        self.trans_dur.setRange(0.2, 2.0)
        self.trans_dur.setSingleStep(0.1)
        self.trans_dur.setValue(0.5)
        self.trans_dur.setSuffix(" s")
        trans_row.addWidget(self.trans_dur, 1)
        right_lay.addLayout(trans_row)

        lbl_fmt = QLabel("Formato")
        lbl_fmt.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_fmt)

        self.formato_combo = QComboBox()
        self.formato_combo.addItem("9:16 — TikTok / Shorts (1080×1920)", (1080, 1920))
        self.formato_combo.addItem("16:9 — YouTube (1920×1080)", (1920, 1080))
        right_lay.addWidget(self.formato_combo)

        right_lay.addStretch()

        self.btn_montar = QPushButton("🎬  Montar Compilação")
        self.btn_montar.setMinimumHeight(48)
        self.btn_montar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_montar.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c3aed, stop:1 #3b82f6);
                color: white;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6d28d9, stop:1 #2563eb);
            }
            QPushButton:disabled { background: #334155; color: #64748b; }
        """)
        self.btn_montar.clicked.connect(self._montar)
        right_lay.addWidget(self.btn_montar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        right_lay.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.status_label.setWordWrap(True)
        right_lay.addWidget(self.status_label)

        root.addWidget(right, 4)

    # ------------------------------------------------------------------
    # Clipes
    # ------------------------------------------------------------------

    def _refresh_item(self, item: QListWidgetItem):
        idx = self.clip_list.row(item) + 1
        nome = Path(item.data(_PATH_ROLE)).name
        rotulo = item.data(_ROTULO_ROLE) or ""
        texto = f"{idx}.  {nome}"
        if rotulo:
            texto += f"   🏷 {rotulo}"
        item.setText(texto)
        item.setToolTip(item.data(_PATH_ROLE))

    def _refresh_todos(self):
        for i in range(self.clip_list.count()):
            self._refresh_item(self.clip_list.item(i))

    def _adicionar_clipes(self):
        vagas = MAX_CLIPES - self.clip_list.count()
        if vagas <= 0:
            QMessageBox.information(
                self, "Limite", f"Máximo de {MAX_CLIPES} clipes por compilação."
            )
            return
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar clipes", settings.last_open_dir, _VIDEO_FILTER
        )
        if not caminhos:
            return
        settings.last_open_dir = str(Path(caminhos[0]).parent)
        settings.save_config()
        for caminho in caminhos[:vagas]:
            item = QListWidgetItem()
            item.setData(_PATH_ROLE, caminho)
            item.setData(_ROTULO_ROLE, "")
            item.setForeground(QColor("#e2e8f0"))
            self.clip_list.addItem(item)
        if len(caminhos) > vagas:
            QMessageBox.information(
                self, "Limite",
                f"Só {vagas} vaga(s) — os demais vídeos foram ignorados."
            )
        self._refresh_todos()

    def _editar_rotulo(self):
        item = self.clip_list.currentItem()
        if not item:
            self.status_label.setText("Selecione um clipe para definir o rótulo.")
            return
        atual = item.data(_ROTULO_ROLE) or ""
        texto, ok = QInputDialog.getText(
            self, "Rótulo do clipe",
            'Texto queimado no topo (ex.: "Música 1", "#3 lugar"). Vazio remove:',
            text=atual,
        )
        if ok:
            item.setData(_ROTULO_ROLE, texto.strip())
            self._refresh_item(item)

    def _mover(self, delta: int):
        row = self.clip_list.currentRow()
        if row < 0:
            return
        novo = row + delta
        if not (0 <= novo < self.clip_list.count()):
            return
        item = self.clip_list.takeItem(row)
        self.clip_list.insertItem(novo, item)
        self.clip_list.setCurrentRow(novo)
        self._refresh_todos()

    def _remover(self):
        row = self.clip_list.currentRow()
        if row >= 0:
            self.clip_list.takeItem(row)
            self._refresh_todos()

    # ------------------------------------------------------------------
    # Logo
    # ------------------------------------------------------------------

    def _escolher_logo(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Logo do canal", settings.last_open_dir, "Imagens (*.png)"
        )
        if caminho:
            self.logo_edit.setText(caminho)
            self.logo_preview.setPixmap(QPixmap(caminho))

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _segmentos(self) -> list[SegmentoCompilacao]:
        return [
            SegmentoCompilacao(
                video=Path(self.clip_list.item(i).data(_PATH_ROLE)),
                rotulo=self.clip_list.item(i).data(_ROTULO_ROLE) or "",
            )
            for i in range(self.clip_list.count())
        ]

    def _montar(self):
        segmentos = self._segmentos()
        if len(segmentos) < MIN_CLIPES:
            QMessageBox.warning(
                self, "Poucos clipes",
                f"Adicione pelo menos {MIN_CLIPES} clipes (3 a 5 recomendado).",
            )
            return

        final_dir = output_subdir(settings.output_dir, OUTPUT_FINAL)
        output = final_dir / f"compilacao_{datetime.now():%Y%m%d_%H%M%S}.mp4"

        logo = self.logo_edit.text().strip()
        self._thread = CompilacaoThread(
            segmentos,
            output,
            logo_path=Path(logo) if logo else None,
            logo_pos=self.logo_pos_combo.currentData(),
            logo_frac=self.logo_tam_combo.currentData(),
            transicao=self.trans_combo.currentData(),
            dur_transicao=self.trans_dur.value(),
            resolucao=self.formato_combo.currentData(),
        )
        self._thread.progresso.connect(self.progress.setValue)
        self._thread.concluido.connect(self._on_concluido)

        self.btn_montar.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setText("Montando compilação... isso pode levar alguns minutos.")
        self._thread.start()

    def _on_concluido(self, sucesso: bool, info: str):
        if self._thread:
            self._thread.wait()
        self.btn_montar.setEnabled(True)
        self.progress.setVisible(False)
        if sucesso:
            self.status_label.setText(f"✅ Salvo em: {info}")
            QMessageBox.information(
                self, "Compilação pronta! 🎉", f"Vídeo salvo em:\n{info}"
            )
        else:
            self.status_label.setText(f"❌ {info}")
            QMessageBox.critical(self, "Erro", info)
