import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QTabWidget, QFileDialog, 
    QDateTimeEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QGroupBox, QFormLayout, QLineEdit, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread
from PyQt6.QtGui import QIcon

from config import settings
from core import SocialPlatform, SocialManager

logger = logging.getLogger(__name__)

class AddAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conectar Conta")
        self.setFixedSize(400, 200)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.platform_combo = QComboBox()
        self.platform_combo.addItems([p.value for p in SocialPlatform])
        form_layout.addRow("Plataforma:", self.platform_combo)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("@usuario")
        form_layout.addRow("Usuário:", self.username_input)
        
        # Simulação de autenticação
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Token (Simulado)")
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Token:", self.token_input)
        
        layout.addLayout(form_layout)
        
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_connect = QPushButton("Conectar")
        self.btn_connect.clicked.connect(self.accept)
        # Style primary button
        self.btn_connect.setStyleSheet("background-color: #3b82f6; color: white; font-weight: bold;")
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_connect)
        
        layout.addLayout(btn_layout)

    def get_data(self):
        return {
            "platform": self.platform_combo.currentText(),
            "username": self.username_input.text(),
            "token": self.token_input.text()
        }

class SchedulerThread(QThread):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.running = True

    def run(self):
        while self.running:
            try:
                due_posts = self.manager.get_due_posts()
                for post in due_posts:
                    logger.info(f"Processing post {post.id}...")
                    self.manager.mark_post_status(post.id, "posting")
                    
                    # Simulation of posting delay
                    self.sleep(2)
                    
                    # Success
                    self.manager.mark_post_status(post.id, "posted")
                    logger.info(f"Post {post.id} completed.")
                    
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            # Check every 10 seconds
            self.sleep(10)

    def stop(self):
        self.running = False
        self.wait()

class SocialWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.manager = settings.social_manager
        self.setup_ui()
        self.refresh_data()
        
        # Timer para atualizar a fila automaticamente
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_queue)
        self.timer.start(5000) # 5 segundos
        
        # Start Scheduler Thread
        if self.manager:
            self.scheduler_thread = SchedulerThread(self.manager)
            self.scheduler_thread.start()

    def closeEvent(self, event):
        if hasattr(self, 'scheduler_thread'):
            self.scheduler_thread.stop()
        super().closeEvent(event)

    def setup_ui(self):
        layout = QHBoxLayout(self)
        
        # Lateral: Contas
        accounts_group = QGroupBox("Contas Conectadas")
        accounts_layout = QVBoxLayout(accounts_group)
        
        self.accounts_list = QListWidget()
        accounts_layout.addWidget(self.accounts_list)
        
        btn_add_account = QPushButton("➕ Conectar Conta")
        btn_add_account.clicked.connect(self.add_account)
        accounts_layout.addWidget(btn_add_account)
        
        btn_remove_account = QPushButton("❌ Desconectar")
        btn_remove_account.clicked.connect(self.remove_account)
        accounts_layout.addWidget(btn_remove_account)
        
        layout.addWidget(accounts_group, 1)
        
        # Centro/Direita: Agendamento e Fila
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Agendamento
        schedule_group = QGroupBox("Novo Agendamento")
        schedule_layout = QFormLayout(schedule_group)
        
        # Vídeo
        video_layout = QHBoxLayout()
        self.video_path_input = QLineEdit()
        self.video_path_input.setReadOnly(True)
        btn_browse = QPushButton("📁")
        btn_browse.clicked.connect(self.browse_video)
        video_layout.addWidget(self.video_path_input)
        video_layout.addWidget(btn_browse)
        schedule_layout.addRow("Vídeo:", video_layout)
        
        # Título
        self.title_input = QLineEdit()
        schedule_layout.addRow("Título:", self.title_input)
        
        # Data/Hora
        self.dt_edit = QDateTimeEdit(datetime.now())
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.setDisplayFormat("dd/MM/yyyy HH:mm")
        schedule_layout.addRow("Data/Hora:", self.dt_edit)
        
        # Botão Agendar
        self.btn_schedule = QPushButton("📅 Agendar Postagem")
        self.btn_schedule.setMinimumHeight(40)
        self.btn_schedule.setStyleSheet("background-color: #10b981; color: white; font-weight: bold; font-size: 14px;")
        self.btn_schedule.clicked.connect(self.schedule_post)
        schedule_layout.addRow(self.btn_schedule)
        
        right_layout.addWidget(schedule_group)
        
        # Fila
        queue_group = QGroupBox("Fila de Agendamentos")
        queue_layout = QVBoxLayout(queue_group)
        
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(5)
        self.queue_table.setHorizontalHeaderLabels(["Data/Hora", "Plataforma", "Título", "Status", "ID"])
        self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.queue_table.hideColumn(4) # Hide ID
        queue_layout.addWidget(self.queue_table)
        
        btn_refresh_queue = QPushButton("🔄 Atualizar Fila")
        btn_refresh_queue.clicked.connect(self.refresh_queue)
        queue_layout.addWidget(btn_refresh_queue)
        
        right_layout.addWidget(queue_group)
        
        layout.addWidget(right_widget, 2)

    def refresh_data(self):
        self.refresh_accounts()
        self.refresh_queue()

    def refresh_accounts(self):
        self.accounts_list.clear()
        if not self.manager:
            return
            
        for account in self.manager.accounts.values():
            item = QListWidgetItem(f"{account.platform}: {account.username}")
            item.setData(Qt.ItemDataRole.UserRole, account.id)
            self.accounts_list.addItem(item)

    def refresh_queue(self):
        if not self.manager:
            return
            
        self.queue_table.setRowCount(0)
        for post in self.manager.posts:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            
            # Format Date
            dt_str = datetime.fromisoformat(post.scheduled_time).strftime("%d/%m/%Y %H:%M")
            self.queue_table.setItem(row, 0, QTableWidgetItem(dt_str))
            
            # Platforms
            platforms = []
            for acc_id in post.platform_ids:
                acc = self.manager.accounts.get(acc_id)
                if acc:
                    platforms.append(acc.platform)
            self.queue_table.setItem(row, 1, QTableWidgetItem(", ".join(platforms)))
            
            self.queue_table.setItem(row, 2, QTableWidgetItem(post.title))
            self.queue_table.setItem(row, 3, QTableWidgetItem(post.status))
            self.queue_table.setItem(row, 4, QTableWidgetItem(post.id))

    def add_account(self):
        if not self.manager:
            QMessageBox.critical(self, "Erro", "Gerenciador social não inicializado.")
            return

        dialog = AddAccountDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            if data["username"]:
                self.manager.add_account(data["platform"], data["username"], data["token"])
                self.refresh_accounts()
            else:
                QMessageBox.warning(self, "Aviso", "Usuário é obrigatório.")

    def remove_account(self):
        selected_items = self.accounts_list.selectedItems()
        if not selected_items:
            return
            
        account_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        confirm = QMessageBox.question(
            self, "Confirmar", "Deseja remover esta conta?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            self.manager.remove_account(account_id)
            self.refresh_accounts()

    def browse_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Vídeo",
            str(settings.output_dir),
            "Vídeos (*.mp4 *.mkv *.mov)"
        )
        if file_path:
            self.video_path_input.setText(file_path)

    def schedule_post(self):
        if not self.manager:
            return
            
        video_path = self.video_path_input.text()
        if not video_path:
            QMessageBox.warning(self, "Aviso", "Selecione um vídeo.")
            return
            
        if not self.manager.accounts:
            QMessageBox.warning(self, "Aviso", "Conecte pelo menos uma conta antes de agendar.")
            return
            
        # Por enquanto, agenda para TODAS as contas conectadas
        # TODO: Permitir selecionar quais contas
        account_ids = list(self.manager.accounts.keys())
        
        dt = self.dt_edit.dateTime().toPyDateTime()
        if dt <= datetime.now():
            QMessageBox.warning(self, "Aviso", "A data deve ser no futuro.")
            return

        self.manager.schedule_post(
            video_path=video_path,
            account_ids=account_ids,
            scheduled_time=dt,
            title=self.title_input.text(),
            description=""
        )
        
        QMessageBox.information(self, "Sucesso", "Post agendado com sucesso!")
        self.refresh_queue()
        self.video_path_input.clear()
        self.title_input.clear()
