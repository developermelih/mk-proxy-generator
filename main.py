import sys
import json
import time
import socket
import threading
from datetime import datetime
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QTextEdit, QGroupBox, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRunnable, QObject, QThreadPool
from PyQt5.QtGui import QFont, QColor

from backend.tor_handler import TorPoolManager
from backend.proxy_server import HybridProxyServer


DEFAULT_CONFIG = {
    "pool_size": 5,
    "proxy_port": 8080,
    "auto_rotate_time": 0,
    "base_socks_port": 9050,
    "base_control_port": 9051,
    "ip_cache_ttl": 60,
    "connection_timeout": 2.0,
    "rotation_timeout": 10,
    "check_interval": 1500
}

DARK_STYLE = """
QMainWindow {
    background-color: #1e1e1e;
    color: #ffffff;
}

QWidget {
    background-color: #1e1e1e;
    color: #ffffff;
}

QGroupBox {
    border: 2px solid #3a3a3a;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
    color: #00ff00;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}

QPushButton {
    background-color: #2d2d2d;
    border: 2px solid #3a3a3a;
    border-radius: 5px;
    padding: 8px;
    font-weight: bold;
    min-height: 30px;
}

QPushButton:hover {
    background-color: #3a3a3a;
    border: 2px solid #4a4a4a;
}

QPushButton:pressed {
    background-color: #1a1a1a;
}

QPushButton#startButton {
    background-color: #00aa00;
    border: 2px solid #00ff00;
    color: #ffffff;
    font-size: 14px;
    min-height: 40px;
}

QPushButton#startButton:hover {
    background-color: #00cc00;
}

QPushButton#stopButton {
    background-color: #aa0000;
    border: 2px solid #ff0000;
    color: #ffffff;
    font-size: 14px;
    min-height: 40px;
}

QPushButton#stopButton:hover {
    background-color: #cc0000;
}

QPushButton#rotateButton {
    background-color: #aa5500;
    border: 2px solid #ff8800;
    color: #ffffff;
    font-size: 12px;
}

QPushButton#rotateButton:hover {
    background-color: #cc6600;
}

QSpinBox, QLineEdit {
    background-color: #2d2d2d;
    border: 2px solid #3a3a3a;
    border-radius: 3px;
    padding: 5px;
    color: #ffffff;
}

QSpinBox:hover, QLineEdit:hover {
    border: 2px solid #4a4a4a;
}

QSpinBox:focus, QLineEdit:focus {
    border: 2px solid #00ff00;
}

QTableWidget {
    background-color: #1a1a1a;
    border: 2px solid #3a3a3a;
    border-radius: 5px;
    gridline-color: #3a3a3a;
    color: #ffffff;
    selection-background-color: #3a3a3a;
    alternate-background-color: #2d2d2d;
}

QTableWidget::item {
    padding: 5px;
}

QTableWidget::item:selected {
    background-color: #00aa00;
}

QHeaderView::section {
    background-color: #2d2d2d;
    color: #00ff00;
    padding: 5px;
    border: 1px solid #3a3a3a;
    font-weight: bold;
}

QTextEdit {
    background-color: #000000;
    border: 2px solid #3a3a3a;
    border-radius: 5px;
    color: #00ff00;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 10pt;
}

QLabel {
    color: #ffffff;
}

QLabel#statusLabel {
    font-weight: bold;
    font-size: 12pt;
    padding: 10px;
    border-radius: 5px;
    background-color: #2d2d2d;
}

QLabel#infoLabel {
    background-color: #2d2d2d;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 8px;
    color: #00ff00;
}
"""


class ConfigManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.default_config = DEFAULT_CONFIG.copy()
    
    def load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return {**self.default_config, **config}
            except Exception:
                return self.default_config.copy()
        return self.default_config.copy()
    
    def save(self, config: dict):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Config save error: {e}")


