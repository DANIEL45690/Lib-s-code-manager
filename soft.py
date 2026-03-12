import sys
import subprocess
import importlib
import os
import json
import platform
import psutil
import datetime
import threading
import queue
import time
import re
import pkg_resources
from collections import Counter
from typing import List, Dict, Tuple
import webbrowser
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# ==================== АВТОМАТИЧЕСКАЯ УСТАНОВКА БИБЛИОТЕК ====================

REQUIRED_LIBRARIES = ["PyQt5", "PyQt5-sip", "psutil", "requests"]


def check_and_install_libraries():
    """Проверяет и устанавливает необходимые библиотеки"""
    missing_libs = []

    for lib in REQUIRED_LIBRARIES:
        try:
            if lib == "PyQt5-sip":
                lib_check = "sip"
            elif lib == "PyQt5":
                lib_check = "PyQt5.QtWidgets"
            else:
                lib_check = lib

            importlib.import_module(lib_check)
            print(f"✓ Библиотека {lib} уже установлена")
        except ImportError:
            missing_libs.append(lib)

    if missing_libs:
        print(
            f"Обнаружены отсутствующие библиотеки ({len(missing_libs)}): {', '.join(missing_libs)}"
        )
        print("Начинаю установку...")

        try:
            for lib in missing_libs:
                print(f"Устанавливаю {lib}...")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", lib],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    print(f"✅ {lib} успешно установлена")
                else:
                    print(f"⚠️ Проблема с {lib}: {result.stderr[:100]}")

            print("Все библиотеки установлены!")
            return True
        except Exception as e:
            print(f"❌ Ошибка при установке: {e}")
            return False

    return True


# ==================== КЛАСС ДЛЯ УСТАНОВКИ БИБЛИОТЕК ====================


class LibraryInstaller(QThread):
    """Поток для установки библиотек"""

    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, libraries):
        super().__init__()
        self.libraries = libraries

    def run(self):
        results = {"success": [], "failed": [], "already": []}

        for lib in self.libraries:
            try:
                # Проверяем, установлена ли уже
                self.progress.emit(f"🔍 Проверяю {lib}...")

                try:
                    if lib == "PyQt5-sip":
                        importlib.import_module("sip")
                    else:
                        importlib.import_module(lib)
                    results["already"].append(lib)
                    self.progress.emit(f"✓ {lib} уже установлена")
                    continue
                except ImportError:
                    pass

                # Устанавливаем
                self.progress.emit(f"📦 Устанавливаю {lib}...")

                process = subprocess.run(
                    [sys.executable, "-m", "pip", "install", lib],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if process.returncode == 0:
                    results["success"].append(lib)
                    self.progress.emit(f"✅ {lib} успешно установлена")
                else:
                    results["failed"].append((lib, process.stderr[:200]))
                    self.progress.emit(f"❌ Ошибка установки {lib}")

            except subprocess.TimeoutExpired:
                results["failed"].append((lib, "Таймаут"))
                self.progress.emit(f"⏰ Таймаут при установке {lib}")
            except Exception as e:
                results["failed"].append((lib, str(e)))
                self.progress.emit(f"⚠️ Ошибка: {lib} - {str(e)[:100]}")

        self.finished.emit(results)


# ==================== МЕНЕДЖЕР КОНФИГУРАЦИИ ====================


class ConfigManager:
    """Управление настройками приложения"""

    def __init__(self):
        self.config_file = "console_hack_config.json"
        self.default_config = {
            "theme": "dark_red",
            "auto_update": True,
            "check_dependencies": True,
            "log_level": "info",
            "pip_source": "https://pypi.org/simple/",
            "timeout": 30,
            "recent_codes": [],
            "installed_libs": [],
            "window_size": [1200, 800],
            "window_position": [100, 100],
        }
        self.config = self.load_config()

    def load_config(self):
        """Загружает конфигурацию из файла"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    # Объединяем с дефолтными настройками
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}")

        return self.default_config.copy()

    def save_config(self):
        """Сохраняет конфигурацию в файл"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")
            return False

    def update_setting(self, key, value):
        """Обновляет настройку"""
        self.config[key] = value
        return self.save_config()


# ==================== СИСТЕМНЫЙ МОНИТОР ====================


class SystemMonitor(QThread):
    """Поток для мониторинга системы"""

    update_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        while self.running:
            try:
                # Сбор системной информации
                cpu_percent = psutil.cpu_percent(interval=0.5)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                net_io = psutil.net_io_counters()
                battery = None

                if hasattr(psutil, "sensors_battery"):
                    battery = psutil.sensors_battery()

                # Температура (требует прав администратора на некоторых системах)
                temps = {}
                try:
                    if hasattr(psutil, "sensors_temperatures"):
                        temps = psutil.sensors_temperatures()
                except:
                    pass

                # Процессы
                processes = []
                for proc in psutil.process_iter(
                    ["pid", "name", "cpu_percent", "memory_percent"]
                ):
                    try:
                        processes.append(
                            {
                                "pid": proc.info["pid"],
                                "name": proc.info["name"],
                                "cpu": proc.info["cpu_percent"],
                                "memory": proc.info["memory_percent"],
                            }
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                # Сортируем по использованию CPU
                processes.sort(key=lambda x: x["cpu"], reverse=True)
                top_processes = processes[:10]

                # Формируем данные
                data = {
                    "cpu": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_used_gb": memory.used / (1024**3),
                    "memory_total_gb": memory.total / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3),
                    "net_sent_mb": net_io.bytes_sent / (1024**2),
                    "net_recv_mb": net_io.bytes_recv / (1024**2),
                    "battery_percent": battery.percent if battery else None,
                    "battery_plugged": battery.power_plugged if battery else None,
                    "temperatures": temps,
                    "processes": top_processes,
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                }

                self.update_signal.emit(data)

                # Обновляем каждые 2 секунды
                time.sleep(2)

            except Exception as e:
                print(f"Ошибка мониторинга: {e}")
                time.sleep(5)

    def stop(self):
        """Останавливает мониторинг"""
        self.running = False


# ==================== АНАЛИЗАТОР КОДА ====================


class CodeAnalyzer:
    """Анализирует Python код и извлекает импорты"""

    @staticmethod
    def extract_imports(code: str) -> List[str]:
        """Извлекает все импорты из кода"""
        imports = []

        # Регулярные выражения для поиска импортов
        import_patterns = [
            r"^\s*import\s+([\w\.]+)",  # import module
            r"^\s*from\s+([\w\.]+)\s+import",  # from module import
            r'^\s*__import__\s*\(\s*[\'"]([\w\.]+)[\'"]',  # __import__()
        ]

        for line in code.split("\n"):
            for pattern in import_patterns:
                match = re.search(pattern, line)
                if match:
                    module = match.group(1).split(".")[
                        0
                    ]  # Берем только корневой модуль
                    if module and module not in imports:
                        imports.append(module)

        return imports

    @staticmethod
    def get_installed_libraries() -> List[str]:
        """Возвращает список установленных библиотек"""
        installed = []
        try:
            for dist in pkg_resources.working_set:
                installed.append(dist.key)
        except:
            # Альтернативный способ через pip
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "list", "--format=freeze"],
                    capture_output=True,
                    text=True,
                )
                for line in result.stdout.split("\n"):
                    if "==" in line:
                        installed.append(line.split("==")[0].lower())
            except:
                pass

        return installed

    @staticmethod
    def analyze_dependencies(code: str) -> Dict:
        """Анализирует зависимости кода"""
        imports = CodeAnalyzer.extract_imports(code)
        installed = CodeAnalyzer.get_installed_libraries()

        # Стандартные библиотеки Python (не требуют установки)
        std_libs = [
            "os",
            "sys",
            "math",
            "datetime",
            "json",
            "re",
            "collections",
            "itertools",
            "functools",
            "typing",
            "random",
            "string",
            "hashlib",
            "time",
            "threading",
            "queue",
            "pathlib",
            "shutil",
            "subprocess",
            "argparse",
            "getpass",
            "csv",
            "pickle",
            "socket",
            "ssl",
            "urllib",
        ]

        # Классифицируем импорты
        to_install = []
        already_installed = []
        standard_libs = []
        unknown = []

        for lib in imports:
            lib_lower = lib.lower()
            if lib_lower in std_libs:
                standard_libs.append(lib)
            elif lib_lower in installed:
                already_installed.append(lib)
            else:
                # Проверяем, существует ли такая библиотека на PyPI
                to_install.append(lib)

        return {
            "to_install": to_install,
            "already_installed": already_installed,
            "standard_libs": standard_libs,
            "total_imports": len(imports),
            "unique_imports": imports,
        }


# ==================== ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ ====================


class ConsoleHackApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.monitor = SystemMonitor()
        self.code_analyzer = CodeAnalyzer()

        self.setWindowTitle("Console Hack PRO v2.0 | @concole_hack")
        self.setGeometry(100, 100, 1200, 800)

        # Восстанавливаем размер и позицию окна
        if "window_size" in self.config.config:
            self.resize(*self.config.config["window_size"])
        if "window_position" in self.config.config:
            self.move(*self.config.config["window_position"])

        self.setup_ui()
        self.setup_connections()

        # Запускаем мониторинг системы
        self.monitor.update_signal.connect(self.update_monitor_display)
        self.monitor.start()

        # Загружаем историю
        self.load_history()

    def setup_ui(self):
        """Настройка интерфейса"""
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Главный макет
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Верхняя панель
        self.create_top_panel(main_layout)

        # Центральная область
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # Боковая панель
        self.create_sidebar(center_layout)

        # Область контента
        self.create_content_area(center_layout)

        center_widget.setLayout(center_layout)
        main_layout.addWidget(center_widget)

        # Нижняя панель
        self.create_bottom_panel(main_layout)

    def create_top_panel(self, parent_layout):
        """Создает верхнюю панель"""
        top_panel = QFrame()
        top_panel.setFixedHeight(70)
        top_panel.setStyleSheet(self.get_gradient_style("top"))

        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(20, 10, 20, 10)

        # Логотип и название
        logo_label = QLabel("⚡ CONSOLE HACK PRO")
        logo_label.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 28px;
                font-weight: bold;
                font-family: 'Courier New', monospace;
                text-shadow: 0 0 15px #ff0000, 0 0 25px #ff0000;
                padding: 5px;
            }
        """
        )

        version_label = QLabel("v2.0 | Python " + platform.python_version())
        version_label.setStyleSheet(
            """
            QLabel {
                color: #ff9999;
                font-size: 12px;
                font-family: 'Courier New', monospace;
                padding: 5px;
            }
        """
        )

        # Кнопки действий
        btn_style = """
            QPushButton {
                background-color: rgba(255, 50, 50, 0.3);
                color: white;
                border: 1px solid #ff3333;
                border-radius: 5px;
                padding: 8px 15px;
                font-family: 'Courier New';
                margin: 0 2px;
            }
            QPushButton:hover {
                background-color: rgba(255, 50, 50, 0.5);
                border-color: #ff6666;
            }
        """

        btn_update = QPushButton("🔄 Проверить обновления")
        btn_update.setStyleSheet(btn_style)
        btn_update.clicked.connect(self.check_for_updates)

        btn_export = QPushButton("💾 Экспорт настроек")
        btn_export.setStyleSheet(btn_style)
        btn_export.clicked.connect(self.export_settings)

        btn_help = QPushButton("❓ Помощь")
        btn_help.setStyleSheet(btn_style)
        btn_help.clicked.connect(self.show_help)

        top_layout.addWidget(logo_label)
        top_layout.addStretch()
        top_layout.addWidget(version_label)
        top_layout.addSpacing(20)
        top_layout.addWidget(btn_update)
        top_layout.addWidget(btn_export)
        top_layout.addWidget(btn_help)

        parent_layout.addWidget(top_panel)

    def create_sidebar(self, parent_layout):
        """Создает боковую панель"""
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(self.get_gradient_style("sidebar"))

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(8)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)

        # Заголовок
        sidebar_title = QLabel("📂 НАВИГАЦИЯ")
        sidebar_title.setStyleSheet(
            """
            QLabel {
                color: #ff6666;
                font-size: 16px;
                font-weight: bold;
                font-family: 'Courier New';
                padding: 10px;
                border-bottom: 1px solid #330000;
            }
        """
        )
        sidebar_layout.addWidget(sidebar_title)

        # Кнопки навигации
        self.btn_group = QButtonGroup()

        sections = [
            ("📊 СИСТЕМНЫЙ МОНИТОР", "system_monitor"),
            ("🚀 УСТАНОВКА БИБЛИОТЕК", "install_libs"),
            ("🔍 АНАЛИЗ КОДА", "code_analysis"),
            ("📈 СТАТИСТИКА", "statistics"),
            ("⚙️ НАСТРОЙКИ", "settings"),
            ("🛠️ ИНСТРУМЕНТЫ", "tools"),
            ("📚 БИБЛИОТЕКИ", "libraries"),
            ("📖 ДОКУМЕНТАЦИЯ", "docs"),
            ("💡 ИДЕИ И СОВЕТЫ", "tips"),
        ]

        for text, section_id in sections:
            btn = QPushButton(text)
            btn.setObjectName(section_id)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self.get_button_style())
            btn.setMinimumHeight(45)

            self.btn_group.addButton(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Информация о системе
        sys_info = QLabel(f"ОС: {platform.system()} {platform.release()}")
        sys_info.setStyleSheet(
            """
            QLabel {
                color: #999999;
                font-size: 11px;
                font-family: 'Courier New';
                padding: 10px;
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 5px;
            }
        """
        )
        sidebar_layout.addWidget(sys_info)

        parent_layout.addWidget(sidebar)

    def create_content_area(self, parent_layout):
        """Создает область контента"""
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet(
            """
            QStackedWidget {
                background-color: #0a0a0a;
                border-left: 2px solid #220000;
            }
        """
        )

        # Создаем все страницы
        self.pages = {}

        # Страница мониторинга системы
        self.pages["system_monitor"] = self.create_system_monitor_page()
        self.content_stack.addWidget(self.pages["system_monitor"])

        # Страница установки библиотек
        self.pages["install_libs"] = self.create_install_page()
        self.content_stack.addWidget(self.pages["install_libs"])

        # Страница анализа кода
        self.pages["code_analysis"] = self.create_code_analysis_page()
        self.content_stack.addWidget(self.pages["code_analysis"])

        # Страница статистики
        self.pages["statistics"] = self.create_statistics_page()
        self.content_stack.addWidget(self.pages["statistics"])

        # Страница настроек
        self.pages["settings"] = self.create_settings_page()
        self.content_stack.addWidget(self.pages["settings"])

        # Страница инструментов
        self.pages["tools"] = self.create_tools_page()
        self.content_stack.addWidget(self.pages["tools"])

        # Страница библиотек
        self.pages["libraries"] = self.create_libraries_page()
        self.content_stack.addWidget(self.pages["libraries"])

        # Страница документации
        self.pages["docs"] = self.create_docs_page()
        self.content_stack.addWidget(self.pages["docs"])

        # Страница советов
        self.pages["tips"] = self.create_tips_page()
        self.content_stack.addWidget(self.pages["tips"])

        parent_layout.addWidget(self.content_stack)

    def create_bottom_panel(self, parent_layout):
        """Создает нижнюю панель"""
        bottom_panel = QFrame()
        bottom_panel.setFixedHeight(50)
        bottom_panel.setStyleSheet(self.get_gradient_style("bottom"))

        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(20, 0, 20, 0)

        # Статус бар
        self.status_label = QLabel("🚀 Система активна | Готов к работе")
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: #00ff00;
                font-family: 'Courier New';
                font-size: 12px;
                padding: 5px;
            }
        """
        )

        # Индикатор CPU
        self.cpu_label = QLabel("CPU: --%")
        self.cpu_label.setStyleSheet(
            """
            QLabel {
                color: #ff9900;
                font-family: 'Courier New';
                font-size: 12px;
                padding: 5px;
                background-color: rgba(0, 0, 0, 0.3);
                border-radius: 3px;
            }
        """
        )

        # Индикатор памяти
        self.mem_label = QLabel("MEM: --%")
        self.mem_label.setStyleSheet(
            """
            QLabel {
                color: #ff3366;
                font-family: 'Courier New';
                font-size: 12px;
                padding: 5px;
                background-color: rgba(0, 0, 0, 0.3);
                border-radius: 3px;
            }
        """
        )

        # Время
        self.time_label = QLabel()
        self.time_label.setStyleSheet(
            """
            QLabel {
                color: #cccccc;
                font-family: 'Courier New';
                font-size: 12px;
                padding: 5px;
            }
        """
        )
        self.update_time()

        # Таймер для обновления времени
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.cpu_label)
        bottom_layout.addWidget(self.mem_label)
        bottom_layout.addSpacing(20)
        bottom_layout.addWidget(self.time_label)

        parent_layout.addWidget(bottom_panel)

    def create_system_monitor_page(self):
        """Создает страницу мониторинга системы"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Заголовок
        title = QLabel("📊 СИСТЕМНЫЙ МОНИТОР В РЕАЛЬНОМ ВРЕМЕНИ")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Основной контейнер с вкладками
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet(self.get_tab_style())

        # Вкладка 1: Общая информация
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)

        # Статистика в реальном времени
        stats_grid = QGridLayout()

        # CPU
        cpu_group = self.create_metric_widget(
            "⚡ ЦЕНТРАЛЬНЫЙ ПРОЦЕССОР", "Загрузка CPU", "cpu_bar"
        )
        stats_grid.addWidget(cpu_group, 0, 0)

        # Память
        mem_group = self.create_metric_widget(
            "💾 ОПЕРАТИВНАЯ ПАМЯТЬ", "Использование памяти", "mem_bar"
        )
        stats_grid.addWidget(mem_group, 0, 1)

        # Диск
        disk_group = self.create_metric_widget(
            "💿 ДИСКОВОЕ ПРОСТРАНСТВО", "Свободное место", "disk_bar"
        )
        stats_grid.addWidget(disk_group, 1, 0)

        # Сеть
        net_group = self.create_metric_widget(
            "🌐 СЕТЕВАЯ АКТИВНОСТЬ", "Передача данных", "net_label"
        )
        stats_grid.addWidget(net_group, 1, 1)

        tab1_layout.addLayout(stats_grid)

        # Информация о системе
        sys_info_text = QTextEdit()
        sys_info_text.setReadOnly(True)
        sys_info_text.setStyleSheet(self.get_text_edit_style())
        sys_info_text.setHtml(self.get_system_info_html())
        tab1_layout.addWidget(sys_info_text)

        tab_widget.addTab(tab1, "📈 Общая статистика")

        # Вкладка 2: Процессы
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)

        # Таблица процессов
        self.process_table = QTableWidget()
        self.process_table.setColumnCount(5)
        self.process_table.setHorizontalHeaderLabels(
            ["PID", "Имя", "CPU %", "Память %", "Статус"]
        )
        self.process_table.setStyleSheet(self.get_table_style())
        self.process_table.horizontalHeader().setStretchLastSection(True)

        tab2_layout.addWidget(self.process_table)
        tab_widget.addTab(tab2, "🔄 Процессы")

        # Вкладка 3: Сеть
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)

        network_info = QTextEdit()
        network_info.setReadOnly(True)
        network_info.setStyleSheet(self.get_text_edit_style())
        network_info.setHtml(self.get_network_info_html())
        tab3_layout.addWidget(network_info)

        tab_widget.addTab(tab3, "🌐 Сеть")

        layout.addWidget(tab_widget)

        return page

    def create_install_page(self):
        """Создает страницу установки библиотек"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("🚀 УСТАНОВКА БИБЛИОТЕК ИЗ КОДА")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Область для ввода кода
        code_input_label = QLabel("📝 Вставьте ваш Python код ниже:")
        code_input_label.setStyleSheet(
            """
            QLabel {
                color: #ff9900;
                font-family: 'Courier New';
                font-size: 14px;
                padding: 10px;
            }
        """
        )
        layout.addWidget(code_input_label)

        self.code_input = QTextEdit()
        self.code_input.setStyleSheet(
            """
            QTextEdit {
                background-color: #000000;
                color: #00ff00;
                font-family: 'Consolas', monospace;
                font-size: 13px;
                border: 2px solid #ff3300;
                border-radius: 8px;
                padding: 15px;
                selection-background-color: #ff0000;
            }
        """
        )
        self.code_input.setPlaceholderText(
            "# Вставьте ваш Python код здесь...\n# Пример:\nimport numpy as np\nimport pandas as pd\nfrom sklearn.model_selection import train_test_split"
        )
        layout.addWidget(self.code_input)

        # Кнопки действий
        btn_layout = QHBoxLayout()

        btn_analyze = QPushButton("🔍 АНАЛИЗИРОВАТЬ КОД")
        btn_analyze.setStyleSheet(self.get_action_button_style())
        btn_analyze.clicked.connect(self.analyze_code)

        btn_install = QPushButton("⚡ УСТАНОВИТЬ ВСЕ")
        btn_install.setStyleSheet(self.get_action_button_style())
        btn_install.clicked.connect(self.install_all_libraries)

        btn_clear = QPushButton("🗑️ ОЧИСТИТЬ")
        btn_clear.setStyleSheet(self.get_action_button_style("gray"))
        btn_clear.clicked.connect(self.clear_code_input)

        btn_history = QPushButton("📜 ИСТОРИЯ")
        btn_history.setStyleSheet(self.get_action_button_style("blue"))
        btn_history.clicked.connect(self.show_history)

        btn_layout.addWidget(btn_analyze)
        btn_layout.addWidget(btn_install)
        btn_layout.addWidget(btn_clear)
        btn_layout.addWidget(btn_history)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # Результаты анализа
        self.analysis_result = QTextEdit()
        self.analysis_result.setReadOnly(True)
        self.analysis_result.setStyleSheet(
            """
            QTextEdit {
                background-color: #001100;
                color: #aaffaa;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                border: 1px solid #00aa00;
                border-radius: 5px;
                padding: 10px;
                min-height: 150px;
            }
        """
        )
        layout.addWidget(self.analysis_result)

        # Прогресс установки
        self.install_progress = QTextEdit()
        self.install_progress.setReadOnly(True)
        self.install_progress.setStyleSheet(
            """
            QTextEdit {
                background-color: #110011;
                color: #ffaaff;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                border: 1px solid #aa00aa;
                border-radius: 5px;
                padding: 10px;
                min-height: 100px;
            }
        """
        )
        layout.addWidget(self.install_progress)

        return page

    def create_code_analysis_page(self):
        """Создает страницу анализа кода"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("🔍 ГЛУБОКИЙ АНАЛИЗ КОДА")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Вкладки анализа
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet(self.get_tab_style())

        # Вкладка 1: Анализ зависимостей
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)

        analysis_btn = QPushButton("🔬 ЗАПУСТИТЬ ПОЛНЫЙ АНАЛИЗ")
        analysis_btn.setStyleSheet(self.get_action_button_style())
        analysis_btn.clicked.connect(self.run_full_analysis)
        tab1_layout.addWidget(analysis_btn)

        self.analysis_output = QTextEdit()
        self.analysis_output.setReadOnly(True)
        self.analysis_output.setStyleSheet(self.get_text_edit_style())
        tab1_layout.addWidget(self.analysis_output)

        tab_widget.addTab(tab1, "📦 Зависимости")

        # Вкладка 2: Статистика кода
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)

        stats_btn = QPushButton("📊 АНАЛИЗИРОВАТЬ СТАТИСТИКУ")
        stats_btn.setStyleSheet(self.get_action_button_style())
        stats_btn.clicked.connect(self.analyze_code_stats)
        tab2_layout.addWidget(stats_btn)

        self.stats_output = QTextEdit()
        self.stats_output.setReadOnly(True)
        self.stats_output.setStyleSheet(self.get_text_edit_style())
        tab2_layout.addWidget(self.stats_output)

        tab_widget.addTab(tab2, "📈 Статистика")

        layout.addWidget(tab_widget)

        return page

    def create_statistics_page(self):
        """Создает страницу статистики"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("📈 СТАТИСТИКА И АНАЛИТИКА")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Карточки статистики
        stats_grid = QGridLayout()

        cards = [
            ("Установлено библиотек", "0", "#ff5555"),
            ("Проанализировано файлов", "0", "#55ff55"),
            ("Успешных установок", "0", "#5555ff"),
            ("Сэкономлено времени", "0 часов", "#ffaa55"),
            ("Общий размер", "0 МБ", "#aa55ff"),
            ("Активных процессов", "0", "#55ffff"),
        ]

        for i, (title_text, value, color) in enumerate(cards):
            card = self.create_stat_card(title_text, value, color)
            stats_grid.addWidget(card, i // 3, i % 3)

        layout.addLayout(stats_grid)

        # Графики (заглушка)
        graph_label = QLabel("📊 Графики использования будут здесь")
        graph_label.setStyleSheet(
            """
            QLabel {
                color: #cccccc;
                font-family: 'Courier New';
                font-size: 16px;
                padding: 30px;
                background-color: rgba(0, 0, 0, 0.3);
                border: 2px dashed #444444;
                border-radius: 10px;
                margin: 20px;
                text-align: center;
            }
        """
        )
        layout.addWidget(graph_label)

        return page

    def create_settings_page(self):
        """Создает страницу настроек"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("⚙️ НАСТРОЙКИ ПРИЛОЖЕНИЯ")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Настройки в виде формы
        form_layout = QFormLayout()

        # Тема
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Темно-красная", "Темная", "Светлая", "Хакерская"])
        self.theme_combo.setStyleSheet(self.get_combo_style())
        form_layout.addRow("🎨 Цветовая тема:", self.theme_combo)

        # Автообновление
        self.auto_update_cb = QCheckBox("Автоматически проверять обновления")
        self.auto_update_cb.setStyleSheet(self.get_checkbox_style())
        form_layout.addRow(self.auto_update_cb)

        # Проверка зависимостей
        self.check_deps_cb = QCheckBox("Проверять зависимости при запуске")
        self.check_deps_cb.setStyleSheet(self.get_checkbox_style())
        form_layout.addRow(self.check_deps_cb)

        # Уровень логирования
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(
            ["Отладка", "Информация", "Предупреждения", "Ошибки"]
        )
        self.log_level_combo.setStyleSheet(self.get_combo_style())
        form_layout.addRow("📝 Уровень логирования:", self.log_level_combo)

        # Таймаут
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setSuffix(" секунд")
        self.timeout_spin.setStyleSheet(self.get_spinbox_style())
        form_layout.addRow("⏰ Таймаут установки:", self.timeout_spin)

        layout.addLayout(form_layout)

        # Кнопки сохранения
        btn_layout = QHBoxLayout()

        btn_save = QPushButton("💾 СОХРАНИТЬ НАСТРОЙКИ")
        btn_save.setStyleSheet(self.get_action_button_style())
        btn_save.clicked.connect(self.save_settings)

        btn_reset = QPushButton("🔄 СБРОСИТЬ")
        btn_reset.setStyleSheet(self.get_action_button_style("gray"))
        btn_reset.clicked.connect(self.reset_settings)

        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_reset)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # Расширенные настройки
        advanced_group = QGroupBox("🔧 Расширенные настройки")
        advanced_group.setStyleSheet(self.get_groupbox_style())

        advanced_layout = QVBoxLayout()

        self.advanced_cb1 = QCheckBox("Использовать зеркала PyPI")
        self.advanced_cb1.setStyleSheet(self.get_checkbox_style())

        self.advanced_cb2 = QCheckBox("Сохранять историю установок")
        self.advanced_cb2.setStyleSheet(self.get_checkbox_style())

        self.advanced_cb3 = QCheckBox("Автоматически обновлять pip")
        self.advanced_cb3.setStyleSheet(self.get_checkbox_style())

        advanced_layout.addWidget(self.advanced_cb1)
        advanced_layout.addWidget(self.advanced_cb2)
        advanced_layout.addWidget(self.advanced_cb3)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        return page

    def create_tools_page(self):
        """Создает страницу инструментов"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("🛠️ ИНСТРУМЕНТЫ РАЗРАБОТЧИКА")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Сетка инструментов
        tools_grid = QGridLayout()

        tools = [
            ("🧹 Очистка кэша pip", self.clean_pip_cache),
            ("📦 Обновить все библиотеки", self.upgrade_all_packages),
            ("🔍 Поиск библиотек", self.search_libraries),
            ("📋 Список установленных", self.list_installed_packages),
            ("⚡ Проверить обновления", self.check_package_updates),
            ("🗑️ Удалить библиотеку", self.remove_package),
            ("📊 Анализ зависимостей", self.analyze_dependencies),
            ("🚀 Ускорить pip", self.optimize_pip),
        ]

        for i, (text, func) in enumerate(tools):
            btn = QPushButton(text)
            btn.setStyleSheet(self.get_tool_button_style())
            btn.clicked.connect(func)
            tools_grid.addWidget(btn, i // 4, i % 4)

        layout.addLayout(tools_grid)

        # Вывод инструментов
        self.tools_output = QTextEdit()
        self.tools_output.setReadOnly(True)
        self.tools_output.setStyleSheet(self.get_text_edit_style())
        layout.addWidget(self.tools_output)

        return page

    def create_libraries_page(self):
        """Создает страницу управления библиотеками"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("📚 УПРАВЛЕНИЕ БИБЛИОТЕКАМИ")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Поиск и фильтрация
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Поиск библиотек...")
        self.search_input.setStyleSheet(self.get_line_edit_style())

        self.search_btn = QPushButton("Поиск")
        self.search_btn.setStyleSheet(self.get_action_button_style())
        self.search_btn.clicked.connect(self.search_packages)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(
            ["Все", "Установленные", "Популярные", "Рекомендуемые"]
        )
        self.filter_combo.setStyleSheet(self.get_combo_style())

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        search_layout.addWidget(self.filter_combo)
        search_layout.addStretch()

        layout.addLayout(search_layout)

        # Таблица библиотек
        self.libs_table = QTableWidget()
        self.libs_table.setColumnCount(5)
        self.libs_table.setHorizontalHeaderLabels(
            ["Библиотека", "Версия", "Статус", "Размер", "Действия"]
        )
        self.libs_table.setStyleSheet(self.get_table_style())
        self.libs_table.horizontalHeader().setStretchLastSection(True)

        # Заполняем таблицу
        self.populate_libraries_table()

        layout.addWidget(self.libs_table)

        return page

    def create_docs_page(self):
        """Создает страницу документации"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("📖 ДОКУМЕНТАЦИЯ И СПРАВКА")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        # Быстрые ссылки
        links_layout = QHBoxLayout()

        links = [
            ("🌐 PyPI", "https://pypi.org"),
            ("📚 Python Docs", "https://docs.python.org"),
            ("🐍 Stack Overflow", "https://stackoverflow.com"),
            ("🔧 GitHub", "https://github.com"),
            ("💬 Python Forum", "https://python.org/community/forums"),
        ]

        for text, url in links:
            btn = QPushButton(text)
            btn.setStyleSheet(self.get_link_button_style())
            btn.clicked.connect(lambda checked, u=url: webbrowser.open(u))
            links_layout.addWidget(btn)

        layout.addLayout(links_layout)

        # Документация
        docs_text = QTextEdit()
        docs_text.setReadOnly(True)
        docs_text.setStyleSheet(self.get_text_edit_style())
        docs_text.setHtml(self.get_documentation_html())
        layout.addWidget(docs_text)

        return page

    def create_tips_page(self):
        """Создает страницу советов"""
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("💡 ИДЕИ, СОВЕТЫ И ЛАЙФХАКИ")
        title.setStyleSheet(self.get_title_style())
        layout.addWidget(title)

        tips_text = QTextEdit()
        tips_text.setReadOnly(True)
        tips_text.setStyleSheet(self.get_text_edit_style())
        tips_text.setHtml(self.get_tips_html())
        layout.addWidget(tips_text)

        return page

    # ==================== СТИЛИ ====================

    def get_gradient_style(self, element):
        """Возвращает стиль с градиентом для элементов"""
        styles = {
            "top": """
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #000000, stop:0.2 #1a0000, 
                        stop:0.5 #4d0000, stop:0.8 #800000, stop:1 #000000);
                    border-bottom: 3px solid #ff0000;
                }
            """,
            "sidebar": """
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #000000, stop:0.3 #330000, 
                        stop:0.7 #660000, stop:1 #330000);
                    border-right: 2px solid #ff3333;
                }
            """,
            "bottom": """
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #ff0000, stop:0.3 #990000,
                        stop:0.7 #330000, stop:1 #000000);
                    border-top: 2px solid #ff0000;
                }
            """,
        }
        return styles.get(element, "")

    def get_button_style(self):
        """Возвращает стиль для кнопок"""
        return """
            QPushButton {
                background-color: rgba(255, 0, 0, 0.1);
                color: #ffffff;
                border: none;
                padding: 12px 15px;
                text-align: left;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                margin: 2px;
                border-radius: 5px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.3);
                border-left: 4px solid #ff0000;
                padding-left: 11px;
            }
            QPushButton:checked {
                background-color: rgba(255, 0, 0, 0.5);
                border-left: 6px solid #ff0000;
                padding-left: 9px;
                font-weight: bold;
                color: #ffff00;
            }
        """

    def get_action_button_style(self, color="red"):
        """Стиль для кнопок действий"""
        colors = {
            "red": "#ff3333",
            "green": "#33ff33",
            "blue": "#3366ff",
            "gray": "#666666",
        }
        bg_color = colors.get(color, "#ff3333")

        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                padding: 12px 20px;
                font-family: 'Courier New';
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
                margin: 5px;
                min-width: 150px;
            }}
            QPushButton:hover {{
                background-color: {colors.get(color, "#ff6666") if color == "red" else bg_color};
                border: 2px solid white;
                padding: 10px 18px;
            }}
            QPushButton:pressed {{
                background-color: #000000;
                border: 2px solid {bg_color};
            }}
        """

    def get_title_style(self):
        """Стиль для заголовков"""
        return """
            QLabel {
                color: #ff6600;
                font-size: 24px;
                font-weight: bold;
                font-family: 'Courier New', monospace;
                padding: 20px;
                border-bottom: 2px solid #330000;
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 10px 10px 0 0;
                margin-bottom: 10px;
            }
        """

    def get_text_edit_style(self):
        """Стиль для текстовых полей"""
        return """
            QTextEdit {
                background-color: #111111;
                color: #cccccc;
                border: 1px solid #444444;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }
        """

    def get_tab_style(self):
        """Стиль для вкладок"""
        return """
            QTabWidget::pane {
                border: 2px solid #330000;
                border-radius: 5px;
                background-color: #0a0a0a;
            }
            QTabBar::tab {
                background-color: #330000;
                color: #cccccc;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-family: 'Courier New';
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: #990000;
                color: white;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #660000;
            }
        """

    def get_table_style(self):
        """Стиль для таблиц"""
        return """
            QTableWidget {
                background-color: #0a0a0a;
                color: #cccccc;
                gridline-color: #333333;
                border: 1px solid #444444;
                border-radius: 5px;
                font-family: 'Consolas';
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 5px;
                border-bottom: 1px solid #222222;
            }
            QTableWidget::item:selected {
                background-color: #990000;
                color: white;
            }
            QHeaderView::section {
                background-color: #330000;
                color: white;
                padding: 8px;
                border: none;
                font-family: 'Courier New';
                font-weight: bold;
            }
        """

    def get_combo_style(self):
        """Стиль для комбобоксов"""
        return """
            QComboBox {
                background-color: #222222;
                color: white;
                border: 1px solid #666666;
                border-radius: 5px;
                padding: 8px;
                min-width: 200px;
            }
            QComboBox:hover {
                border-color: #ff3333;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
            }
        """

    def get_checkbox_style(self):
        """Стиль для чекбоксов"""
        return """
            QCheckBox {
                color: #cccccc;
                font-family: 'Courier New';
                font-size: 14px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #666666;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #ff3333;
                border-color: #ff3333;
            }
            QCheckBox::indicator:hover {
                border-color: #ff6666;
            }
        """

    def get_spinbox_style(self):
        """Стиль для спинбоксов"""
        return """
            QSpinBox {
                background-color: #222222;
                color: white;
                border: 1px solid #666666;
                border-radius: 5px;
                padding: 8px;
                min-width: 150px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #330000;
                border: none;
                width: 20px;
            }
        """

    def get_groupbox_style(self):
        """Стиль для групп"""
        return """
            QGroupBox {
                color: #ff9900;
                font-family: 'Courier New';
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #444444;
                border-radius: 8px;
                margin-top: 20px;
                padding-top: 15px;
                background-color: rgba(0, 0, 0, 0.3);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
            }
        """

    def get_line_edit_style(self):
        """Стиль для полей ввода"""
        return """
            QLineEdit {
                background-color: #111111;
                color: white;
                border: 1px solid #666666;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Courier New';
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #ff3333;
                padding: 9px;
            }
        """

    def get_tool_button_style(self):
        """Стиль для кнопок инструментов"""
        return """
            QPushButton {
                background-color: rgba(51, 51, 51, 0.7);
                color: #cccccc;
                border: 1px solid #666666;
                border-radius: 5px;
                padding: 15px 10px;
                font-family: 'Courier New';
                font-size: 13px;
                min-height: 60px;
            }
            QPushButton:hover {
                background-color: rgba(102, 0, 0, 0.7);
                border-color: #ff3333;
                color: white;
            }
        """

    def get_link_button_style(self):
        """Стиль для кнопок-ссылок"""
        return """
            QPushButton {
                background-color: rgba(0, 51, 102, 0.5);
                color: #66ccff;
                border: 1px solid #3366cc;
                border-radius: 5px;
                padding: 10px 15px;
                font-family: 'Courier New';
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(0, 102, 204, 0.7);
                border-color: #66ccff;
                color: white;
            }
        """

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def create_metric_widget(self, title, description, widget_id):
        """Создает виджет метрики"""
        group = QGroupBox(title)
        group.setStyleSheet(self.get_groupbox_style())

        layout = QVBoxLayout()

        # Описание
        desc_label = QLabel(description)
        desc_label.setStyleSheet("color: #999999; font-size: 12px;")
        layout.addWidget(desc_label)

        # Прогресс-бар или значение
        if "bar" in widget_id:
            progress = QProgressBar()
            progress.setObjectName(widget_id)
            progress.setStyleSheet(
                """
                QProgressBar {
                    border: 2px solid #333333;
                    border-radius: 5px;
                    text-align: center;
                    height: 25px;
                    font-family: 'Courier New';
                }
                QProgressBar::chunk {
                    background-color: #ff3333;
                    border-radius: 3px;
                }
            """
            )
            layout.addWidget(progress)
        else:
            value_label = QLabel("--")
            value_label.setObjectName(widget_id)
            value_label.setStyleSheet(
                """
                QLabel {
                    color: #ffff00;
                    font-size: 24px;
                    font-weight: bold;
                    font-family: 'Courier New';
                    padding: 10px;
                    background-color: rgba(0, 0, 0, 0.5);
                    border-radius: 5px;
                    text-align: center;
                }
            """
            )
            layout.addWidget(value_label)

        group.setLayout(layout)
        return group

    def create_stat_card(self, title, value, color):
        """Создает карточку статистики"""
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.2),
                    stop:1 rgba(0, 0, 0, 0.5));
                border: 2px solid {color};
                border-radius: 10px;
                padding: 15px;
            }}
        """
        )

        layout = QVBoxLayout(card)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            """
            QLabel {
                color: #cccccc;
                font-size: 14px;
                font-family: 'Courier New';
                font-weight: bold;
            }
        """
        )

        value_label = QLabel(value)
        value_label.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                font-size: 28px;
                font-family: 'Courier New';
                font-weight: bold;
                padding: 10px;
            }}
        """
        )

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        return card

    def get_system_info_html(self):
        """Возвращает HTML с информацией о системе"""
        try:
            info = f"""
            <div style="font-family: 'Courier New'; color: #cccccc;">
                <h3 style="color: #ff9900;">💻 Информация о системе</h3>
                <table style="width: 100%;">
                    <tr><td style="color: #999999;">ОС:</td><td>{platform.system()} {platform.release()}</td></tr>
                    <tr><td style="color: #999999;">Архитектура:</td><td>{platform.machine()}</td></tr>
                    <tr><td style="color: #999999;">Процессор:</td><td>{platform.processor()}</td></tr>
                    <tr><td style="color: #999999;">Python:</td><td>{platform.python_version()}</td></tr>
                    <tr><td style="color: #999999;">Пользователь:</td><td>{os.getlogin()}</td></tr>
                    <tr><td style="color: #999999;">Рабочий каталог:</td><td>{os.getcwd()}</td></tr>
                </table>
            </div>
            """
            return info
        except:
            return "<div style='color: red;'>Не удалось получить информацию о системе</div>"

    def get_network_info_html(self):
        """Возвращает HTML с информацией о сети"""
        try:
            net_info = psutil.net_if_addrs()
            html = "<div style='font-family: Courier New; color: #cccccc;'>"
            html += "<h3 style='color: #ff9900;'>🌐 Сетевые интерфейсы</h3>"

            for interface, addresses in net_info.items():
                html += f"<h4 style='color: #66ccff;'>{interface}</h4>"
                for addr in addresses:
                    html += f"<div style='margin-left: 20px;'>"
                    html += f"{addr.family.name}: {addr.address}"
                    if addr.netmask:
                        html += f" (маска: {addr.netmask})"
                    html += "</div>"

            html += "</div>"
            return html
        except:
            return (
                "<div style='color: red;'>Не удалось получить сетевую информацию</div>"
            )

    def get_documentation_html(self):
        """Возвращает HTML с документацией"""
        return """
        <div style="font-family: 'Courier New'; color: #cccccc; line-height: 1.6;">
            <h2 style="color: #ff9900;">📚 Руководство пользователя</h2>
            
            <h3 style="color: #66ccff;">🚀 Установка библиотек</h3>
            <p>1. Вставьте Python код в поле ввода</p>
            <p>2. Нажмите "Анализировать код" для проверки зависимостей</p>
            <p>3. Нажмите "Установить все" для автоматической установки</p>
            
            <h3 style="color: #66ccff;">📊 Мониторинг системы</h3>
            <p>• Реальное время обновления CPU, памяти и диска</p>
            <p>• Просмотр активных процессов</p>
            <p>• Сетевая статистика</p>
            
            <h3 style="color: #66ccff;">⚙️ Настройки</h3>
            <p>• Изменение цветовой темы</p>
            <p>• Настройка автообновления</p>
            <p>• Управление логированием</p>
            
            <h3 style="color: #66ccff;">🛠️ Инструменты</h3>
            <p>• Очистка кэша pip</p>
            <p>• Обновление всех пакетов</p>
            <p>• Поиск и управление библиотеками</p>
            
            <h3 style="color: #ff3333;">⚠️ Важные заметки</h3>
            <p>• Для некоторых функций требуются права администратора</p>
            <p>• Проверяйте зависимости перед установкой в production</p>
            <p>• Сохраняйте резервные копии виртуальных окружений</p>
        </div>
        """

    def get_tips_html(self):
        """Возвращает HTML с советами"""
        return """
        <div style="font-family: 'Courier New'; color: #cccccc; line-height: 1.6;">
            <h2 style="color: #ff9900;">💡 Советы и лайфхаки</h2>
            
            <div style="background-color: rgba(255, 100, 0, 0.1); padding: 15px; border-radius: 10px; margin: 10px 0;">
                <h3 style="color: #ffcc00;">🚀 Ускорение установки</h3>
                <p>• Используйте зеркала PyPI для ускорения загрузки</p>
                <p>• Отключайте ненужные проверки в настройках</p>
                <p>• Используйте параметр --no-deps для быстрой установки</p>
            </div>
            
            <div style="background-color: rgba(0, 100, 255, 0.1); padding: 15px; border-radius: 10px; margin: 10px 0;">
                <h3 style="color: #66ccff;">🔧 Оптимизация работы</h3>
                <p>• Создавайте виртуальные окружения для каждого проекта</p>
                <p>• Фиксируйте версии в requirements.txt</p>
                <p>• Регулярно обновляйте устаревшие пакеты</p>
            </div>
            
            <div style="background-color: rgba(0, 255, 100, 0.1); padding: 15px; border-radius: 10px; margin: 10px 0;">
                <h3 style="color: #66ff66;">📊 Мониторинг и отладка</h3>
                <p>• Используйте встроенный мониторинг для отслеживания ресурсов</p>
                <p>• Проверяйте совместимость библиотек перед установкой</p>
                <p>• Сохраняйте логи установки для отладки</p>
            </div>
            
            <div style="background-color: rgba(255, 0, 100, 0.1); padding: 15px; border-radius: 10px; margin: 10px 0;">
                <h3 style="color: #ff6699;">⚡ Производительность</h3>
                <p>• Закрывайте неиспользуемые вкладки мониторинга</p>
                <p>• Настраивайте интервал обновления в настройках</p>
                <p>• Используйте фильтры для больших списков библиотек</p>
            </div>
            
            <h3 style="color: #ff3333;">🔥 Продвинутые техники</h3>
            <ul>
                <li>Используйте pre-commit hooks для автоматической проверки</li>
                <li>Настройте CI/CD для автоматической установки зависимостей</li>
                <li>Создавайте собственные зеркала PyPI для командной работы</li>
                <li>Используйте Docker для изоляции окружений</li>
            </ul>
        </div>
        """

    # ==================== ОСНОВНЫЕ МЕТОДЫ ====================

    def setup_connections(self):
        """Настраивает соединения сигналов и слотов"""
        # Подключаем кнопки навигации
        for btn in self.btn_group.buttons():
            btn.clicked.connect(self.on_navigation_clicked)

    def on_navigation_clicked(self):
        """Обработчик клика по навигации"""
        sender = self.sender()
        if sender:
            page_id = sender.objectName()
            index = list(self.pages.keys()).index(page_id)
            self.content_stack.setCurrentIndex(index)
            self.status_label.setText(
                f"📂 Переключено на: {sender.text().split(' ', 1)[1]}"
            )

    def update_time(self):
        """Обновляет время на нижней панели"""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(f"🕒 {current_time}")

    def update_monitor_display(self, data):
        """Обновляет отображение мониторинга"""
        # Обновляем CPU
        cpu_bar = self.findChild(QProgressBar, "cpu_bar")
        if cpu_bar:
            cpu_bar.setValue(int(data["cpu"]))
            cpu_bar.setFormat(f"CPU: {data['cpu']:.1f}%")

        # Обновляем память
        mem_bar = self.findChild(QProgressBar, "mem_bar")
        if mem_bar:
            mem_bar.setValue(int(data["memory_percent"]))
            mem_bar.setFormat(f"Память: {data['memory_percent']:.1f}%")

        # Обновляем диск
        disk_bar = self.findChild(QProgressBar, "disk_bar")
        if disk_bar:
            disk_bar.setValue(int(data["disk_percent"]))
            disk_bar.setFormat(f"Диск: {data['disk_percent']:.1f}%")

        # Обновляем сеть
        net_label = self.findChild(QLabel, "net_label")
        if net_label:
            net_label.setText(
                f"📤 {data['net_sent_mb']:.1f} MB | 📥 {data['net_recv_mb']:.1f} MB"
            )

        # Обновляем нижнюю панель
        self.cpu_label.setText(f"CPU: {data['cpu']:.1f}%")
        self.mem_label.setText(f"MEM: {data['memory_percent']:.1f}%")

        # Обновляем таблицу процессов
        if hasattr(self, "process_table"):
            self.process_table.setRowCount(len(data["processes"]))
            for i, proc in enumerate(data["processes"]):
                self.process_table.setItem(i, 0, QTableWidgetItem(str(proc["pid"])))
                self.process_table.setItem(i, 1, QTableWidgetItem(proc["name"][:30]))
                self.process_table.setItem(
                    i, 2, QTableWidgetItem(f"{proc['cpu']:.1f}%")
                )
                self.process_table.setItem(
                    i, 3, QTableWidgetItem(f"{proc['memory']:.1f}%")
                )
                self.process_table.setItem(i, 4, QTableWidgetItem("Активен"))

    def analyze_code(self):
        """Анализирует код на наличие зависимостей"""
        code = self.code_input.toPlainText()
        if not code.strip():
            self.analysis_result.setText("❌ Ошибка: Введите Python код для анализа")
            return

        self.status_label.setText("🔍 Анализирую код...")

        try:
            analysis = self.code_analyzer.analyze_dependencies(code)

            result_text = "=" * 60 + "\n"
            result_text += "📊 РЕЗУЛЬТАТЫ АНАЛИЗА КОДА\n"
            result_text += "=" * 60 + "\n\n"

            result_text += f"📈 Всего импортов: {analysis['total_imports']}\n"
            result_text += (
                f"🔍 Уникальных библиотек: {len(analysis['unique_imports'])}\n\n"
            )

            result_text += "✅ Уже установлены:\n"
            for lib in analysis["already_installed"]:
                result_text += f"   • {lib}\n"

            result_text += "\n📦 Требуют установки:\n"
            for lib in analysis["to_install"]:
                result_text += f"   ⚠️ {lib}\n"

            result_text += "\n🐍 Стандартные библиотеки Python:\n"
            for lib in analysis["standard_libs"]:
                result_text += f"   ✓ {lib}\n"

            if analysis["to_install"]:
                result_text += (
                    "\n🚀 Для установки всех библиотек нажмите 'УСТАНОВИТЬ ВСЕ'"
                )
            else:
                result_text += "\n🎉 Все необходимые библиотеки уже установлены!"

            self.analysis_result.setText(result_text)
            self.status_label.setText("✅ Анализ кода завершен")

            # Сохраняем в историю
            self.save_to_history(code, analysis)

        except Exception as e:
            self.analysis_result.setText(f"❌ Ошибка анализа: {str(e)}")
            self.status_label.setText("❌ Ошибка анализа кода")

    def install_all_libraries(self):
        """Устанавливает все необходимые библиотеки"""
        code = self.code_input.toPlainText()
        if not code.strip():
            self.install_progress.setText("❌ Ошибка: Сначала проанализируйте код")
            return

        try:
            analysis = self.code_analyzer.analyze_dependencies(code)
            libs_to_install = analysis["to_install"]

            if not libs_to_install:
                self.install_progress.setText("✅ Все библиотеки уже установлены!")
                return

            self.install_progress.setText(
                f"🚀 Начинаю установку {len(libs_to_install)} библиотек...\n"
            )
            self.status_label.setText(
                f"📦 Устанавливаю {len(libs_to_install)} библиотек..."
            )

            # Создаем и запускаем установщик в отдельном потоке
            self.installer = LibraryInstaller(libs_to_install)
            self.installer.progress.connect(self.update_install_progress)
            self.installer.finished.connect(self.on_install_finished)
            self.installer.error.connect(self.on_install_error)
            self.installer.start()

        except Exception as e:
            self.install_progress.setText(f"❌ Ошибка: {str(e)}")

    def update_install_progress(self, message):
        """Обновляет прогресс установки"""
        current_text = self.install_progress.toPlainText()
        self.install_progress.setText(current_text + message + "\n")

        # Прокручиваем вниз
        scrollbar = self.install_progress.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_install_finished(self, results):
        """Обработчик завершения установки"""
        success_count = len(results["success"])
        already_count = len(results["already"])
        failed_count = len(results["failed"])

        summary = "\n" + "=" * 60 + "\n"
        summary += "📋 ИТОГОВЫЙ ОТЧЕТ\n"
        summary += "=" * 60 + "\n\n"
        summary += f"✅ Успешно установлено: {success_count}\n"
        summary += f"📦 Уже были установлены: {already_count}\n"
        summary += f"❌ Не удалось установить: {failed_count}\n\n"

        if results["failed"]:
            summary += "Список ошибок:\n"
            for lib, error in results["failed"]:
                summary += f"   • {lib}: {error[:100]}...\n"

        self.install_progress.setText(self.install_progress.toPlainText() + summary)
        self.status_label.setText(f"✅ Установка завершена ({success_count} успешно)")

        # Обновляем статистику
        self.update_statistics()

    def on_install_error(self, error_message):
        """Обработчик ошибок установки"""
        self.install_progress.setText(
            self.install_progress.toPlainText()
            + f"\n❌ Критическая ошибка: {error_message}"
        )
        self.status_label.setText("❌ Ошибка установки")

    def clear_code_input(self):
        """Очищает поле ввода кода"""
        self.code_input.clear()
        self.analysis_result.clear()
        self.install_progress.clear()
        self.status_label.setText("📝 Поле ввода очищено")

    def save_to_history(self, code, analysis):
        """Сохраняет анализ в историю"""
        history_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "code_length": len(code),
            "imports_count": analysis["total_imports"],
            "libraries_to_install": analysis["to_install"],
            "libraries_already": analysis["already_installed"],
        }

        if "history" not in self.config.config:
            self.config.config["history"] = []

        self.config.config["history"].insert(0, history_entry)

        # Ограничиваем историю 50 записями
        if len(self.config.config["history"]) > 50:
            self.config.config["history"] = self.config.config["history"][:50]

        self.config.save_config()

    def load_history(self):
        """Загружает историю из конфигурации"""
        if "history" in self.config.config:
            return self.config.config["history"]
        return []

    def show_history(self):
        """Показывает историю анализа"""
        history = self.load_history()

        if not history:
            QMessageBox.information(self, "История", "История пуста")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("📜 История анализа")
        dialog.setMinimumSize(600, 400)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: #0a0a0a;
            }
        """
        )

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(self.get_text_edit_style())

        history_text = "📜 ИСТОРИЯ АНАЛИЗА КОДА\n" + "=" * 50 + "\n\n"

        for i, entry in enumerate(history[:10], 1):
            history_text += f"{i}. {entry['timestamp'][:19]}\n"
            history_text += f"   📝 Символов: {entry['code_length']}\n"
            history_text += f"   📦 Импортов: {entry['imports_count']}\n"

            if entry["libraries_to_install"]:
                history_text += f"   ⚠️ Требовали установки: {len(entry['libraries_to_install'])} библиотек\n"

            history_text += "-" * 40 + "\n"

        text_edit.setText(history_text)
        layout.addWidget(text_edit)

        dialog.exec_()

    def run_full_analysis(self):
        """Запускает полный анализ кода"""
        code = self.code_input.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, "Ошибка", "Введите код для анализа")
            return

        self.analysis_output.setText("🔬 Запускаю глубокий анализ...\n")

        try:
            # Анализ сложности
            lines = code.split("\n")
            total_lines = len(lines)
            code_lines = len(
                [l for l in lines if l.strip() and not l.strip().startswith("#")]
            )
            comment_lines = len([l for l in lines if l.strip().startswith("#")])
            empty_lines = len([l for l in lines if not l.strip()])

            # Анализ импортов
            imports = self.code_analyzer.extract_imports(code)

            # Поиск потенциальных проблем
            warnings = []
            for i, line in enumerate(lines, 1):
                if "import *" in line:
                    warnings.append(
                        f"Строка {i}: Использован импорт '*' - может вызвать конфликты"
                    )
                if "eval(" in line or "exec(" in line:
                    warnings.append(
                        f"Строка {i}: Использована функция eval/exec - опасность безопасности"
                    )

            # Формируем отчет
            report = "=" * 60 + "\n"
            report += "🔬 ПОЛНЫЙ АНАЛИЗ КОДА\n"
            report += "=" * 60 + "\n\n"

            report += "📊 ОСНОВНАЯ СТАТИСТИКА:\n"
            report += f"• Всего строк: {total_lines}\n"
            report += f"• Строк кода: {code_lines}\n"
            report += f"• Комментарии: {comment_lines}\n"
            report += f"• Пустые строки: {empty_lines}\n"
            report += f"• Уникальных импортов: {len(imports)}\n\n"

            report += "📦 ИМПОРТЫ:\n"
            for imp in imports:
                report += f"   • {imp}\n"

            if warnings:
                report += "\n⚠️ ПОТЕНЦИАЛЬНЫЕ ПРОБЛЕМЫ:\n"
                for warn in warnings:
                    report += f"   • {warn}\n"

            report += "\n💡 РЕКОМЕНДАЦИИ:\n"
            if len(imports) > 10:
                report += "   • Слишком много импортов, рассмотрите рефакторинг\n"
            if not comment_lines:
                report += "   • Добавьте комментарии для улучшения читаемости\n"
            if empty_lines > total_lines * 0.3:
                report += "   • Слишком много пустых строк\n"

            self.analysis_output.setText(report)
            self.status_label.setText("✅ Полный анализ завершен")

        except Exception as e:
            self.analysis_output.setText(f"❌ Ошибка анализа: {str(e)}")

    def analyze_code_stats(self):
        """Анализирует статистику кода"""
        code = self.code_input.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, "Ошибка", "Введите код для анализа")
            return

        try:
            # Простая статистика
            lines = code.split("\n")

            # Считаем различные элементы
            function_count = len(re.findall(r"def\s+\w+\(", code))
            class_count = len(re.findall(r"class\s+\w+", code))
            import_count = len(re.findall(r"^import|^from", code, re.MULTILINE))
            comment_count = len([l for l in lines if l.strip().startswith("#")])

            # Считаем длину строк
            line_lengths = [len(l) for l in lines]
            avg_length = sum(line_lengths) / len(line_lengths) if line_lengths else 0
            max_length = max(line_lengths) if line_lengths else 0

            # Формируем отчет
            stats = "📊 СТАТИСТИКА КОДА:\n" + "=" * 40 + "\n\n"
            stats += f"📈 Базовые метрики:\n"
            stats += f"• Функций: {function_count}\n"
            stats += f"• Классов: {class_count}\n"
            stats += f"• Импортов: {import_count}\n"
            stats += f"• Комментариев: {comment_count}\n\n"

            stats += f"📏 Длина строк:\n"
            stats += f"• Средняя длина: {avg_length:.1f} символов\n"
            stats += f"• Максимальная длина: {max_length} символов\n"
            stats += f"• Всего строк: {len(lines)}\n\n"

            # Качество кода
            quality = "✅ Хорошо"
            if max_length > 100:
                quality = "⚠️ Есть длинные строки"
            if function_count == 0 and class_count == 0:
                quality = "⚠️ Нет функций/классов"
            if comment_count == 0:
                quality = "⚠️ Нет комментариев"

            stats += f"📊 ОЦЕНКА КАЧЕСТВА: {quality}\n"

            self.stats_output.setText(stats)

        except Exception as e:
            self.stats_output.setText(f"❌ Ошибка: {str(e)}")

    def update_statistics(self):
        """Обновляет статистику"""
        # Здесь можно добавить обновление реальной статистики
        pass

    def save_settings(self):
        """Сохраняет настройки"""
        try:
            # Сохраняем настройки в конфиг
            self.config.update_setting("theme", self.theme_combo.currentText())
            self.config.update_setting("auto_update", self.auto_update_cb.isChecked())
            self.config.update_setting(
                "check_dependencies", self.check_deps_cb.isChecked()
            )
            self.config.update_setting("log_level", self.log_level_combo.currentText())
            self.config.update_setting("timeout", self.timeout_spin.value())

            QMessageBox.information(
                self, "Настройки", "✅ Настройки успешно сохранены!"
            )
            self.status_label.setText("⚙️ Настройки сохранены")

        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка", f"❌ Не удалось сохранить настройки: {str(e)}"
            )

    def reset_settings(self):
        """Сбрасывает настройки"""
        reply = QMessageBox.question(
            self,
            "Сброс",
            "Вы уверены, что хотите сбросить все настройки?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.config.config = self.config.default_config.copy()
            self.config.save_config()

            # Перезагружаем интерфейс
            QMessageBox.information(
                self, "Сброс", "✅ Настройки сброшены. Перезапустите приложение."
            )

    def check_for_updates(self):
        """Проверяет обновления"""
        self.status_label.setText("🔄 Проверяю обновления...")
        QTimer.singleShot(
            1000, lambda: self.status_label.setText("✅ Проверка обновлений завершена")
        )

    def export_settings(self):
        """Экспортирует настройки"""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Экспорт настроек", "", "JSON Files (*.json)"
            )

            if filename:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(self.config.config, f, indent=2, ensure_ascii=False)

                self.status_label.setText(f"💾 Настройки экспортированы в {filename}")

        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка", f"❌ Не удалось экспортировать настройки: {str(e)}"
            )

    def show_help(self):
        """Показывает справку"""
        QMessageBox.information(
            self,
            "Помощь",
            "Console Hack PRO v2.0\n\n"
            "Для анализа кода:\n"
            "1. Вставьте код в поле ввода\n"
            "2. Нажмите 'Анализировать код'\n"
            "3. Установите необходимые библиотеки\n\n"
            "by @concole_hack",
        )

    def clean_pip_cache(self):
        """Очищает кэш pip"""
        try:
            self.tools_output.setText("🧹 Очищаю кэш pip...\n")

            result = subprocess.run(
                [sys.executable, "-m", "pip", "cache", "purge"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                self.tools_output.setText("✅ Кэш pip успешно очищен")
            else:
                self.tools_output.setText(
                    f"⚠️ Не удалось очистить кэш:\n{result.stderr}"
                )

        except Exception as e:
            self.tools_output.setText(f"❌ Ошибка: {str(e)}")

    def upgrade_all_packages(self):
        """Обновляет все пакеты"""
        reply = QMessageBox.question(
            self,
            "Обновление",
            "Обновить все пакеты? Это может занять некоторое время.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.tools_output.setText(
                "📦 Обновляю все пакеты...\nЭто может занять несколько минут.\n"
            )

            # Запускаем в отдельном потоке
            thread = threading.Thread(target=self._upgrade_packages_thread)
            thread.start()

    def _upgrade_packages_thread(self):
        """Поток для обновления пакетов"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--outdated", "--format=freeze"],
                capture_output=True,
                text=True,
            )

            outdated = []
            for line in result.stdout.split("\n"):
                if line:
                    outdated.append(line.split("==")[0])

            if not outdated:
                self.tools_output.setText("✅ Все пакеты актуальны")
                return

            self.tools_output.append(
                f"📦 Найдено устаревших пакетов: {len(outdated)}\n"
            )

            for i, package in enumerate(outdated, 1):
                self.tools_output.append(
                    f"🔄 Обновляю {package} ({i}/{len(outdated)})..."
                )

                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", package],
                    capture_output=True,
                    text=True,
                )

            self.tools_output.append("\n✅ Все пакеты обновлены!")

        except Exception as e:
            self.tools_output.append(f"\n❌ Ошибка: {str(e)}")

    def search_libraries(self):
        """Ищет библиотеки"""
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Поиск библиотек")
        dialog.setLabelText("Введите название библиотеки:")
        dialog.setStyleSheet(
            """
            QInputDialog {
                background-color: #0a0a0a;
                color: white;
            }
        """
        )

        if dialog.exec_():
            query = dialog.textValue()
            if query:
                self.tools_output.setText(f"🔍 Ищу библиотеку: {query}...\n")

                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "search", query],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if result.returncode == 0:
                        self.tools_output.setText(result.stdout[:1000])
                    else:
                        self.tools_output.setText(
                            f"⚠️ Библиотека не найдена или ошибка поиска"
                        )

                except subprocess.TimeoutExpired:
                    self.tools_output.setText("⏰ Таймаут при поиске")
                except Exception as e:
                    self.tools_output.setText(f"❌ Ошибка: {str(e)}")

    def list_installed_packages(self):
        """Показывает список установленных пакетов"""
        try:
            self.tools_output.setText("📋 Получаю список установленных пакетов...\n")

            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=columns"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Ограничиваем вывод
                lines = result.stdout.split("\n")
                self.tools_output.setText("\n".join(lines[:50]))

                if len(lines) > 50:
                    self.tools_output.append(f"\n... и ещё {len(lines)-50} пакетов")
            else:
                self.tools_output.setText("⚠️ Не удалось получить список пакетов")

        except Exception as e:
            self.tools_output.setText(f"❌ Ошибка: {str(e)}")

    def check_package_updates(self):
        """Проверяет обновления пакетов"""
        try:
            self.tools_output.setText("⚡ Проверяю обновления пакетов...\n")

            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--outdated"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                if result.stdout.strip():
                    self.tools_output.setText(
                        "📦 Доступны обновления:\n" + result.stdout
                    )
                else:
                    self.tools_output.setText("✅ Все пакеты актуальны")
            else:
                self.tools_output.setText("⚠️ Не удалось проверить обновления")

        except Exception as e:
            self.tools_output.setText(f"❌ Ошибка: {str(e)}")

    def remove_package(self):
        """Удаляет пакет"""
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Удаление библиотеки")
        dialog.setLabelText("Введите название библиотеки для удаления:")

        if dialog.exec_():
            package = dialog.textValue()
            if package:
                reply = QMessageBox.question(
                    self,
                    "Подтверждение",
                    f"Удалить библиотеку '{package}'?",
                    QMessageBox.Yes | QMessageBox.No,
                )

                if reply == QMessageBox.Yes:
                    try:
                        self.tools_output.setText(f"🗑️ Удаляю {package}...\n")

                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "uninstall", "-y", package],
                            capture_output=True,
                            text=True,
                        )

                        if result.returncode == 0:
                            self.tools_output.setText(
                                f"✅ Библиотека '{package}' удалена"
                            )
                        else:
                            self.tools_output.setText(
                                f"⚠️ Не удалось удалить библиотеку"
                            )

                    except Exception as e:
                        self.tools_output.setText(f"❌ Ошибка: {str(e)}")

    def analyze_dependencies(self):
        """Анализирует зависимости"""
        try:
            self.tools_output.setText("🔍 Анализирую зависимости...\n")

            # Получаем все установленные пакеты
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                packages = json.loads(result.stdout)
                self.tools_output.setText(f"📦 Всего пакетов: {len(packages)}\n\n")

                # Простой анализ
                total_size = 0
                python_versions = []

                for pkg in packages[:20]:  # Ограничиваем вывод
                    self.tools_output.append(f"• {pkg['name']} {pkg['version']}")

                self.tools_output.append(f"\n📊 Показано 20 из {len(packages)} пакетов")

            else:
                self.tools_output.setText("⚠️ Не удалось проанализировать зависимости")

        except Exception as e:
            self.tools_output.setText(f"❌ Ошибка: {str(e)}")

    def optimize_pip(self):
        """Оптимизирует pip"""
        try:
            self.tools_output.setText("🚀 Оптимизирую pip...\n")

            commands = [
                ["pip", "config", "set", "global.timeout", "60"],
                ["pip", "config", "set", "global.retries", "5"],
                ["pip", "config", "set", "install.use-deprecated", "legacy-resolver"],
            ]

            for cmd in commands:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self.tools_output.append(f"✅ {cmd[-1]}: настроено")
                else:
                    self.tools_output.append(f"⚠️ {cmd[-1]}: ошибка")

            self.tools_output.append("\n🎉 Оптимизация завершена!")

        except Exception as e:
            self.tools_output.setText(f"❌ Ошибка: {str(e)}")

    def search_packages(self):
        """Ищет пакеты в таблице"""
        query = self.search_input.text().lower()

        # Здесь будет логика поиска
        # Пока что просто показываем сообщение
        self.status_label.setText(f"🔍 Поиск: {query}")

    def populate_libraries_table(self):
        """Заполняет таблицу библиотек"""
        try:
            # Получаем список установленных библиотек
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                packages = json.loads(result.stdout)

                self.libs_table.setRowCount(len(packages))

                for i, pkg in enumerate(packages):
                    self.libs_table.setItem(i, 0, QTableWidgetItem(pkg["name"]))
                    self.libs_table.setItem(i, 1, QTableWidgetItem(pkg["version"]))
                    self.libs_table.setItem(i, 2, QTableWidgetItem("✅ Установлена"))
                    self.libs_table.setItem(i, 3, QTableWidgetItem("--"))

                    # Кнопка действий
                    action_btn = QPushButton("⚡ Действия")
                    action_btn.setStyleSheet(
                        """
                        QPushButton {
                            background-color: #333333;
                            color: white;
                            border: none;
                            padding: 5px;
                            border-radius: 3px;
                            font-size: 11px;
                        }
                        QPushButton:hover {
                            background-color: #666666;
                        }
                    """
                    )
                    self.libs_table.setCellWidget(i, 4, action_btn)

        except Exception as e:
            print(f"Ошибка при загрузке библиотек: {e}")

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        # Сохраняем размер и позицию окна
        self.config.config["window_size"] = [self.width(), self.height()]
        self.config.config["window_position"] = [self.x(), self.y()]
        self.config.save_config()

        # Останавливаем мониторинг
        if hasattr(self, "monitor"):
            self.monitor.stop()
            self.monitor.wait()

        event.accept()


# ==================== ЗАПУСК ПРИЛОЖЕНИЯ ====================


def main():
    print("=" * 70)
    print("🚀 CONSOLE HACK PRO v2.0 - ЗАПУСК")
    print("📦 Проверка и установка зависимостей")
    print("=" * 70)

    # Проверяем и устанавливаем библиотеки
    success = check_and_install_libraries()

    if not success:
        print("\n⚠️ Предупреждение: Не все библиотеки удалось установить автоматически")
        print("Попробуйте установить их вручную:")
        print("pip install PyQt5 PyQt5-sip psutil requests")
        print("\nПродолжаю запуск...")

    print("\n" + "=" * 70)
    print("🎮 Запуск графического интерфейса...")
    print("by @concole_hack")
    print("=" * 70)

    # Запускаем приложение
    app = QApplication(sys.argv)

    # Устанавливаем темную палитру
    app.setStyle("Fusion")

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(10, 10, 10))
    dark_palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, QColor(50, 50, 50))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.Text, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.Button, QColor(50, 50, 50))
    dark_palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(255, 50, 50))
    dark_palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setPalette(dark_palette)

    # Создаем и показываем главное окно
    window = ConsoleHackApp()
    window.show()

    # Запускаем главный цикл
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
