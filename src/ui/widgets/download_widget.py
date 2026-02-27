"""Widget principal de download"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QComboBox, QLabel, QFileDialog, QFrame,
    QListWidget, QListWidgetItem, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor
from pathlib import Path


class DownloadWidget(QWidget):
    """Widget para configurar e iniciar download"""

    download_iniciado = pyqtSignal(list, str, Path)         # lista_urls, qualidade, pasta
    download_video_apenas = pyqtSignal(list, str, Path)     # baixar apenas (sem legendas)
    download_e_legendar = pyqtSignal(list, str, Path)       # NOVO: baixar + legendar fluxo completo

    def __init__(self):
        super().__init__()
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
        container_layout.setSpacing(18)
        container_layout.setContentsMargins(30, 30, 30, 30)

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
        self.url_entry.setMinimumHeight(46)
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
        self.btn_add_url.setMinimumHeight(46)
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
        self.url_list.setMinimumHeight(130)
        self.url_list.setMaximumHeight(200)
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
        self.qualidade_combo.setMinimumHeight(42)
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
        self.pasta_label.setMinimumHeight(42)
        pasta_input_layout.addWidget(self.pasta_label)

        self.btn_pasta = QPushButton("Escolher...")
        self.btn_pasta.setMinimumHeight(42)
        self.btn_pasta.clicked.connect(self.escolher_pasta)
        pasta_input_layout.addWidget(self.btn_pasta)

        pasta_group.addLayout(pasta_input_layout)
        grid_config.addLayout(pasta_group, 2)

        container_layout.addLayout(grid_config)

        # ── Botões de ação ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        # Botão: apenas baixar
        self.btn_baixar = QPushButton("⬇  Baixar (Sem Legendas)")
        self.btn_baixar.setMinimumHeight(52)
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
        self.btn_baixar_legendar.setMinimumHeight(52)
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

        # Exibir só o domínio + path curto p/ legibilidade
        display = url if len(url) <= 60 else url[:57] + "..."
        item.setText(f"🔗  {display}")
        item.setToolTip(url)
        item.setForeground(QColor("#e2e8f0"))

        self.url_list.addItem(item)
        self.url_list.scrollToBottom()

    def _remove_selected_urls(self):
        for item in self.url_list.selectedItems():
            self.url_list.takeItem(self.url_list.row(item))
        self._ensure_placeholder()

    def _clear_url_list(self):
        self.url_list.clear()
        self._ensure_placeholder()

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
        """Retorna configuração atual (URLs checadas + qualidade + pasta)"""
        return {
            "urls": self._get_checked_urls(),
            "qualidade": self.qualidade_combo.currentText(),
            "pasta": Path(self.pasta_label.text()),
        }

    def set_urls(self, urls: list[str]):
        """Adiciona URLs programaticamente (ex: chamado de outro widget)"""
        for url in urls:
            self._append_url(url)
