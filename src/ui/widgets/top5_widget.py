"""Aba Top 5: gera o ranking (início das músicas ou momentos engraçados), compila e legenda.

Fluxo: fontes → ranking editável (#N → #1) → compilação → revisão do texto → queima da legenda.
"""

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from config.paths import output_subdir, OUTPUT_FINAL, OUTPUT_TEMP
from config.settings import settings
from core.compilation import (
    MAX_CLIPES, MIN_CLIPES, TRANSICOES, SegmentoCompilacao, montar_compilacao,
)
from core.top5 import (
    Momento, aplicar_edicoes, detectar_momentos_engracados, ordem_contagem,
    rotulo_rank,
)

logger = logging.getLogger(__name__)

_VIDEO_FILTER = "Vídeos (*.mp4 *.mov *.mkv *.avi *.webm *.m4v)"
_MOMENTO_ROLE = int(Qt.ItemDataRole.UserRole)
_TITULO_ROLE = int(Qt.ItemDataRole.UserRole) + 1

_LIST_STYLE = """
    QListWidget {
        background-color: rgba(10, 15, 30, 0.9);
        border: 1px solid rgba(59, 130, 246, 0.25);
        border-radius: 10px;
        color: white;
        font-size: 12px;
        outline: none;
    }
    QListWidget::item { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.04); }
    QListWidget::item:selected { background-color: rgba(59, 130, 246, 0.2); }
    QListWidget::item:hover { background-color: rgba(255,255,255,0.05); }
"""


def _mmss(segundos: float) -> str:
    s = int(round(segundos))
    return f"{s // 60:02d}:{s % 60:02d}"


# ----------------------------------------------------------------------
# Threads (padrão do projeto: run() puro, cancelamento via requestInterruption)
# ----------------------------------------------------------------------

class DeteccaoThread(QThread):
    """Roda a heurística de momentos engraçados sobre as fontes."""

    progresso = pyqtSignal(int, str)
    concluido = pyqtSignal(list)  # list[Momento]

    def __init__(self, videos, duracao, quantidade):
        super().__init__()
        self.videos, self.duracao, self.quantidade = videos, duracao, quantidade

    def run(self):
        try:
            momentos = detectar_momentos_engracados(
                self.videos, self.duracao, self.quantidade,
                progress_callback=self.progresso.emit,
                cancelado=self.isInterruptionRequested,
            )
        except Exception as e:
            logger.exception(f"Falha na detecção: {e}")
            momentos = []
        self.concluido.emit(momentos)


class Top5Thread(QThread):
    """Monta a compilação e, se pedido, transcreve o resultado para revisão."""

    progresso = pyqtSignal(int, str)
    compilado = pyqtSignal(str, object)  # caminho, transcrição (None = sem legenda)
    erro = pyqtSignal(str)

    def __init__(self, segmentos, output_path, transcrever: bool, **opcoes):
        super().__init__()
        self.segmentos = segmentos
        self.output_path = output_path
        self.transcrever = transcrever
        self.opcoes = opcoes

    def run(self):
        peso = 70 if self.transcrever else 100
        ok = montar_compilacao(
            self.segmentos,
            self.output_path,
            progress_callback=lambda pct: self.progresso.emit(
                int(pct * peso / 100), "Montando compilação..."
            ),
            **self.opcoes,
        )
        if not ok:
            self.erro.emit("Falha ao montar a compilação. Verifique os logs.")
            return
        if not self.transcrever or self.isInterruptionRequested():
            self.compilado.emit(str(self.output_path), None)
            return

        try:
            from core import Transcriber

            self.progresso.emit(75, "Extraindo áudio...")
            transcriber = Transcriber(
                modelo=settings.whisper_model,
                device=settings.whisper_device,
                idioma=settings.whisper_language,
            )
            audio = output_subdir(settings.output_dir, OUTPUT_TEMP) / f"{self.output_path.stem}.wav"
            if not transcriber.extrair_audio_de_video(self.output_path, audio):
                self.erro.emit("Vídeo montado, mas falhou ao extrair o áudio para a legenda.")
                return
            self.progresso.emit(80, "Transcrevendo com IA...")
            transcricao = transcriber.transcrever(audio)
            audio.unlink(missing_ok=True)
        except Exception as e:
            logger.exception(f"Falha na transcrição do Top 5: {e}")
            self.erro.emit(f"Vídeo montado em {self.output_path}, mas a transcrição falhou: {e}")
            return
        self.progresso.emit(100, "Transcrição pronta — revise o texto.")
        self.compilado.emit(str(self.output_path), transcricao)