class BackendWorker(QThread):
    log_signal = pyqtSignal(str)
    pool_ready_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    
    def __init__(self, pool_size: int, proxy_port: int, base_socks_port: int, base_control_port: int):
        super().__init__()
        self.pool_size = pool_size
        self.proxy_port = proxy_port
        self.base_socks_port = base_socks_port
        self.base_control_port = base_control_port
        self.pool_manager = None
        self.proxy_server = None
        self.running = False
    
    def run(self):
        try:
            self.running = True
            self.pool_manager = TorPoolManager(
                count=self.pool_size,
                base_socks_port=self.base_socks_port,
                base_control_port=self.base_control_port
            )
            
            try:
                self.pool_manager.start_pool()
            except Exception as e:
                error_msg = f'<span style="color: #ff0000;">[{datetime.now().strftime("%H:%M:%S")}] ✗ Pool start error: {str(e)}</span>'
                self.log_signal.emit(error_msg)
                self.error_signal.emit(str(e))
                return
            
            if not self.pool_manager.instances:
                error_msg = f'<span style="color: #ff0000;">[{datetime.now().strftime("%H:%M:%S")}] ✗ Tor instances could not be started</span>'
                self.log_signal.emit(error_msg)
                self.error_signal.emit("No Tor instances started")
                return
            
            self.log_signal.emit(f'<span style="color: #00ff00;">[{datetime.now().strftime("%H:%M:%S")}] [Pool ready - {len(self.pool_manager.instances)} instances]</span>')
            
            try:
                self.proxy_server = HybridProxyServer(
                    pool_manager=self.pool_manager,
                    host='127.0.0.1',
                    port=self.proxy_port,
                    log_callback=self.log_signal.emit
                )
                self.log_signal.emit(f'<span style="color: #00ff00;">[{datetime.now().strftime("%H:%M:%S")}] [Proxy server started - 127.0.0.1:{self.proxy_port}]</span>')
            except Exception as e:
                error_msg = f'<span style="color: #ff0000;">[{datetime.now().strftime("%H:%M:%S")}] ✗ Proxy server start error: {str(e)}</span>'
                self.log_signal.emit(error_msg)
                self.error_signal.emit(f"Proxy server error: {str(e)}")
                return
            
            self.pool_ready_signal.emit(self.pool_manager)
            
            self.proxy_server.timeout = 0.5
            self.proxy_server.socket.settimeout(0.5)
            while self.running:
                try:
                    self.proxy_server.handle_request()
                except socket.timeout:
                    continue
                except Exception:
                    if not self.running:
                        break
                    time.sleep(0.1)
        except Exception as e:
            if self.running:
                error_msg = f'<span style="color: #ff0000;">[{datetime.now().strftime("%H:%M:%S")}] ✗ ERROR: {str(e)}</span>'
                self.log_signal.emit(error_msg)
                self.error_signal.emit(str(e))
    
    def stop(self):
        self.running = False
        if self.proxy_server:
            try:
                self.proxy_server.stop()
            except:
                pass
        if self.pool_manager:
            try:
                self.pool_manager.stop_pool()
            except:
                pass
    


class WorkerSignals(QObject):
    """Signals for IP check workers."""
    result = pyqtSignal(int, str, str, str)  # row, ip, country, status


