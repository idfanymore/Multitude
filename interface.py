from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QTextEdit, QTabWidget, 
                           QTableWidget, QTableWidgetItem, QDialog, QCheckBox, 
                           QScrollArea, QDialogButtonBox, QLabel, QLineEdit,
                           QProgressBar, QSpinBox, QFormLayout, QGroupBox,
                           QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
import config
import json
import os
import sqlite3
from openpyxl import Workbook

class UpdateThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, sources, threads):
        super().__init__()
        self.sources = sources
        self.threads = threads

    def run(self):
        try:
            result = config.update_proxies(self.sources, self.threads, self.progress.emit)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class CheckThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, threads):
        super().__init__()
        self.threads = threads

    def run(self):
        try:
            result = config.check_all_proxies(self.threads, self.progress.emit)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class ProxyManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multitude")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon('icon.png') if os.path.exists('icon.png') else QIcon())
        self.config = self.load_config()
        self.init_ui()
        
    def load_config(self):
        return config.load_config()

    def save_config(self):
        with open(config.CONFIG_PATH, 'w') as f:
            json.dump(self.config, f)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        btn_layout = QHBoxLayout()
        self.update_btn = QPushButton("Update Proxies")
        self.update_btn.clicked.connect(self.show_update_dialog)
        btn_layout.addWidget(self.update_btn)

        self.check_btn = QPushButton("Check Proxies")
        self.check_btn.clicked.connect(self.show_check_dialog)
        btn_layout.addWidget(self.check_btn)

        self.random_btn = QPushButton("Get Random")
        self.random_btn.clicked.connect(self.get_random_proxy)
        btn_layout.addWidget(self.random_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self.show_export_dialog)
        btn_layout.addWidget(self.export_btn)

        layout.addLayout(btn_layout)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        self.tabs = QTabWidget()
        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(4)
        self.proxy_table.setHorizontalHeaderLabels(["Proxy", "Type", "Country", "Status"])
        
        self.region_table = QTableWidget()
        self.region_table.setColumnCount(2)
        self.region_table.setHorizontalHeaderLabels(["Country", "Count"])
        
        self.tabs.addTab(self.proxy_table, "Proxies")
        self.tabs.addTab(self.region_table, "Regions")
        layout.addWidget(self.tabs)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

        self.load_data()

    def show_update_dialog(self):
        self.update_dialog = QDialog(self)
        self.update_dialog.setWindowTitle("Update Settings")
        self.update_dialog.setFixedSize(600, 500)
        
        layout = QVBoxLayout()
        
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout()
        
        self.update_threads_spin = QSpinBox()
        self.update_threads_spin.setRange(1, 500)
        self.update_threads_spin.setValue(self.config['update_threads'])
        settings_layout.addRow("Threads:", self.update_threads_spin)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        sources_group = QGroupBox("Sources")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.scroll_layout = QVBoxLayout(content)
        
        self.source_widgets = []
        all_sources = config.PROXY_SOURCES + config.load_custom_sources()
        
        for source in all_sources:
            hbox = QHBoxLayout()
            cb = QCheckBox(source)
            cb.setChecked(True)
            
            count_label = QLabel("Checking...")
            count_label.setAlignment(Qt.AlignRight)
            count_label.setFixedWidth(100)
            
            if source in config.load_custom_sources():
                cb.setStyleSheet("color: blue;")
            
            hbox.addWidget(cb)
            hbox.addWidget(count_label)
            
            container = QWidget()
            container.setLayout(hbox)
            
            self.source_widgets.append((cb, count_label))
            self.scroll_layout.addWidget(container)
            
            # Запускаем проверку количества прокси
            self.check_source_count(source, count_label)
        
        scroll.setWidget(content)
        sources_layout = QVBoxLayout()
        sources_layout.addWidget(scroll)
        
        add_layout = QHBoxLayout()
        self.new_source_edit = QLineEdit()
        self.new_source_edit.setPlaceholderText("Enter custom source URL")
        add_btn = QPushButton("Add Source")
        add_btn.clicked.connect(self.add_custom_source)
        add_layout.addWidget(self.new_source_edit)
        add_layout.addWidget(add_btn)
        sources_layout.addLayout(add_layout)
        
        sources_group.setLayout(sources_layout)
        layout.addWidget(sources_group)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.start_update)
        btn_box.rejected.connect(self.update_dialog.reject)
        layout.addWidget(btn_box)
        
        self.update_dialog.setLayout(layout)
        self.update_dialog.exec_()

    def check_source_count(self, source, label):
        def update_count():
            count = config.get_proxy_count_from_source(source)
            label.setText(f"Proxies: {count}")
        
        QTimer.singleShot(0, update_count)

    def add_custom_source(self):
        new_source = self.new_source_edit.text().strip()
        if not new_source:
            return
            
        if not new_source.startswith(('http://', 'https://')):
            self.console.append("Error: URL must start with http:// or https://")
            return
            
        custom_sources = config.load_custom_sources()
        if new_source not in custom_sources:
            custom_sources.append(new_source)
            config.save_custom_sources(custom_sources)
            self.config = config.load_config()
            
            hbox = QHBoxLayout()
            cb = QCheckBox(new_source)
            cb.setChecked(True)
            cb.setStyleSheet("color: blue;")
            
            count_label = QLabel("Checking...")
            count_label.setAlignment(Qt.AlignRight)
            count_label.setFixedWidth(100)
            
            hbox.addWidget(cb)
            hbox.addWidget(count_label)
            
            container = QWidget()
            container.setLayout(hbox)
            
            self.source_widgets.append((cb, count_label))
            self.scroll_layout.addWidget(container)
            
            self.check_source_count(new_source, count_label)
            self.console.append(f"Added new source: {new_source}")
        
        self.new_source_edit.clear()

    def start_update(self):
        selected = [cb.text() for cb, _ in self.source_widgets if cb.isChecked()]
        threads = self.update_threads_spin.value()
        
        self.config['update_threads'] = threads
        self.save_config()
        
        self.update_dialog.close()
        self.console.append(f"Updating proxies using {threads} threads...")
        self.toggle_buttons(False)
        self.progress.show()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        
        self.update_thread = UpdateThread(selected, threads)
        self.update_thread.progress.connect(self.update_progress)
        self.update_thread.finished.connect(self.update_complete)
        self.update_thread.error.connect(self.update_error)
        self.update_thread.start()

    def show_check_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Check Settings")
        dialog.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout()
        
        self.check_threads_spin = QSpinBox()
        self.check_threads_spin.setRange(1, 500)
        self.check_threads_spin.setValue(self.config['check_threads'])
        settings_layout.addRow("Threads:", self.check_threads_spin)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(lambda: self.start_check(dialog))
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def start_check(self, dialog):
        threads = self.check_threads_spin.value()
        self.config['check_threads'] = threads
        self.save_config()
        
        dialog.close()
        self.console.append(f"Checking proxies using {threads} threads...")
        self.toggle_buttons(False)
        self.progress.show()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        
        self.check_thread = CheckThread(threads)
        self.check_thread.progress.connect(self.check_progress)
        self.check_thread.finished.connect(self.check_complete)
        self.check_thread.error.connect(self.check_error)
        self.check_thread.start()

    def show_export_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Proxies")
        dialog.setFixedSize(300, 200)
        
        layout = QVBoxLayout()
        
        txt_btn = QPushButton("Export to TXT")
        txt_btn.clicked.connect(lambda: self.export_proxies('txt'))
        layout.addWidget(txt_btn)
        
        excel_btn = QPushButton("Export to Excel")
        excel_btn.clicked.connect(lambda: self.export_proxies('excel'))
        layout.addWidget(excel_btn)
        
        sqlite_btn = QPushButton("Export to SQLite")
        sqlite_btn.clicked.connect(lambda: self.export_proxies('sqlite'))
        layout.addWidget(sqlite_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def export_proxies(self, format_type):
        options = QFileDialog.Options()
        options |= QFileDialog.DontConfirmOverwrite
        default_name = f"proxies_{format_type}"
        
        if format_type == 'txt':
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save TXT File", default_name, "Text Files (*.txt)", options=options)
            if file_name:
                self.save_to_txt(file_name)
                
        elif format_type == 'excel':
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save Excel File", default_name, "Excel Files (*.xlsx)", options=options)
            if file_name:
                self.save_to_excel(file_name)
                
        elif format_type == 'sqlite':
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save SQLite File", default_name, "SQLite Files (*.db)", options=options)
            if file_name:
                self.save_to_sqlite(file_name)

    def save_to_txt(self, file_path):
        try:
            with config.get_db_connection() as conn:
                proxies = conn.execute('SELECT proxy FROM proxies').fetchall()
            
            with open(file_path, 'w') as f:
                for proxy in proxies:
                    f.write(f"{proxy['proxy']}\n")
            
            self.console.append(f"Exported {len(proxies)} proxies to {file_path}")
            QMessageBox.information(self, "Success", f"Exported {len(proxies)} proxies to TXT")
        except Exception as e:
            self.console.append(f"Export error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def save_to_excel(self, file_path):
        try:
            with config.get_db_connection() as conn:
                proxies = conn.execute('SELECT * FROM proxies').fetchall()
            
            wb = Workbook()
            ws = wb.active
            ws.append(["Proxy", "Type", "Country", "Status"])
            
            for proxy in proxies:
                status = "Active" if proxy['is_active'] else "Inactive"
                ws.append([proxy['proxy'], proxy['type'], proxy['country'], status])
            
            wb.save(file_path)
            
            self.console.append(f"Exported {len(proxies)} proxies to {file_path}")
            QMessageBox.information(self, "Success", f"Exported {len(proxies)} proxies to Excel")
        except Exception as e:
            self.console.append(f"Export error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def save_to_sqlite(self, file_path):
        try:
            with sqlite3.connect(config.DB_PATH) as src:
                with sqlite3.connect(file_path) as dst:
                    src.backup(dst)
            
            self.console.append(f"Database copied to {file_path}")
            QMessageBox.information(self, "Success", "Database exported successfully")
        except Exception as e:
            self.console.append(f"Export error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def update_progress(self, value):
        self.progress.setValue(value)

    def check_progress(self, value):
        self.progress.setValue(value)

    def update_complete(self, count):
        self.progress.setValue(100)  # Устанавливаем на 100% при завершении
        QTimer.singleShot(1000, self.progress.hide)
        self.progress.hide()
        self.console.append(f"Update complete. Added {count} new proxies")
        self.toggle_buttons(True)
        self.load_data()

    def check_complete(self, count):
        self.progress.setValue(100)  # Устанавливаем на 100% при завершении
        QTimer.singleShot(1000, self.progress.hide)
        self.progress.hide()
        self.console.append(f"Check complete. Active proxies: {count}")
        self.toggle_buttons(True)
        self.load_data()

    def update_error(self, error):
        self.progress.hide()
        self.progress.hide()
        self.console.append(f"Update error: {error}")
        self.toggle_buttons(True)

    def check_error(self, error):
        self.progress.hide()
        self.progress.hide()
        self.console.append(f"Check error: {error}")
        self.toggle_buttons(True)

    def toggle_buttons(self, enabled):
        self.update_btn.setEnabled(enabled)
        self.check_btn.setEnabled(enabled)
        self.random_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)

    def get_random_proxy(self):
        proxy = config.get_random_proxy()
        self.console.append(f"Random proxy: {proxy}" if proxy else "No proxies available")

    def load_data(self):
        with config.get_db_connection() as conn:
            proxies = conn.execute('SELECT * FROM proxies').fetchall()
        
        self.proxy_table.setRowCount(len(proxies))
        for i, p in enumerate(proxies):
            self.proxy_table.setItem(i, 0, QTableWidgetItem(p['proxy']))
            self.proxy_table.setItem(i, 1, QTableWidgetItem(p['type']))
            self.proxy_table.setItem(i, 2, QTableWidgetItem(p['country']))
            
            status = QTableWidgetItem("Active" if p['is_active'] else "Inactive")
            status.setForeground(Qt.green if p['is_active'] else Qt.red)
            self.proxy_table.setItem(i, 3, status)

        regions = config.get_proxies_by_region()
        self.region_table.setRowCount(len(regions))
        for i, r in enumerate(regions):
            self.region_table.setItem(i, 0, QTableWidgetItem(r['country']))
            self.region_table.setItem(i, 1, QTableWidgetItem(str(r['count'])))

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = ProxyManager()
    window.show()
    sys.exit(app.exec_())