class QueimarLegendaThread(QThread):
    """Gera o .ass com o estilo escolhido e queima no vídeo compilado."""

    progresso = pyqtSignal(int)
    concluido = pyqtSignal(bool, str)

    def __init__(self, video, transcricao, estilo, output_path):
        super().__init__()
        self.video, self.transcricao = Path(video), transcricao
        self.estilo, self.output_path = estilo, output_path

    def run(self):
        from core import SubtitleGenerator, VideoEditor

        ass = self.video.with_suffix(".ass")
        if not SubtitleGenerator().gerar_ass(self.transcricao, self.estilo, ass):
            self.concluido.emit(False, "Falha ao gerar o arquivo de legenda.")
            return
        ok = VideoEditor().queimar_legendas(
            self.video, ass, self.output_path,
            progress_callback=lambda pct: self.progresso.emit(int(pct)),
        )
        ass.unlink(missing_ok=True)
        if ok:
            self.concluido.emit(True, str(self.output_path))
        else:
            self.concluido.emit(False, "Falha ao queimar a legenda. Verifique os logs.")


# ----------------------------------------------------------------------
# Revisão da legenda
# ----------------------------------------------------------------------

class LegendaReviewDialog(QDialog):
    """Tabela com o texto transcrito (editável) + escolha do estilo antes de queimar."""

    def __init__(self, transcricao: dict, estilos, estilo_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revisar legenda")
        self.resize(760, 520)
        self.transcricao = transcricao
        self.estilos = estilos

        lay = QVBoxLayout(self)
        dica = QLabel(
            "Corrija o texto direto na tabela. Apagar o texto remove a linha da legenda."
        )
        dica.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lay.addWidget(dica)

        segs = transcricao.get("segmentos", [])
        self.tabela = QTableWidget(len(segs), 3)
        self.tabela.setHorizontalHeaderLabels(["Início", "Fim", "Texto"])
        self.tabela.verticalHeader().setVisible(False)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row, seg in enumerate(segs):
            for col, valor in enumerate((_mmss(seg["inicio"]), _mmss(seg["fim"]))):
                cel = QTableWidgetItem(valor)
                cel.setFlags(cel.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabela.setItem(row, col, cel)
            self.tabela.setItem(row, 2, QTableWidgetItem(seg.get("texto", "")))
        lay.addWidget(self.tabela, 1)

        estilo_row = QHBoxLayout()
        estilo_row.addWidget(QLabel("Estilo:"))
        self.estilo_combo = QComboBox()
        for estilo in estilos:
            self.estilo_combo.addItem(estilo.nome, estilo.id)
        idx = self.estilo_combo.findData(estilo_id)
        if idx >= 0:
            self.estilo_combo.setCurrentIndex(idx)
        estilo_row.addWidget(self.estilo_combo, 1)
        lay.addLayout(estilo_row)

        botoes = QDialogButtonBox()
        botoes.addButton("🔥 Queimar legenda", QDialogButtonBox.ButtonRole.AcceptRole)
        botoes.addButton("Manter sem legenda", QDialogButtonBox.ButtonRole.RejectRole)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        lay.addWidget(botoes)

    def transcricao_editada(self) -> dict:
        textos = [self.tabela.item(r, 2).text() for r in range(self.tabela.rowCount())]
        return aplicar_edicoes(self.transcricao, textos)

    def estilo(self):
        alvo = self.estilo_combo.currentData()
        return next((e for e in self.estilos if e.id == alvo), None)


# ----------------------------------------------------------------------
# Widget
# ----------------------------------------------------------------------

class Top5Widget(QWidget):
    """UI do Top 5 automatizado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._estilos = settings.get_todos_estilos()
        self._init_ui()
        self._on_modo_changed()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Esquerda: modo, fontes e ranking ─────────────────────────────
        left = QFrame()
        left.setObjectName("GlassContainer")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(20, 16, 20, 16)
        left_lay.setSpacing(8)

        titulo = QLabel("🏆  Top 5 Automático")
        titulo.setObjectName("SectionTitle")
        left_lay.addWidget(titulo)

        modo_row = QHBoxLayout()
        self.radio_musicas = QRadioButton("🎵 Músicas (início de cada vídeo)")
        self.radio_engracados = QRadioButton("😂 Momentos engraçados")
        self.radio_musicas.setChecked(True)
        self.radio_musicas.toggled.connect(self._on_modo_changed)
        modo_row.addWidget(self.radio_musicas)
        modo_row.addWidget(self.radio_engracados)
        modo_row.addStretch()
        left_lay.addLayout(modo_row)

        self.dica_modo = QLabel()
        self.dica_modo.setStyleSheet("color: #64748b; font-size: 12px;")
        self.dica_modo.setWordWrap(True)
        left_lay.addWidget(self.dica_modo)

        self.fontes_list = QListWidget()
        self.fontes_list.setStyleSheet(_LIST_STYLE)
        self.fontes_list.setMaximumHeight(130)
        left_lay.addWidget(self.fontes_list)

        fontes_row = QHBoxLayout()
        btn_add = QPushButton("➕ Adicionar Vídeo(s)")
        btn_add.clicked.connect(self._adicionar_fontes)
        fontes_row.addWidget(btn_add, 1)
        btn_rm_fonte = QPushButton("✕")
        btn_rm_fonte.setToolTip("Remover vídeo selecionado")
        btn_rm_fonte.clicked.connect(
            lambda: self.fontes_list.takeItem(self.fontes_list.currentRow())
        )
        fontes_row.addWidget(btn_rm_fonte)
        self.btn_ranking = QPushButton("⚡ Gerar Ranking")
        self.btn_ranking.clicked.connect(self._gerar_ranking)
        fontes_row.addWidget(self.btn_ranking, 1)
        left_lay.addLayout(fontes_row)

        lbl_rank = QLabel("Ranking (ordem do vídeo final: #5 → #1)")
        lbl_rank.setObjectName("SectionTitle")
        left_lay.addWidget(lbl_rank)

        self.rank_list = QListWidget()
        self.rank_list.setStyleSheet(_LIST_STYLE)
        self.rank_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rank_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.rank_list.model().rowsMoved.connect(lambda *_: self._refresh_ranking())
        self.rank_list.currentRowChanged.connect(self._on_rank_selected)
        left_lay.addWidget(self.rank_list, 1)

        rank_btns = QHBoxLayout()
        for texto, tooltip, handler in (
            ("⬆", "Mover para cima", lambda: self._mover(-1)),
            ("⬇", "Mover para baixo", lambda: self._mover(1)),
            ("✕ Remover", "Remover do ranking", self._remover_rank),
        ):
            btn = QPushButton(texto)
            btn.setToolTip(tooltip)
            btn.clicked.connect(handler)
            rank_btns.addWidget(btn, 1 if texto.startswith("✕") else 0)
        left_lay.addLayout(rank_btns)

        # Ajuste fino do item selecionado
        edit_row = QHBoxLayout()
        self.titulo_edit = QLineEdit()
        self.titulo_edit.setPlaceholderText("Título (ex.: nome da música)")
        self.titulo_edit.textEdited.connect(self._on_item_editado)
        edit_row.addWidget(self.titulo_edit, 3)
        self.item_inicio = QDoubleSpinBox()
        self.item_inicio.setRange(0, 36000)
        self.item_inicio.setDecimals(1)
        self.item_inicio.setPrefix("início ")
        self.item_inicio.setSuffix(" s")
        self.item_inicio.valueChanged.connect(self._on_item_editado)
        edit_row.addWidget(self.item_inicio, 2)
        self.item_dur = QDoubleSpinBox()
        self.item_dur.setRange(2, 600)
        self.item_dur.setDecimals(1)
        self.item_dur.setPrefix("dur. ")
        self.item_dur.setSuffix(" s")
        self.item_dur.valueChanged.connect(self._on_item_editado)
        edit_row.addWidget(self.item_dur, 2)
        left_lay.addLayout(edit_row)

        root.addWidget(left, 5)

        # ── Direita: parâmetros e ação ───────────────────────────────────
        right = QFrame()
        right.setObjectName("GlassContainer")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(20, 16, 20, 16)
        right_lay.setSpacing(8)

        lbl_cortes = QLabel("Cortes")
        lbl_cortes.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_cortes)

        cortes_row = QHBoxLayout()
        self.qtd_spin = QSpinBox()
        self.qtd_spin.setRange(MIN_CLIPES, MAX_CLIPES)
        self.qtd_spin.setValue(MAX_CLIPES)
        self.qtd_spin.setPrefix("Top ")
        cortes_row.addWidget(self.qtd_spin, 1)
        self.inicio_spin = QDoubleSpinBox()
        self.inicio_spin.setRange(0, 600)
        self.inicio_spin.setDecimals(0)
        self.inicio_spin.setPrefix("a partir de ")
        self.inicio_spin.setSuffix(" s")
        cortes_row.addWidget(self.inicio_spin, 2)
        self.dur_spin = QDoubleSpinBox()
        self.dur_spin.setRange(3, 120)
        self.dur_spin.setDecimals(0)
        self.dur_spin.setSuffix(" s cada")
        cortes_row.addWidget(self.dur_spin, 2)
        right_lay.addLayout(cortes_row)

        self.chk_rotulos = QCheckBox("Rótulos #5 … #1 no topo")
        self.chk_rotulos.setChecked(True)
        right_lay.addWidget(self.chk_rotulos)

        lbl_trans = QLabel("Transição")
        lbl_trans.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_trans)
        trans_row = QHBoxLayout()
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

        self.formato_combo = QComboBox()
        self.formato_combo.addItem("9:16 — TikTok / Shorts (1080×1920)", (1080, 1920))
        self.formato_combo.addItem("16:9 — YouTube (1920×1080)", (1920, 1080))
        right_lay.addWidget(self.formato_combo)

        lbl_leg = QLabel("Legenda")
        lbl_leg.setObjectName("SectionTitle")
        right_lay.addWidget(lbl_leg)
        self.chk_legenda = QCheckBox("Transcrever e legendar (revisa o texto antes)")
        self.chk_legenda.setChecked(True)
        right_lay.addWidget(self.chk_legenda)
        self.estilo_combo = QComboBox()
        for estilo in self._estilos:
            self.estilo_combo.addItem(estilo.nome, estilo.id)
        self.chk_legenda.toggled.connect(self.estilo_combo.setEnabled)
        right_lay.addWidget(self.estilo_combo)

        right_lay.addStretch()

        self.btn_gerar = QPushButton("🎬  Gerar Top 5")
        self.btn_gerar.setMinimumHeight(48)
        self.btn_gerar.setStyleSheet("""
            QPushButton {
                font-size: 14px; font-weight: bold; color: white; border: none;
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c3aed, stop:1 #3b82f6);
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6d28d9, stop:1 #2563eb);
            }
            QPushButton:disabled { background: #334155; color: #64748b; }
        """)
        self.btn_gerar.clicked.connect(self._gerar_video)
        right_lay.addWidget(self.btn_gerar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setVisible(False)
        self.btn_cancelar.clicked.connect(self._cancelar)
        right_lay.addWidget(self.btn_cancelar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        right_lay.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.status_label.setWordWrap(True)
        right_lay.addWidget(self.status_label)

        for btn in (btn_add, btn_rm_fonte, self.btn_ranking, self.btn_gerar, self.btn_cancelar):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        root.addWidget(right, 4)

    def _musicas(self) -> bool:
        return self.radio_musicas.isChecked()

    def _on_modo_changed(self, *_):
        if self._musicas():
            self.dica_modo.setText(
                "Adicione um vídeo por música, do #1 (primeiro da lista) ao último. Cada um "
                "vira um corte dos primeiros segundos; o título sai do nome do arquivo (editável)."
            )
            self.dur_spin.setValue(30)
        else:
            self.dica_modo.setText(
                "Adicione um ou mais vídeos. A detecção procura picos de risada, grito "
                "e aplauso no áudio (offline) — revise e ajuste os cortes antes de gerar."
            )
            self.dur_spin.setValue(12)
        self.inicio_spin.setEnabled(self._musicas())

    # ------------------------------------------------------------------
    # Fontes e ranking
    # ------------------------------------------------------------------

    def _adicionar_fontes(self):
        caminhos, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar vídeos", settings.last_open_dir, _VIDEO_FILTER
        )
        if not caminhos:
            return
        settings.last_open_dir = str(Path(caminhos[0]).parent)
        settings.save_config()
        for caminho in caminhos:
            item = QListWidgetItem(Path(caminho).name)
            item.setData(_MOMENTO_ROLE, caminho)
            item.setToolTip(caminho)
            item.setForeground(QColor("#e2e8f0"))
            self.fontes_list.addItem(item)

    def _fontes(self) -> list[Path]:
        return [
            Path(self.fontes_list.item(i).data(_MOMENTO_ROLE))
            for i in range(self.fontes_list.count())
        ]

    def _gerar_ranking(self):
        fontes = self._fontes()
        qtd = self.qtd_spin.value()
        if not fontes:
            QMessageBox.information(self, "Sem vídeos", "Adicione os vídeos de origem primeiro.")
            return

        if self._musicas():
            if len(fontes) < MIN_CLIPES:
                QMessageBox.warning(self, "Poucos vídeos", f"Adicione pelo menos {MIN_CLIPES} músicas.")
                return
            if len(fontes) > qtd:
                self.status_label.setText(f"Usando os {qtd} primeiros vídeos da lista.")
            # A ordem das fontes é tratada como #1 primeiro; a contagem inverte.
            momentos = [
                Momento(v, self.inicio_spin.value(), self.dur_spin.value(), score=-i)
                for i, v in enumerate(fontes[:qtd])
            ]
            self._preencher_ranking(ordem_contagem(momentos), titulos_do_arquivo=True)
            return

        self._thread = DeteccaoThread(fontes, self.dur_spin.value(), qtd)
        self._thread.progresso.connect(self._on_progresso)
        self._thread.concluido.connect(self._on_deteccao)
        self._set_ocupado(True, "Analisando áudio...")
        self._thread.start()

    def _on_deteccao(self, momentos: list):
        self._finalizar_thread()
        if len(momentos) < MIN_CLIPES:
            self.status_label.setText("❌ Não achei momentos suficientes (vídeos curtos ou mudos?).")
            return
        self._preencher_ranking(ordem_contagem(momentos), titulos_do_arquivo=False)
        self.status_label.setText(
            f"✅ {len(momentos)} momentos encontrados. Arraste para reordenar e ajuste os cortes."
        )

    def _preencher_ranking(self, momentos: list[Momento], titulos_do_arquivo: bool):
        self.rank_list.clear()
        for m in momentos:
            item = QListWidgetItem()
            item.setData(_MOMENTO_ROLE, m)
            item.setData(_TITULO_ROLE, m.video.stem if titulos_do_arquivo else "")
            item.setForeground(QColor("#e2e8f0"))
            self.rank_list.addItem(item)
        self._refresh_ranking()
        self.rank_list.setCurrentRow(0)

    def _refresh_ranking(self):
        total = self.rank_list.count()
        for i in range(total):
            item = self.rank_list.item(i)
            m: Momento = item.data(_MOMENTO_ROLE)
            rotulo = rotulo_rank(i, total, item.data(_TITULO_ROLE) or "")
            item.setText(
                f"{rotulo}\n    {m.video.name}  ·  {_mmss(m.inicio)}–{_mmss(m.inicio + m.duracao)}"
            )
            item.setToolTip(str(m.video))

    def _on_rank_selected(self, row: int):
        item = self.rank_list.item(row) if row >= 0 else None
        for w in (self.titulo_edit, self.item_inicio, self.item_dur):
            w.blockSignals(True)
            w.setEnabled(item is not None)
        if item:
            m: Momento = item.data(_MOMENTO_ROLE)
            self.titulo_edit.setText(item.data(_TITULO_ROLE) or "")
            self.item_inicio.setValue(m.inicio)
            self.item_dur.setValue(m.duracao)
        for w in (self.titulo_edit, self.item_inicio, self.item_dur):
            w.blockSignals(False)

    def _on_item_editado(self, *_):
        item = self.rank_list.currentItem()
        if not item:
            return
        m: Momento = item.data(_MOMENTO_ROLE)
        m.inicio, m.duracao = self.item_inicio.value(), self.item_dur.value()
        item.setData(_MOMENTO_ROLE, m)
        item.setData(_TITULO_ROLE, self.titulo_edit.text())
        self._refresh_ranking()

    def _mover(self, delta: int):
        row = self.rank_list.currentRow()
        novo = row + delta
        if row < 0 or not (0 <= novo < self.rank_list.count()):
            return
        self.rank_list.insertItem(novo, self.rank_list.takeItem(row))
        self.rank_list.setCurrentRow(novo)
        self._refresh_ranking()

    def _remover_rank(self):
        row = self.rank_list.currentRow()
        if row >= 0:
            self.rank_list.takeItem(row)
            self._refresh_ranking()

    # ------------------------------------------------------------------
    # Geração
    # ------------------------------------------------------------------

    def _segmentos(self) -> list[SegmentoCompilacao]:
        total = self.rank_list.count()
        segmentos = []
        for i in range(total):
            item = self.rank_list.item(i)
            m: Momento = item.data(_MOMENTO_ROLE)
            rotulo = rotulo_rank(i, total, item.data(_TITULO_ROLE) or "")
            segmentos.append(SegmentoCompilacao(
                video=m.video,
                rotulo=rotulo if self.chk_rotulos.isChecked() else "",
                inicio=m.inicio,
                duracao=m.duracao,
            ))
        return segmentos

    def _gerar_video(self):
        segmentos = self._segmentos()
        if not (MIN_CLIPES <= len(segmentos) <= MAX_CLIPES):
            QMessageBox.warning(
                self, "Ranking inválido",
                f"Gere o ranking primeiro ({MIN_CLIPES} a {MAX_CLIPES} cortes).",
            )
            return

        legendar = self.chk_legenda.isChecked() and bool(self._estilos)
        nome = f"top{len(segmentos)}_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        # Com legenda, a compilação é intermediária: o final sai da queima.
        destino = OUTPUT_TEMP if legendar else OUTPUT_FINAL
        output = output_subdir(settings.output_dir, destino) / nome

        self._thread = Top5Thread(
            segmentos, output, legendar,
            transicao=self.trans_combo.currentData(),
            dur_transicao=self.trans_dur.value(),
            resolucao=self.formato_combo.currentData(),
        )
        self._thread.progresso.connect(self._on_progresso)
        self._thread.compilado.connect(self._on_compilado)
        self._thread.erro.connect(self._on_erro)
        self._set_ocupado(True, "Montando compilação...")
        self._thread.start()

    def _on_compilado(self, caminho: str, transcricao):
        self._finalizar_thread()
        if transcricao is None:
            self._sucesso(caminho)
            return

        dialog = LegendaReviewDialog(
            transcricao, self._estilos, self.estilo_combo.currentData(), self
        )
        final = output_subdir(settings.output_dir, OUTPUT_FINAL) / Path(caminho).name
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.estilo():
            Path(caminho).replace(final)
            self._sucesso(str(final))
            return

        self._thread = QueimarLegendaThread(
            caminho, dialog.transcricao_editada(), dialog.estilo(), final
        )
        self._thread.progresso.connect(lambda pct: self._on_progresso(pct, "Queimando legenda..."))
        self._thread.concluido.connect(
            lambda ok, info: self._on_queimado(ok, info, Path(caminho))
        )
        self._set_ocupado(True, "Queimando legenda...")
        self._thread.start()

    def _on_queimado(self, ok: bool, info: str, intermediario: Path):
        self._finalizar_thread()
        if ok:
            intermediario.unlink(missing_ok=True)
            self._sucesso(info)
        else:
            self._on_erro(f"{info}\nA versão sem legenda ficou em: {intermediario}")

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def _set_ocupado(self, ocupado: bool, msg: str = ""):
        for w in (self.btn_gerar, self.btn_ranking):
            w.setEnabled(not ocupado)
        self.btn_cancelar.setVisible(ocupado)
        self.progress.setVisible(ocupado)
        if ocupado:
            self.progress.setValue(0)
            self.status_label.setText(msg)

    def _on_progresso(self, pct: int, msg: str = ""):
        self.progress.setValue(pct)
        if msg:
            self.status_label.setText(msg)

    def _finalizar_thread(self):
        if self._thread:
            self._thread.wait()
            self._thread = None
        self._set_ocupado(False)

    def _cancelar(self):
        if self._thread:
            # Interrompe entre etapas; um encode do FFmpeg em andamento vai até o fim.
            self._thread.requestInterruption()
            self.status_label.setText("Cancelando após a etapa atual...")

    def _on_erro(self, msg: str):
        self._finalizar_thread()
        self.status_label.setText(f"❌ {msg}")
        QMessageBox.critical(self, "Erro", msg)

    def _sucesso(self, caminho: str):
        self.status_label.setText(f"✅ Salvo em: {caminho}")
        QMessageBox.information(self, "Top 5 pronto! 🎉", f"Vídeo salvo em:\n{caminho}")
