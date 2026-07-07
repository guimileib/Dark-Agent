"""Widget principal de download"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QComboBox, QLabel, QFileDialog, QFrame,
    QListWidget, QListWidgetItem, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor
from pathlib import Path


_MARKER_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class DownloadWidget(QWidget):
    """Widget para configurar e iniciar download"""

    download_iniciado = pyqtSignal(list, str, Path)         # lista_urls, qualidade, pasta
    download_video_apenas = pyqtSignal(list, str, Path)     # baixar apenas (sem legendas)
    download_e_legendar = pyqtSignal(list, str, Path)       # NOVO: baixar + legendar fluxo completo

    def __init__(self):
        super().__init__()
        self._loading_marker = False
        self.init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        container = QFrame()
        container.setObjectName("GlassContainer")
        container_layout = QVBoxLayout(container)
        # Compacto de propósito: o conteúdo inteiro (até os botões de ação)
        # precisa caber na janela padrão sem depender do scroll do tab.
        container_layout.setSpacing(10)
        container_layout.setContentsMargins(24, 18, 24, 18)

        # ── Título ──────────────────────────────────────────────────────
        url_label = QLabel("URLs dos Vídeos")
        url_label.setObjectName("SectionTitle")
        container_layout.addWidget(url_label)

        url_subtitle = QLabel("Digite o link e pressione Enter para adicionar à fila")
        url_subtitle.setStyleSheet("color: #64748b; font-size: 12px; margin-bottom: 4px;")
        container_layout.addWidget(url_subtitle)

        # ── Campo de entrada (URL única, Enter adiciona) ─────────────────
        entry_row = QHBoxLayout()
        entry_row.setSpacing(8)

        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("📺 Cole ou digite o link (YouTube, TikTok, etc)...")
        self.url_entry.setMinimumHeight(40)
        self.url_entry.setStyleSheet("""
            QLineEdit {
                background-color: rgba(15, 23, 42, 0.8);
                color: white;
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-radius: 10px;
                padding: 0 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
                background-color: rgba(15, 23, 42, 0.95);
            }
        """)
        self.url_entry.returnPressed.connect(self._add_url_from_entry)
        entry_row.addWidget(self.url_entry, 1)

        self.btn_add_url = QPushButton("+ Adicionar")
        self.btn_add_url.setMinimumHeight(40)
        self.btn_add_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_url.setStyleSheet("""
            QPushButton {
                background-color: rgba(59, 130, 246, 0.25);
                color: #93c5fd;
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-radius: 10px;
                padding: 0 18px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(59, 130, 246, 0.45); color: white; }
            QPushButton:pressed { background-color: #3b82f6; }
        """)
        self.btn_add_url.clicked.connect(self._add_url_from_entry)
        entry_row.addWidget(self.btn_add_url)

        container_layout.addLayout(entry_row)

        # ── Lista de URLs com checkbox ────────────────────────────────────
        list_header = QHBoxLayout()
        lbl_fila = QLabel("Fila de Downloads")
        lbl_fila.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")
        list_header.addWidget(lbl_fila)
        list_header.addStretch()

        self.btn_clear_list = QPushButton("🗑 Limpar")
        self.btn_clear_list.setFixedHeight(26)
        self.btn_clear_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_list.setStyleSheet("""
            QPushButton {
                background-color: rgba(239,68,68,0.15);
                color: #fca5a5;
                border: 1px solid rgba(239,68,68,0.3);
                border-radius: 6px;
                padding: 0 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: rgba(239,68,68,0.3); }
        """)
        self.btn_clear_list.clicked.connect(self._clear_url_list)
        list_header.addWidget(self.btn_clear_list)

        self.btn_remove_url = QPushButton("✕ Remover")
        self.btn_remove_url.setFixedHeight(26)
        self.btn_remove_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_url.setStyleSheet("""
            QPushButton {
                background-color: rgba(100,116,139,0.15);
                color: #94a3b8;
                border: 1px solid rgba(100,116,139,0.3);
                border-radius: 6px;
                padding: 0 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: rgba(100,116,139,0.3); }
        """)
        self.btn_remove_url.clicked.connect(self._remove_selected_urls)
        list_header.addWidget(self.btn_remove_url)

        container_layout.addLayout(list_header)

        self.url_list = QListWidget()
        self.url_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Altura fixa: adicionar links rola DENTRO da lista, nunca empurra
        # nem sobrepõe os campos abaixo (Qualidade / Pasta de Saída).
        self.url_list.setFixedHeight(150)
        self.url_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(10, 15, 30, 0.9);
                border: 1px solid rgba(59, 130, 246, 0.25);
                border-radius: 10px;
                color: white;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }
            QListWidget::item:selected {
                background-color: rgba(59, 130, 246, 0.2);
            }
            QListWidget::item:hover {
                background-color: rgba(255,255,255,0.05);
            }
            QListWidget::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
            }
            QListWidget::indicator:checked {
                background-color: #3b82f6;
                border: 1px solid #60a5fa;
            }
            QListWidget::indicator:unchecked {
                background-color: rgba(20,30,50,0.9);
                border: 1px solid rgba(100,116,139,0.5);
            }
        """)

        # Placeholder quando vazio
        self._empty_item = QListWidgetItem("  Nenhum link adicionado ainda...")
        self._empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self._empty_item.setForeground(QColor("#475569"))
        self.url_list.addItem(self._empty_item)

        container_layout.addWidget(self.url_list)

        # ── Configurações: Qualidade + Pasta ─────────────────────────────
        grid_config = QHBoxLayout()
        grid_config.setSpacing(20)

        qualidade_group = QVBoxLayout()
        qualidade_group.setSpacing(6)
        qualidade_label = QLabel("Qualidade")
        qualidade_label.setObjectName("SectionTitle")
        qualidade_group.addWidget(qualidade_label)

        self.qualidade_combo = QComboBox()
        self.qualidade_combo.addItems(["1080p", "720p", "480p", "360p"])
        self.qualidade_combo.setCurrentText("720p")
        self.qualidade_combo.setMinimumHeight(38)
        qualidade_group.addWidget(self.qualidade_combo)
        grid_config.addLayout(qualidade_group, 1)

        pasta_group = QVBoxLayout()
        pasta_group.setSpacing(6)
        pasta_label = QLabel("Pasta de Saída")
        pasta_label.setObjectName("SectionTitle")
        pasta_group.addWidget(pasta_label)

        pasta_input_layout = QHBoxLayout()
        pasta_input_layout.setSpacing(8)

        try:
            from config.settings import settings
        except ImportError:
            from src.config.settings import settings

        self.pasta_label = QLineEdit(str(settings.output_dir))
        self.pasta_label.setReadOnly(True)
        self.pasta_label.setMinimumHeight(38)
        pasta_input_layout.addWidget(self.pasta_label)

        self.btn_pasta = QPushButton("Escolher...")
        self.btn_pasta.setMinimumHeight(38)
        self.btn_pasta.clicked.connect(self.escolher_pasta)
        pasta_input_layout.addWidget(self.btn_pasta)

        pasta_group.addLayout(pasta_input_layout)
        grid_config.addLayout(pasta_group, 2)

        container_layout.addLayout(grid_config)

        # ── Marcador permanente (por vídeo) ──────────────────────────────
        marker_label = QLabel("Marcador no Vídeo (Por Vídeo)")
        marker_label.setObjectName("SectionTitle")
        container_layout.addWidget(marker_label)

        self.marker_status_label = QLabel("Selecione um vídeo da fila para configurar seu marcador.")
        self.marker_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic; margin-bottom: 2px;")
        container_layout.addWidget(self.marker_status_label)

        marker_row = QHBoxLayout()
        marker_row.setSpacing(8)

        self.marker_entry = QLineEdit()
        self.marker_entry.setPlaceholderText("Ex.: Episódio 1 — selecione um vídeo na fila")
        self.marker_entry.setMinimumHeight(38)
        self.marker_entry.setEnabled(False)
        self.marker_entry.setStyleSheet("""
            QLineEdit {
                background-color: rgba(15, 23, 42, 0.8);
                color: white;
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-radius: 10px;
                padding: 0 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
                background-color: rgba(15, 23, 42, 0.95);
            }
        """)
        marker_row.addWidget(self.marker_entry, 2)

        self.marker_pos_combo = QComboBox()
        self.marker_pos_combo.addItem("Topo Direita",     "top_right")
        self.marker_pos_combo.addItem("Topo Centro",      "top_center")
        self.marker_pos_combo.addItem("Topo Esquerda",    "top_left")
        self.marker_pos_combo.addItem("Embaixo Direita",  "bottom_right")
        self.marker_pos_combo.addItem("Embaixo Centro",   "bottom_center")
        self.marker_pos_combo.addItem("Embaixo Esquerda", "bottom_left")
        self.marker_pos_combo.setMinimumHeight(38)
        self.marker_pos_combo.setEnabled(False)
        marker_row.addWidget(self.marker_pos_combo, 1)

        container_layout.addLayout(marker_row)

        # Sinais: editar marcador grava no(s) item(s) selecionado(s);
        # mudar seleção carrega o marcador correspondente nos campos.
        self.marker_entry.textChanged.connect(self._on_marker_edited)
        self.marker_pos_combo.currentIndexChanged.connect(self._on_marker_edited)
        self.url_list.itemSelectionChanged.connect(self._on_url_selection_changed)

        # ── Botões de ação ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        # Botão: apenas baixar
        self.btn_baixar = QPushButton("⬇  Baixar (Sem Legendas)")
        self.btn_baixar.setMinimumHeight(46)
        self.btn_baixar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_baixar.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                background-color: rgba(59,130,246,0.25);
                color: #93c5fd;
                border: 1px solid rgba(59,130,246,0.45);
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: rgba(59,130,246,0.45);
                color: white;
            }
            QPushButton:pressed { background-color: #3b82f6; color: white; }
            QPushButton:disabled { opacity: 0.4; color: #64748b; }
        """)
        self.btn_baixar.clicked.connect(self.on_baixar_clicked)
        btn_row.addWidget(self.btn_baixar, 1)

        # Botão: baixar + legendar (NOVO — destaque visual)
        self.btn_baixar_legendar = QPushButton("⚡  Baixar + Legendar")
        self.btn_baixar_legendar.setMinimumHeight(46)
        self.btn_baixar_legendar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_baixar_legendar.setStyleSheet("""
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
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5b21b6, stop:1 #1d4ed8);
            }
            QPushButton:disabled { opacity: 0.4; }
        """)
        self.btn_baixar_legendar.clicked.connect(self.on_baixar_legendar_clicked)
        btn_row.addWidget(self.btn_baixar_legendar, 2)

        container_layout.addLayout(btn_row)

        layout.addWidget(container)
        layout.addStretch()
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Gestão de URLs
    # ------------------------------------------------------------------

    def _add_url_from_entry(self):
        """Pega texto do campo, adiciona à lista e limpa o campo"""
        url = self.url_entry.text().strip()
        if not url:
            return
        self._append_url(url)
        self.url_entry.clear()
        self.url_entry.setFocus()

    def _append_url(self, url: str):
        """Adiciona URL à lista com visual de 'marcado para download'"""
        # Remover placeholder se for o primeiro item real
        if self.url_list.count() == 1 and self.url_list.item(0) is self._empty_item:
            self.url_list.takeItem(0)

        # Verificar duplicatas
        for i in range(self.url_list.count()):
            existing = self.url_list.item(i)
            if existing.data(Qt.ItemDataRole.UserRole) == url:
                # Flash o item existente para indicar duplicata
                existing.setForeground(QColor("#f59e0b"))
                return

        # Criar item com checkbox marcado
        item = QListWidgetItem()
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        item.setData(Qt.ItemDataRole.UserRole, url)
        item.setData(_MARKER_ROLE, None)
        item.setForeground(QColor("#e2e8f0"))

        self._refresh_item_display(item)

        self.url_list.addItem(item)
        self.url_list.scrollToBottom()

    def _refresh_item_display(self, item: QListWidgetItem):
        """Atualiza o texto do item refletindo URL e marcador (se houver)."""
        url = item.data(Qt.ItemDataRole.UserRole) or ""
        marker = item.data(_MARKER_ROLE)

        display = url if len(url) <= 55 else url[:52] + "..."
        text = f"🔗  {display}"
        if marker and marker.get("text"):
            tag = marker["text"]
            tag_short = tag if len(tag) <= 22 else tag[:19] + "..."
            text += f"   🏷 {tag_short}"
        item.setText(text)

        tooltip = url
        if marker and marker.get("text"):
            pos_label = self._position_label(marker.get("position", "top_right"))
            tooltip += f"\n\nMarcador: \"{marker['text']}\" ({pos_label})"
        item.setToolTip(tooltip)

    def _position_label(self, key: str) -> str:
        """Retorna o label legível de uma chave de posição."""
        for i in range(self.marker_pos_combo.count()):
            if self.marker_pos_combo.itemData(i) == key:
                return self.marker_pos_combo.itemText(i)
        return key

    def _selectable_selected_items(self) -> list[QListWidgetItem]:
        """Itens reais (não placeholder) atualmente selecionados."""
        return [
            it for it in self.url_list.selectedItems()
            if it.flags() & Qt.ItemFlag.ItemIsUserCheckable
        ]

    def _on_url_selection_changed(self):
        """Carrega o marcador do(s) item(s) selecionado(s) nos campos do editor."""
        items = self._selectable_selected_items()

        self._loading_marker = True
        try:
            if not items:
                self.marker_entry.clear()
                self.marker_entry.setEnabled(False)
                self.marker_pos_combo.setEnabled(False)
                self.marker_entry.setPlaceholderText("Ex.: Episódio 1 — selecione um vídeo na fila")
                self.marker_status_label.setText("Selecione um vídeo da fila para configurar seu marcador.")
                return

            self.marker_entry.setEnabled(True)
            self.marker_pos_combo.setEnabled(True)

            markers = [(it.data(_MARKER_ROLE) or {}) for it in items]
            same = all(m == markers[0] for m in markers)

            if same:
                m = markers[0]
                self.marker_entry.setText(m.get("text", ""))
                self.marker_entry.setPlaceholderText("Ex.: Episódio 1")
                pos = m.get("position", "top_right")
                idx = self.marker_pos_combo.findData(pos)
                if idx >= 0:
                    self.marker_pos_combo.setCurrentIndex(idx)

                if len(items) == 1:
                    url = items[0].data(Qt.ItemDataRole.UserRole) or ""
                    short = url if len(url) <= 50 else url[:47] + "..."
                    self.marker_status_label.setText(f"Editando marcador de: {short}")
                else:
                    self.marker_status_label.setText(
                        f"Editando {len(items)} vídeos selecionados (mesmo marcador)."
                    )
            else:
                self.marker_entry.clear()
                self.marker_entry.setPlaceholderText("(múltiplos valores) — digite para sobrescrever todos")
                self.marker_status_label.setText(
                    f"{len(items)} vídeos com marcadores diferentes — editar aqui sobrescreve todos."
                )
        finally:
            self._loading_marker = False

    def _on_marker_edited(self, *_):
        """Persiste o marcador atual nos itens selecionados da fila."""
        if self._loading_marker:
            return
        items = self._selectable_selected_items()
        if not items:
            return

        text = self.marker_entry.text().strip()
        position = self.marker_pos_combo.currentData() or "top_right"
        marker = {"text": text, "position": position} if text else None

        for it in items:
            it.setData(_MARKER_ROLE, marker)
            self._refresh_item_display(it)

    def _remove_selected_urls(self):
        for item in self.url_list.selectedItems():
            self.url_list.takeItem(self.url_list.row(item))
        self._ensure_placeholder()
        self._on_url_selection_changed()

    def _clear_url_list(self):
        self.url_list.clear()
        self._ensure_placeholder()
        self._on_url_selection_changed()

    def _ensure_placeholder(self):
        """Mostra placeholder se lista estiver vazia"""
        if self.url_list.count() == 0:
            self._empty_item = QListWidgetItem("  Nenhum link adicionado ainda...")
            self._empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._empty_item.setForeground(QColor("#475569"))
            self.url_list.addItem(self._empty_item)

    def _get_checked_urls(self) -> list[str]:
        """Retorna lista de URLs que estão com checkbox marcado"""
        urls = []
        for i in range(self.url_list.count()):
            item = self.url_list.item(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                if item.checkState() == Qt.CheckState.Checked:
                    url = item.data(Qt.ItemDataRole.UserRole)
                    if url:
                        urls.append(url)
        return urls

    # ------------------------------------------------------------------
    # Pasta
    # ------------------------------------------------------------------

    def escolher_pasta(self):
        try:
            from config.settings import settings
        except ImportError:
            from src.config.settings import settings

        pasta = QFileDialog.getExistingDirectory(
            self, "Escolher Pasta de Saída", settings.last_open_dir
        )
        if pasta:
            self.pasta_label.setText(pasta)
            settings.last_open_dir = pasta
            settings.save_config()

    # ------------------------------------------------------------------
    # Ações dos botões
    # ------------------------------------------------------------------

    def on_baixar_clicked(self):
        """Emite sinal para baixar apenas o vídeo (checados na lista)"""
        urls = self._get_checked_urls()
        self.download_video_apenas.emit(
            urls, self.qualidade_combo.currentText(), Path(self.pasta_label.text())
        )

    def on_baixar_legendar_clicked(self):
        """Emite sinal para executar fluxo completo: download + legenda"""
        urls = self._get_checked_urls()
        self.download_e_legendar.emit(
            urls, self.qualidade_combo.currentText(), Path(self.pasta_label.text())
        )

    # ------------------------------------------------------------------
    # API pública (compatibilidade com MainWindow)
    # ------------------------------------------------------------------

    def get_configuracao(self) -> dict:
        """Retorna configuração atual (URLs checadas + qualidade + pasta + marcadores per-URL)"""
        return {
            "urls": self._get_checked_urls(),
            "qualidade": self.qualidade_combo.currentText(),
            "pasta": Path(self.pasta_label.text()),
            "markers": self.get_markers(),
        }

    def get_markers(self) -> dict:
        """Retorna {url: {"text": str, "position": str}} apenas para URLs com marcador definido."""
        out: dict = {}
        for i in range(self.url_list.count()):
            item = self.url_list.item(i)
            if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                continue
            marker = item.data(_MARKER_ROLE)
            url = item.data(Qt.ItemDataRole.UserRole)
            if marker and url and marker.get("text"):
                out[url] = {
                    "text": marker["text"],
                    "position": marker.get("position", "top_right"),
                }
        return out

    def set_urls(self, urls: list[str]):
        """Adiciona URLs programaticamente (ex: chamado de outro widget)"""
        for url in urls:
            self._append_url(url)