class IpCheckWorker(QRunnable):
    """High-performance QRunnable for checking a single Tor instance IP."""
    
    def __init__(self, row: int, instance, signals: WorkerSignals):
        super().__init__()
        self.row = row
        self.instance = instance
        self.signals = signals
    
    def _is_valid_ip(self, ip_str):
        """Basic IP validation."""
        if not ip_str or ip_str in ("Unknown", "Loading...", "Ready", "...", "-", "Preparing"):
            return False
        parts = ip_str.split('.')
        if len(parts) != 4:
            return False
        try:
            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            return True
        except ValueError:
            return False
    
    def run(self):
        """Execute IP check with caching and parallelization."""
        try:
            for _ in range(10):
                if self.instance.is_circuit_ready():
                    break
                time.sleep(0.5)

            ip = self.instance.get_ip(max_retries=3, retry_delay=1)

            if ip and self._is_valid_ip(ip):
                country = self.instance.get_country(ip)
                status = "🟢 Ready"
            elif ip == "...":
                ip = "Loading..."
                country = "Loading..."
                status = "🟡 Connecting"
            else:
                ip = "Loading..."
                country = "Loading..."
                status = "🟡 Connecting"

            try:
                self.signals.result.emit(self.row, ip, country, status)
            except RuntimeError:
                pass
        except Exception:
            try:
                self.signals.result.emit(self.row, "...", "-", "🔴 Error")
            except RuntimeError:
                pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        
        self.backend_worker = None
        self.pool_manager = None
        self.system_running = False
        self.ips_ready_signal_handled = False
        self.rotation_timer = QTimer()
        self.rotation_timer.timeout.connect(self.auto_rotate_ip)
        self.ip_check_timer = QTimer()
        self.ip_check_timer.timeout.connect(self.check_all_ips)
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(15)
        self.last_ips = {}
        self.worker_signals = {}
        
        self.init_ui()
        self.apply_dark_theme()
        self.load_config_to_ui()
    
    def init_ui(self):
        self.setWindowTitle("MK Proxy Generator and Rotator")
        self.setGeometry(100, 100, 1400, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        left_panel = self.create_left_panel()
        right_panel = self.create_right_panel()
        
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)
    
    def create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)
        
        title = QLabel("Proxy Configuration")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        config_group = QGroupBox("Settings")
        config_layout = QVBoxLayout()
        
        pool_size_layout = QHBoxLayout()
        pool_size_layout.addWidget(QLabel("Pool Size:"))
        self.pool_size_spin = QSpinBox()
        self.pool_size_spin.setRange(1, 10)
        self.pool_size_spin.setValue(self.config.get("pool_size", 5))
        self.pool_size_spin.setEnabled(not self.system_running)
        pool_size_layout.addWidget(self.pool_size_spin)
        config_layout.addLayout(pool_size_layout)
        
        proxy_port_layout = QHBoxLayout()
        proxy_port_layout.addWidget(QLabel("Proxy Port:"))
        self.proxy_port_input = QLineEdit()
        self.proxy_port_input.setText(str(self.config.get("proxy_port", 8080)))
        self.proxy_port_input.setEnabled(not self.system_running)
        proxy_port_layout.addWidget(self.proxy_port_input)
        config_layout.addLayout(proxy_port_layout)
        
        rotation_layout = QHBoxLayout()
        rotation_layout.addWidget(QLabel("Auto Rotate Time (sec):"))
        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(0, 3600)
        self.rotation_spin.setValue(self.config.get("auto_rotate_time", 0))
        self.rotation_spin.setSpecialValueText("Off/Manual")
        self.rotation_spin.setEnabled(not self.system_running)
        self.rotation_spin.valueChanged.connect(self.on_rotation_time_changed)
        rotation_layout.addWidget(self.rotation_spin)
        config_layout.addLayout(rotation_layout)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        button_group = QGroupBox("Control")
        button_layout = QVBoxLayout()
        
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_system)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self.stop_system)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        
        self.rotate_button = QPushButton("Change IP (Manual)")
        self.rotate_button.setObjectName("rotateButton")
        self.rotate_button.clicked.connect(self.manual_rotate_ip)
        self.rotate_button.setEnabled(False)
        button_layout.addWidget(self.rotate_button)
        
        button_group.setLayout(button_layout)
        layout.addWidget(button_group)
        
        info_group = QGroupBox("Connection Info")
        info_layout = QVBoxLayout()
        
        self.info_label = QLabel("Proxy Address: 127.0.0.1:8080")
        self.info_label.setObjectName("infoLabel")
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("System Status: IDLE")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setStyleSheet("background-color: #aa0000; color: #ffffff;")
        self.status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        layout.addStretch()
        
        return panel
    
    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)
        
        table_label = QLabel("Instance List")
        table_label_font = QFont()
        table_label_font.setPointSize(12)
        table_label_font.setBold(True)
        table_label.setFont(table_label_font)
        layout.addWidget(table_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Backend Port", "Current IP", "Country", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(False)
        layout.addWidget(self.table)
        
        log_label = QLabel("Log Terminal")
        log_label_font = QFont()
        log_label_font.setPointSize(12)
        log_label_font.setBold(True)
        log_label.setFont(log_label_font)
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        layout.addWidget(self.log_text)
        
        return panel
    
    def apply_dark_theme(self):
        self.setStyleSheet(DARK_STYLE)
    
    def load_config_to_ui(self):
        self.pool_size_spin.setValue(self.config.get("pool_size", 5))
        self.proxy_port_input.setText(str(self.config.get("proxy_port", 8080)))
        self.rotation_spin.setValue(self.config.get("auto_rotate_time", 0))
        proxy_port = self.config.get("proxy_port", 8080)
        self.info_label.setText(
            f"Proxy Address: 127.0.0.1:{proxy_port}\n\n"
            f"Browser Settings:\n"
            f"HTTP Proxy: 127.0.0.1\n"
            f"Port: {proxy_port}\n\n"
            f"API Rotation:\n"
            f"GET http://127.0.0.1:{proxy_port}/rotate"
        )
    
    def save_config_from_ui(self):
        self.config["pool_size"] = self.pool_size_spin.value()
        self.config["proxy_port"] = int(self.proxy_port_input.text())
        self.config["auto_rotate_time"] = self.rotation_spin.value()
        self.config_manager.save(self.config)
    
    def log_message(self, message: str):
        self.log_text.append(message)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def start_system(self):
        if self.system_running:
            QMessageBox.warning(self, "Warning", "System is already running!")
            return
        
        try:
            pool_size = self.pool_size_spin.value()
            proxy_port = int(self.proxy_port_input.text())
            
            if proxy_port < 1024 or proxy_port > 65535:
                QMessageBox.warning(self, "Error", "Port number must be between 1024 and 65535!")
                return
            
            self.save_config_from_ui()
            
            self.start_button.setEnabled(False)
            self.pool_size_spin.setEnabled(False)
            self.proxy_port_input.setEnabled(False)
            self.rotation_spin.setEnabled(False)
            
            base_socks_port = self.config.get("base_socks_port", 9050)
            base_control_port = self.config.get("base_control_port", 9051)
            
            self.backend_worker = BackendWorker(pool_size, proxy_port, base_socks_port, base_control_port)
            self.backend_worker.log_signal.connect(self.log_message)
            self.backend_worker.pool_ready_signal.connect(self.on_pool_ready)
            self.backend_worker.error_signal.connect(self.on_backend_error)
            self.backend_worker.start()
            
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid port number!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"System could not be started: {str(e)}")
            self.log_message(f'<span style="color: #ff0000;">[{datetime.now().strftime("%H:%M:%S")}] ✗ ERROR: {str(e)}</span>')
    
    def on_pool_ready(self, pool_manager: TorPoolManager):
        self.pool_manager = pool_manager
        
        self.system_running = True
        self.status_label.setText("System Status: RUNNING")
        self.status_label.setStyleSheet("background-color: #00aa00; color: #ffffff;")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.rotate_button.setEnabled(True)
        
        self.update_table()
        self.start_ip_updates()
        
        proxy_port = int(self.proxy_port_input.text())
        self.info_label.setText(
            f"Proxy Address: 127.0.0.1:{proxy_port}\n\n"
            f"Browser Settings:\n"
            f"HTTP Proxy: 127.0.0.1\n"
            f"Port: {proxy_port}\n\n"
            f"API Rotation:\n"
            f"GET http://127.0.0.1:{proxy_port}/rotate"
        )
        
        self.log_message(f'<span style="color: #00ff00;">[{datetime.now().strftime("%H:%M:%S")}] [System started]</span>')
    
    def check_all_ips(self):
        """Check all IPs in parallel using QThreadPool (non-blocking)."""
        if not self.system_running or not self.pool_manager or not self.pool_manager.instances:
            return
        
        for i, instance in enumerate(self.pool_manager.instances):
            if i not in self.worker_signals:
                signals = WorkerSignals()
                signals.result.connect(self.update_table_row)
                self.worker_signals[i] = signals
            
            worker = IpCheckWorker(i, instance, self.worker_signals[i])
            self.thread_pool.start(worker)
    
    def on_backend_error(self, error: str):
        QMessageBox.critical(self, "Error", f"Backend error:\n{error}")
        self.stop_system()
    
    def stop_system(self, force: bool = False):
        if not self.system_running:
            return
        
        self.rotation_timer.stop()
        self.ip_check_timer.stop()
        self.system_running = False
        
        self.thread_pool.waitForDone(500)
        
        for signals in self.worker_signals.values():
            try:
                signals.result.disconnect()
            except:
                pass
        
        self.worker_signals.clear()
        
        def stop_backend():
            if self.backend_worker:
                try:
                    self.backend_worker.stop()
                    self.backend_worker.terminate()
                except:
                    pass
        
        threading.Thread(target=stop_backend, daemon=True).start()
        
        self.pool_manager = None
        self.backend_worker = None
        
        self.status_label.setText("System Status: IDLE")
        self.status_label.setStyleSheet("background-color: #aa0000; color: #ffffff;")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.rotate_button.setEnabled(False)
        self.pool_size_spin.setEnabled(True)
        self.proxy_port_input.setEnabled(True)
        self.rotation_spin.setEnabled(True)
        
        self.table.setRowCount(0)
        self.ips_ready_signal_handled = False
        self.last_ips.clear()
        
        self.log_message(f'<span style="color: #00ff00;">[{datetime.now().strftime("%H:%M:%S")}] [Sistem Durduruldu]</span>')
        QApplication.processEvents()
    
    def on_rotation_time_changed(self, value):
        if self.system_running and self.ips_ready_signal_handled:
            if value > 0:
                if not self.rotation_timer.isActive():
                    self.rotation_timer.start(value * 1000)
                else:
                    self.rotation_timer.setInterval(value * 1000)
            else:
                if self.rotation_timer.isActive():
                    self.rotation_timer.stop()
    
    def manual_rotate_ip(self):
        if not self.pool_manager:
            return
        
        try:
            # Pool size kontrolü
            pool_size = len(self.pool_manager.instances)
            
            # Hızlı geçiş veya IP yenileme
            new_instance = self.pool_manager.switch_to_next_instance()
            if new_instance:
                # Log mesajı: tek instance ise IP yenileme, çoklu ise geçiş
                if pool_size == 1:
                    self.log_message(f'<span style="color: #00ff00;">[{datetime.now().strftime("%H:%M:%S")}] ♻️ IP Yenileniyor -> Port: {new_instance.socks_port}</span>')
                else:
                    self.log_message(f'<span style="color: #00ff00;">[{datetime.now().strftime("%H:%M:%S")}] ♻️ Hızlı Geçiş Yapıldı -> Yeni Port: {new_instance.socks_port}</span>')
            else:
                QMessageBox.warning(self, "Hata", "IP yenileme/geçiş yapılamadı")
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"IP işlemi hatası: {str(e)}")
    
    def auto_rotate_ip(self):
        interval = self.rotation_spin.value()
        if interval > 0 and self.system_running and self.pool_manager:
            self.manual_rotate_ip()
    
    def setup_rotation_timer(self):
        interval = self.rotation_spin.value()
        if interval > 0:
            if self.rotation_timer.isActive():
                self.rotation_timer.stop()
            self.rotation_timer.start(interval * 1000)
        else:
            if self.rotation_timer.isActive():
                self.rotation_timer.stop()
    
    def start_ip_updates(self):
        """Start IP checking timer with fast updates."""
        if self.pool_manager:
            self.check_all_ips()
            self.ip_check_timer.start(1500)
            QTimer.singleShot(2000, self.on_ips_ready)
    
    def on_ips_ready(self):
        if not self.ips_ready_signal_handled:
            self.ips_ready_signal_handled = True
            self.setup_rotation_timer()
    
    def update_table(self):
        if not self.pool_manager:
            return
        
        self.table.setRowCount(len(self.pool_manager.instances))
        
        for i, instance in enumerate(self.pool_manager.instances):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(str(instance.socks_port)))
            self.table.setItem(i, 2, QTableWidgetItem("Loading..."))
            self.table.setItem(i, 3, QTableWidgetItem("Loading..."))
            self.table.setItem(i, 4, QTableWidgetItem("⏳ Waiting"))
    
    def _reset_row_background(self, row: int):
        """Reset the row background to default."""
        if row < self.table.rowCount():
            ip_item = self.table.item(row, 2)
            country_item = self.table.item(row, 3)
            if ip_item:
                ip_item.setBackground(QColor())
            if country_item:
                country_item.setBackground(QColor())
    
    def update_table_row(self, row: int, ip: str, country: str, status: str):
        if row < self.table.rowCount():
            # Eski IP'yi kontrol et (görsel feedback ve log için)
            old_ip_item = self.table.item(row, 2)
            old_ip = old_ip_item.text() if old_ip_item else ""
            
            ip_item = QTableWidgetItem(ip)
            country_item = QTableWidgetItem(country)
            status_item = QTableWidgetItem(status)
            
            self.table.setItem(row, 2, ip_item)
            self.table.setItem(row, 3, country_item)
            self.table.setItem(row, 4, status_item)
            
            last_ip = self.last_ips.get(row, None)
            if (last_ip and last_ip != ip and 
                ip not in ("Loading...", "Unknown", "...") and 
                last_ip not in ("Loading...", "Unknown", "...")):
                self.log_message(f'<span style="color: #00ff00;">[{datetime.now().strftime("%H:%M:%S")}] ID: {row + 1} | IP: {ip} | Country: {country}</span>')
                
                ip_item.setBackground(QColor(0, 150, 0))
                country_item.setBackground(QColor(0, 150, 0))
                
                QTimer.singleShot(1000, lambda: self._reset_row_background(row))
            
            if ip not in ("Loading...", "Unknown", "..."):
                self.last_ips[row] = ip
    
    def closeEvent(self, event):
        if self.system_running:
            reply = QMessageBox.question(
                self,
                "Exit",
                "System is running. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.stop_system(force=True)
                # Wait for thread pool to finish
                self.thread_pool.waitForDone(1000)
                self.save_config_from_ui()
                QApplication.processEvents()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_config_from_ui()
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.setWindowTitle("MK Proxy Generator and Rotator")
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

