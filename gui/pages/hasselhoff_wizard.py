"""Hasselhoff Vibecode Wizard — install Git, IDEs & Claude Code with MAXIMUM HOFF."""

import json
import os
import platform
import random
import shutil
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QProgressBar, QScrollArea,
    QLineEdit, QMessageBox, QInputDialog,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt5.QtGui import QFont, QDesktopServices

from i18n import get_string, get_language

# ─── HASSELHOFF ASCII ART ────────────────────────────────────────────────
HOFF_ASCII = r"""
    ╔══════════════════════════════════════════════════╗
    ║    ██╗  ██╗ ██████╗ ███████╗███████╗██╗██╗██╗   ║
    ║    ██║  ██║██╔═══██╗██╔════╝██╔════╝██║██║██║   ║
    ║    ███████║██║   ██║█████╗  █████╗  ██║██║██║   ║
    ║    ██╔══██║██║   ██║██╔══╝  ██╔══╝  ╚═╝╚═╝╚═╝   ║
    ║    ██║  ██║╚██████╔╝██║     ██║     ██╗██╗██╗   ║
    ║    ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝     ╚═╝╚═╝╚═╝   ║
    ║         V I B E C O D E   W I Z A R D            ║
    ╚══════════════════════════════════════════════════╝
"""

# ─── PROGRESS PHRASES ────────────────────────────────────────────────────
SWIM_PHRASES = {
    "en": [
        "Hasselhoff is swimming to the server...",
        "Knight Rider downloading at 88 mph...",
        "Baywatch rescue in progress...",
        "The Hoff is flexing your internet connection...",
        "Running in slow motion across the beach of bytes...",
        "KITT is hacking the mainframe... just kidding, we're using apt...",
        "Hasselhoff once installed Linux with his bare hands...",
        "Don't Hassel the download! It's coming!",
        "The Berlin Wall of dependencies is falling...",
        "Singing 'Looking for Freedom' while compiling...",
        "Baywatch Mode: ENGAGED. Downloading like it's 1989!",
        "The Hoff doesn't wait for progress bars. Progress bars wait for the Hoff.",
    ],
    "ua": [
        "Хасселхофф пливе до сервера...",
        "Knight Rider завантажує на швидкості 88 миль/год...",
        "Байвотч-рятувальна операція в процесі...",
        "Хофф напружує твоє інтернет-з'єднання...",
        "Біжить в уповільненому русі по пляжу байтів...",
        "КІТТ хакає мейнфрейм... жартую, ми юзаємо apt...",
        "Хасселхофф одного разу встановив Linux голими руками...",
        "Don't Hassel the download! Вже летить!",
        "Берлінська стіна залежностей падає...",
        "Співає 'Looking for Freedom' під час компіляції...",
        "Режим Baywatch: АКТИВОВАНО. Завантажуємо ніби 1989-й!",
        "Хофф не чекає прогрес-барів. Прогрес-бари чекають Хоффа.",
    ],
}

ERROR_PHRASES = {
    "en": [
        "The Berlin Wall of errors! But Hasselhoff NEVER gives up!",
        "Even KITT crashed once. We'll fix this!",
        "Baywatch rescue FAILED?! That's never happened before!",
        "Hasselhoff is disappointed. But still loves you. Try again.",
        "The Hoff has seen worse. Remember that music video?",
        "*sad fart noise* — Something went wrong. The Hoff is investigating.",
    ],
    "ua": [
        "Берлінська стіна помилок! Але Хасселхофф НІКОЛИ не здається!",
        "Навіть КІТТ одного разу крашнувся. Ми це полагодимо!",
        "Байвотч-рятунок ПРОВАЛИВСЯ?! Таке ніколи не траплялось!",
        "Хасселхофф розчарований. Але все ще любить тебе. Спробуй ще.",
        "Хофф бачив гірше. Пам'ятаєш той кліп?",
        "*сумний пердіж* — Щось пішло не так. Хофф розслідує.",
    ],
}

SUCCESS_PHRASES = {
    "en": [
        "HASSELHOFF APPROVES! Installation complete!",
        "Don't Hassel the Hoff! You did it, champ!",
        "Baywatch mission COMPLETE! Another life saved!",
        "Knight Rider says: EXCELLENT installation!",
        "The Hoff gives you a standing ovation! *victory fart*",
        "Looking for Freedom! And you FOUND it — freedom to code!",
        "The Berlin Wall fell. So did your installation barriers. HOFF!",
    ],
    "ua": [
        "ХАССЕЛХОФФ СХВАЛЮЄ! Встановлення завершено!",
        "Don't Hassel the Hoff! Ти зробив це, красунчик!",
        "Місія Baywatch ВИКОНАНА! Ще одне життя врятовано!",
        "Knight Rider каже: ВІДМІННЕ встановлення!",
        "Хофф аплодує стоячи! *пердіж перемоги*",
        "Looking for Freedom! І ти ЗНАЙШОВ — свободу кодити!",
        "Берлінська стіна впала. Як і твої бар'єри встановлення. HOFF!",
    ],
}

ALL_INSTALLED_PHRASES = {
    "en": [
        "ALL TOOLS INSTALLED! You're a Hasselhoff-certified vibecoder!",
        "FULL BAYWATCH MODE! Every tool is ready. Time to code like the Hoff!",
        "Knight Rider's cockpit is fully operational! Start vibecoding!",
        "Hasselhoff has NOTHING left to install. You're PERFECT.",
        "The Hoff weeps tears of joy. Your setup is IMMACULATE.",
    ],
    "ua": [
        "ВСІ ІНСТРУМЕНТИ ВСТАНОВЛЕНІ! Ти Хасселхофф-сертифікований вайбкодер!",
        "ПОВНИЙ РЕЖИМ BAYWATCH! Все готово. Час кодити як Хофф!",
        "Кокпіт Knight Rider повністю операційний! Починай вайбкодити!",
        "Хасселхоффу НІЧОГО більше ставити. Ти ІДЕАЛЬНИЙ.",
        "Хофф плаче сльозами радості. Твій сетап БЕЗДОГАННИЙ.",
    ],
}

# ─── Status labels ────────────────────────────────────────────────────────
STATUS_INSTALLED = {
    "en": "INSTALLED — Hasselhoff approves!",
    "ua": "ВСТАНОВЛЕНО — Хасселхофф схвалює!",
}
STATUS_MISSING = {
    "en": "MISSING — Even the Hoff is disappointed",
    "ua": "ВІДСУТНІЙ — Навіть Хофф розчарований",
}
STATUS_INSTALLING = {
    "en": "INSTALLING — Baywatch rescue in progress...",
    "ua": "ВСТАНОВЛЕННЯ — Байвотч-рятунок в процесі...",
}
STATUS_DOWNLOADING = {
    "en": "DOWNLOADING — Knight Rider at full speed...",
    "ua": "ЗАВАНТАЖЕННЯ — Knight Rider на повній швидкості...",
}


def _get_os():
    s = platform.system().lower()
    if s == "linux":
        return "linux"
    elif s == "darwin":
        return "mac"
    elif s == "windows":
        return "windows"
    return "unknown"


def _detect_pkg_manager():
    """Detect Linux package manager."""
    for cmd, pm in [("apt", "apt"), ("dnf", "dnf"), ("pacman", "pacman")]:
        if shutil.which(cmd):
            return pm
    return None


def _check_installed(tool: dict) -> bool:
    """Check if a tool is installed by running its check_command."""
    cmd = tool.get("check_command")
    if not cmd:
        return False
    try:
        result = subprocess.run(
            cmd.split(), capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    # Fallback: check known paths
    for p in tool.get("check_paths", []):
        if os.path.exists(p):
            return True
    return False


def _check_dependency(tool: dict) -> bool:
    """Check if required dependency (e.g. node for claude_code) exists."""
    req = tool.get("requires_check")
    if not req:
        return True
    try:
        result = subprocess.run(req.split(), capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


class InstallThread(QThread):
    """Background thread for installing a tool."""
    progress = pyqtSignal(str)  # status message
    finished_ok = pyqtSignal(str)  # tool_key
    finished_err = pyqtSignal(str, str)  # tool_key, error

    def __init__(self, tool_key: str, tool_data: dict, parent=None):
        super().__init__(parent)
        self.tool_key = tool_key
        self.tool_data = tool_data

    def run(self):
        os_type = _get_os()
        try:
            if os_type == "linux":
                self._install_linux()
            else:
                self._download_for_os(os_type)
        except Exception as e:
            self.finished_err.emit(self.tool_key, str(e))

    def _install_linux(self):
        install = self.tool_data.get("install", {})

        # Try "all" first (e.g. npm install -g ...)
        if "all" in install:
            self.progress.emit("Running: " + install["all"])
            result = subprocess.run(
                install["all"].split(),
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                self.finished_ok.emit(self.tool_key)
            else:
                self.finished_err.emit(self.tool_key, result.stderr or "Install failed")
            return

        # Try snap first
        if "linux_snap" in install:
            snap_cmd = install["linux_snap"]
            self.progress.emit(f"Running: sudo {snap_cmd}")
            result = self._run_privileged(snap_cmd)
            if result == 0:
                self.finished_ok.emit(self.tool_key)
                return

        # Try linux command (e.g. "snap install cursor")
        if "linux" in install:
            cmd = install["linux"]
            self.progress.emit(f"Running: sudo {cmd}")
            result = self._run_privileged(cmd)
            if result == 0:
                self.finished_ok.emit(self.tool_key)
                return

        # Try package manager
        pm = _detect_pkg_manager()
        pkg_key = f"linux_{pm}" if pm else None
        if pkg_key and pkg_key in install:
            pkg = install[pkg_key]
            if pm == "apt":
                cmd = f"apt install -y {pkg}"
            elif pm == "dnf":
                cmd = f"dnf install -y {pkg}"
            elif pm == "pacman":
                cmd = f"pacman -S --noconfirm {pkg}"
            else:
                self.finished_err.emit(self.tool_key, f"Unknown package manager: {pm}")
                return

            self.progress.emit(f"Running: sudo {cmd}")
            result = self._run_privileged(cmd)
            if result == 0:
                self.finished_ok.emit(self.tool_key)
            else:
                self.finished_err.emit(self.tool_key, f"Package install failed (exit {result})")
            return

        # Fallback — open download page
        self._download_for_os("linux")

    def _run_privileged(self, cmd: str) -> int:
        """Run command with pkexec (graphical sudo) or fallback to xterm."""
        if shutil.which("pkexec"):
            full = ["pkexec"] + cmd.split()
        elif shutil.which("xterm"):
            full = ["xterm", "-e", f"sudo {cmd}; echo 'Press Enter...'; read"]
        else:
            full = ["sudo"] + cmd.split()

        try:
            result = subprocess.run(full, timeout=600)
            return result.returncode
        except subprocess.TimeoutExpired:
            return 1
        except Exception:
            return 1

    def _download_for_os(self, os_type: str):
        downloads = self.tool_data.get("download", {})
        url = downloads.get(os_type) or downloads.get("info")
        if url:
            self.progress.emit(f"Opening: {url}")
            QDesktopServices.openUrl(QUrl(url))
            self.finished_ok.emit(self.tool_key)
        else:
            self.finished_err.emit(self.tool_key, "No download URL available")


class ToolCard(QWidget):
    """Single tool card with status, install button, and Hoff phrase."""
    install_requested = pyqtSignal(str)  # tool_key

    def __init__(self, tool_key: str, tool_data: dict, parent=None):
        super().__init__(parent)
        self.tool_key = tool_key
        self.tool_data = tool_data

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row: icon + name + status
        header = QHBoxLayout()
        icon = tool_data.get("icon", "[?]")
        name = tool_data.get("name", tool_key)
        self.name_label = QLabel(f"{icon} {name}")
        self.name_label.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        header.addWidget(self.name_label)

        header.addStretch()

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("MS Sans Serif", 10))
        header.addWidget(self.status_label)
        layout.addLayout(header)

        # Description
        lang = get_language()
        desc = tool_data.get(f"description_{lang}", tool_data.get("description_en", ""))
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #404040; font-style: italic; padding-left: 4px;")
        layout.addWidget(desc_label)

        # Hoff phrase
        phrases_key = f"hoff_phrases_{lang}"
        phrases = tool_data.get(phrases_key, tool_data.get("hoff_phrases_en", []))
        if phrases:
            phrase = random.choice(phrases)
            hoff_label = QLabel(f'>>> "{phrase}"')
            hoff_label.setWordWrap(True)
            hoff_label.setStyleSheet(
                "color: #800080; font-weight: bold; padding: 4px 8px; "
                "background: #ffe0ff; border: 1px solid #c080c0; margin-top: 4px;"
            )
            layout.addWidget(hoff_label)

        # Button row
        btn_row = QHBoxLayout()

        self.install_btn = QPushButton("")
        self.install_btn.setStyleSheet(
            "font-size: 13px; padding: 6px 16px; font-weight: bold;"
        )
        self.install_btn.clicked.connect(lambda: self.install_requested.emit(self.tool_key))
        btn_row.addWidget(self.install_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Card style
        self.setStyleSheet(
            "ToolCard { background: white; border: 2px groove #808080; margin: 4px; }"
        )

        self.refresh_status()

    def refresh_status(self):
        lang = get_language()
        installed = _check_installed(self.tool_data)

        if installed:
            self.status_label.setText(STATUS_INSTALLED.get(lang, STATUS_INSTALLED["en"]))
            self.status_label.setStyleSheet("color: #008000; font-weight: bold;")
            self.install_btn.setText("[OK]Installed — Hoff approves!" if lang == "en"
                                    else "[OK]Встановлено — Хофф схвалює!")
            self.install_btn.setEnabled(False)
            self.install_btn.setStyleSheet(
                "font-size: 13px; padding: 6px 16px; font-weight: bold; "
                "background: #90EE90; color: #006400; border: 2px outset #60c060;"
            )
        else:
            self.status_label.setText(STATUS_MISSING.get(lang, STATUS_MISSING["en"]))
            self.status_label.setStyleSheet("color: #cc0000; font-weight: bold;")

            os_type = _get_os()
            if os_type == "linux":
                btn_text = ">>Install now!" if lang == "en" else ">>Встановити зараз!"
            else:
                btn_text = ">>Download" if lang == "en" else ">>Завантажити"

            self.install_btn.setText(btn_text)
            self.install_btn.setEnabled(True)
            self.install_btn.setStyleSheet(
                "font-size: 13px; padding: 6px 16px; font-weight: bold; "
                "background: #ff4444; color: white; border: 2px outset #ff8888;"
            )

    def set_installing(self):
        lang = get_language()
        self.status_label.setText(STATUS_INSTALLING.get(lang, STATUS_INSTALLING["en"]))
        self.status_label.setStyleSheet("color: #cc8800; font-weight: bold;")
        self.install_btn.setEnabled(False)
        self.install_btn.setText(
            ">>Hasselhoff is swimming..." if lang == "en"
            else ">>Хасселхофф пливе..."
        )
        self.install_btn.setStyleSheet(
            "font-size: 13px; padding: 6px 16px; font-weight: bold; "
            "background: #ffcc00; color: #333; border: 2px outset #ffdd66;"
        )


class HasselhoffWizardPage(QWidget):
    """The ultimate vibecoding setup wizard powered by David Hasselhoff."""
    hoff_event = pyqtSignal(str)  # message for statusbar / hasselhoff trigger

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tools_data = {}
        self._cards: dict[str, ToolCard] = {}
        self._install_thread = None

        layout = QVBoxLayout(self)

        # ─── HEADER: ASCII ART ────────────────────────────────────
        self.header = QLabel(HOFF_ASCII)
        self.header.setFont(QFont("Courier New", 8))
        self.header.setAlignment(Qt.AlignCenter)
        self.header.setStyleSheet(
            "background: #1a0033; color: #ff00ff; padding: 8px; "
            "border: 3px outset #800080; margin-bottom: 8px;"
        )
        self.header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Easter egg: double-click for special Hoff moment
        self.header.mouseDoubleClickEvent = self._easter_egg
        layout.addWidget(self.header)

        # ─── SUBTITLE ─────────────────────────────────────────────
        self.subtitle = QLabel("")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #800080; padding: 4px;"
        )
        layout.addWidget(self.subtitle)
        self._update_subtitle()

        # ─── INSTALL ALL BUTTON ───────────────────────────────────
        self.install_all_btn = QPushButton("")
        self.install_all_btn.setStyleSheet(
            "font-size: 16px; padding: 12px 32px; font-weight: bold; "
            "background: #ff0066; color: white; border: 3px outset #ff66aa; "
            "margin: 8px 40px;"
        )
        self.install_all_btn.clicked.connect(self._install_all_missing)
        layout.addWidget(self.install_all_btn)
        self._update_install_all_btn()

        # ─── PROGRESS BAR ─────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("")
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 2px inset #808080; background: #1a0033; "
            "text-align: center; height: 24px; color: #ff00ff; font-weight: bold; } "
            "QProgressBar::chunk { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:0, stop:0 #ff0066, stop:0.5 #ff00ff, stop:1 #6600ff); }"
        )
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Progress phrase label
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet(
            "color: #800080; font-weight: bold; font-style: italic; padding: 4px;"
        )
        self.progress_label.hide()
        layout.addWidget(self.progress_label)

        # ─── TOOL CARDS (scrollable) ──────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.cards_container)
        layout.addWidget(scroll)

        # ─── LOAD TOOLS ──────────────────────────────────────────
        self._load_tools_local()

        # ─── PHRASE ROTATION TIMER ────────────────────────────────
        self._phrase_timer = QTimer(self)
        self._phrase_timer.timeout.connect(self._rotate_phrase)

        # ─── INSTALL QUEUE ────────────────────────────────────────
        self._install_queue: list[str] = []

    def _update_subtitle(self):
        lang = get_language()
        if lang == "ua":
            self.subtitle.setText(
                ">>Хасселхофф допоможе тобі стати вайбкодером! "
                "Перевір що встановлено і постав що потрібно. \ud83c\udfca\u200d\u2642\ufe0f"
            )
        else:
            self.subtitle.setText(
                ">>Hasselhoff will help you become a vibecoder! "
                "Check what's installed and set up what's missing. \ud83c\udfca\u200d\u2642\ufe0f"
            )

    def _update_install_all_btn(self):
        lang = get_language()
        missing = [k for k, t in self._tools_data.items() if not _check_installed(t)]
        if missing:
            n = len(missing)
            if lang == "ua":
                self.install_all_btn.setText(
                    f"[!]РЕЖИМ BAYWATCH — Встановити все ({n} відсутніх) [!]"
                )
            else:
                self.install_all_btn.setText(
                    f"[!]BAYWATCH MODE — Install ALL Missing ({n}) [!]"
                )
            self.install_all_btn.setEnabled(True)
            self.install_all_btn.show()
        else:
            if lang == "ua":
                self.install_all_btn.setText(
                    "[*]ВСЕ ВСТАНОВЛЕНО — Хофф пишається тобою! [*]"
                )
            else:
                self.install_all_btn.setText(
                    "[*]ALL INSTALLED — The Hoff is proud of you! [*]"
                )
            self.install_all_btn.setEnabled(False)
            self.install_all_btn.setStyleSheet(
                "font-size: 16px; padding: 12px 32px; font-weight: bold; "
                "background: #00cc66; color: white; border: 3px outset #66ff99; "
                "margin: 8px 40px;"
            )

    def _load_tools_local(self):
        """Load tools.json from local repo."""
        tools_path = Path(__file__).resolve().parent.parent.parent / "tools.json"
        try:
            with open(tools_path) as f:
                data = json.load(f)
            self._tools_data = data.get("tools", {})
            self._build_cards()
        except (OSError, json.JSONDecodeError) as e:
            err = QLabel(f"Failed to load tools.json: {e}")
            err.setStyleSheet("color: #cc0000; padding: 16px; font-weight: bold;")
            self.cards_layout.addWidget(err)

    def _build_cards(self):
        """Create ToolCard for each tool."""
        # Clear existing
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cards.clear()

        for key, tool in self._tools_data.items():
            card = ToolCard(key, tool)
            card.install_requested.connect(self._on_install_requested)
            self.cards_layout.addWidget(card)
            self._cards[key] = card

        self._update_install_all_btn()

    def _on_install_requested(self, tool_key: str):
        """Handle install button click for a single tool."""
        tool = self._tools_data.get(tool_key)
        if not tool:
            return

        # Check dependency
        if not _check_dependency(tool):
            lang = get_language()
            hint_key = f"requires_install_hint_{lang}"
            hint = tool.get(hint_key, tool.get("requires_install_hint_en", ""))
            QMessageBox.warning(
                self, "Hasselhoff says: WAIT!",
                f"This tool requires {tool.get('requires', '???')}!\n\n{hint}\n\n"
                "Install the dependency first, then come back!\n"
                "Even Hasselhoff follows prerequisites!",
            )
            return

        # Git post-install: ask for config
        if tool_key == "git" and _check_installed(tool):
            self._git_config_wizard()
            return

        self._start_install(tool_key)

    def _start_install(self, tool_key: str):
        """Start installation in background thread."""
        if self._install_thread and self._install_thread.isRunning():
            self._install_queue.append(tool_key)
            return

        tool = self._tools_data[tool_key]
        card = self._cards.get(tool_key)
        if card:
            card.set_installing()

        # Show progress
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.show()
        self._rotate_phrase()
        self._phrase_timer.start(3000)

        # Animate progress bar
        self._progress_value = 0
        self._progress_anim = QTimer(self)
        self._progress_anim.timeout.connect(self._animate_progress)
        self._progress_anim.start(200)

        # Start thread
        self._install_thread = InstallThread(tool_key, tool, self)
        self._install_thread.progress.connect(self._on_install_progress)
        self._install_thread.finished_ok.connect(self._on_install_ok)
        self._install_thread.finished_err.connect(self._on_install_error)
        self._install_thread.start()

    def _animate_progress(self):
        """Fake progress animation — because Hasselhoff never stands still."""
        if self._progress_value < 90:
            self._progress_value += random.randint(1, 5)
            self.progress_bar.setValue(self._progress_value)

    def _rotate_phrase(self):
        """Rotate swimming/progress phrases."""
        lang = get_language()
        phrases = SWIM_PHRASES.get(lang, SWIM_PHRASES["en"])
        self.progress_label.setText(random.choice(phrases))

    def _on_install_progress(self, msg: str):
        self.progress_label.setText(msg)

    def _on_install_ok(self, tool_key: str):
        """Installation succeeded!"""
        self._finish_progress()
        lang = get_language()

        # Refresh card
        card = self._cards.get(tool_key)
        if card:
            card.refresh_status()

        # Victory message
        phrase = random.choice(SUCCESS_PHRASES.get(lang, SUCCESS_PHRASES["en"]))
        tool_name = self._tools_data.get(tool_key, {}).get("name", tool_key)
        self.progress_label.setText(f"[OK]{tool_name}: {phrase}")
        self.progress_label.show()

        # Trigger Hasselhoff in main app
        self.hoff_event.emit(f"{tool_name} installed! {phrase}")

        self._update_install_all_btn()

        # Git post-install config
        if tool_key == "git":
            QTimer.singleShot(1000, self._git_config_wizard)

        # Check all installed
        self._check_all_installed()

        # Process queue
        QTimer.singleShot(2000, self._process_queue)

    def _on_install_error(self, tool_key: str, error: str):
        """Installation failed!"""
        self._finish_progress()
        lang = get_language()

        # Refresh card
        card = self._cards.get(tool_key)
        if card:
            card.refresh_status()

        # Error message
        phrase = random.choice(ERROR_PHRASES.get(lang, ERROR_PHRASES["en"]))
        tool_name = self._tools_data.get(tool_key, {}).get("name", tool_key)
        self.progress_label.setText(f"[ERR]{tool_name}: {phrase}")
        self.progress_label.setStyleSheet(
            "color: #cc0000; font-weight: bold; font-style: italic; padding: 4px;"
        )
        self.progress_label.show()

        # Show error detail
        QMessageBox.warning(
            self,
            f"Hasselhoff is sad about {tool_name}",
            f"{phrase}\n\nError: {error}\n\n"
            "Don't worry — even KITT had bad days.\n"
            "Try installing manually or check your internet connection.",
        )

        # Reset label style after delay
        QTimer.singleShot(5000, lambda: self.progress_label.setStyleSheet(
            "color: #800080; font-weight: bold; font-style: italic; padding: 4px;"
        ))

        # Process queue
        QTimer.singleShot(2000, self._process_queue)

    def _finish_progress(self):
        """Stop progress animation."""
        self.progress_bar.setValue(100)
        self._phrase_timer.stop()
        if hasattr(self, "_progress_anim"):
            self._progress_anim.stop()

    def _process_queue(self):
        """Install next tool in queue."""
        if self._install_queue:
            next_key = self._install_queue.pop(0)
            self._start_install(next_key)
        else:
            QTimer.singleShot(3000, self._hide_progress)

    def _hide_progress(self):
        if not (self._install_thread and self._install_thread.isRunning()):
            self.progress_bar.hide()
            self.progress_label.hide()

    def _install_all_missing(self):
        """BAYWATCH MODE: install everything that's missing."""
        missing = [k for k, t in self._tools_data.items() if not _check_installed(t)]
        if not missing:
            return

        lang = get_language()
        if lang == "ua":
            reply = QMessageBox.question(
                self, "РЕЖИМ BAYWATCH!",
                f"Хасселхофф готовий встановити {len(missing)} інструментів!\n\n"
                + "\n".join(f"  \u2022 {self._tools_data[k].get('name', k)}" for k in missing)
                + "\n\nЗапускаємо Baywatch Mode?",
                QMessageBox.Yes | QMessageBox.No,
            )
        else:
            reply = QMessageBox.question(
                self, "BAYWATCH MODE!",
                f"Hasselhoff is ready to install {len(missing)} tools!\n\n"
                + "\n".join(f"  \u2022 {self._tools_data[k].get('name', k)}" for k in missing)
                + "\n\nEngage Baywatch Mode?",
                QMessageBox.Yes | QMessageBox.No,
            )

        if reply == QMessageBox.Yes:
            # Queue all missing, respecting dependencies
            # Tools with dependencies go last
            no_deps = [k for k in missing if not self._tools_data[k].get("requires")]
            with_deps = [k for k in missing if self._tools_data[k].get("requires")]
            ordered = no_deps + with_deps

            if ordered:
                self._start_install(ordered[0])
                self._install_queue.extend(ordered[1:])

    def _check_all_installed(self):
        """Check if everything is installed — trigger MEGA HOFF."""
        missing = [k for k, t in self._tools_data.items() if not _check_installed(t)]
        if not missing and self._tools_data:
            lang = get_language()
            phrase = random.choice(ALL_INSTALLED_PHRASES.get(lang, ALL_INSTALLED_PHRASES["en"]))
            self.hoff_event.emit(phrase)

    def _git_config_wizard(self):
        """Post-install: configure git user.name and user.email."""
        lang = get_language()

        # Check if already configured
        try:
            name_result = subprocess.run(
                ["git", "config", "--global", "user.name"],
                capture_output=True, text=True, timeout=5,
            )
            email_result = subprocess.run(
                ["git", "config", "--global", "user.email"],
                capture_output=True, text=True, timeout=5,
            )
            if name_result.stdout.strip() and email_result.stdout.strip():
                return  # Already configured
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return

        title = ("Hasselhoff Git Config Wizard" if lang == "en"
                 else "Хасселхофф Git Config Визард")
        prompt_name = ("What's your name, vibecoder?\n\n"
                       "(Hasselhoff needs to know who to give credit to)"
                       if lang == "en" else
                       "Як тебе звати, вайбкодеру?\n\n"
                       "(Хасселхофф мусить знати кого хвалити)")

        name, ok = QInputDialog.getText(self, title, prompt_name)
        if not ok or not name:
            return

        prompt_email = ("And your email?\n\n"
                        "(For git commits, not Baywatch fan mail)"
                        if lang == "en" else
                        "І твій email?\n\n"
                        "(Для git комітів, не для фанатської пошти Baywatch)")

        email, ok = QInputDialog.getText(self, title, prompt_email)
        if not ok or not email:
            return

        try:
            subprocess.run(["git", "config", "--global", "user.name", name], timeout=5)
            subprocess.run(["git", "config", "--global", "user.email", email], timeout=5)

            msg = (f"Git configured!\n\n"
                   f"Name: {name}\nEmail: {email}\n\n"
                   f"Hasselhoff approves your identity!"
                   if lang == "en" else
                   f"Git налаштований!\n\n"
                   f"Ім'я: {name}\nEmail: {email}\n\n"
                   f"Хасселхофф схвалює твою ідентичність!")

            QMessageBox.information(self, title, msg)
            self.hoff_event.emit(f"Git configured for {name}! Knight Rider is ready!")
        except Exception as e:
            QMessageBox.warning(self, "Oops", f"Git config failed: {e}")

    def _easter_egg(self, event):
        """Double-click on header — MAXIMUM HOFF."""
        lang = get_language()

        hoff_wisdom = [
            "The Hoff once debugged a production server by staring at it.",
            "Hasselhoff doesn't use Stack Overflow. Stack Overflow uses Hasselhoff.",
            "KITT's AI was just Claude Code in a Pontiac Trans Am.",
            "The Berlin Wall fell because Hasselhoff's code had no walls.",
            "Hasselhoff's git log is just a list of victories.",
            "When Hasselhoff writes tests, they pass in ALL timelines.",
            "Hasselhoff doesn't refactor. He factors correctly the first time.",
            "npm install hasselhoff — installs confidence and beach muscles.",
        ]
        hoff_wisdom_ua = [
            "Хофф одного разу здебажив прод-сервер просто поглядом.",
            "Хасселхофф не юзає Stack Overflow. Stack Overflow юзає Хасселхоффа.",
            "ШІ КІТТа — це просто Claude Code в Понтіак Транс Ам.",
            "Берлінська стіна впала бо в коді Хасселхоффа немає стін.",
            "Git log Хасселхоффа — це просто список перемог.",
            "Коли Хасселхофф пише тести, вони проходять в УСІХ часових лініях.",
            "Хасселхофф не рефакторить. Він пише правильно з першого разу.",
            "npm install hasselhoff — встановлює впевненість і пляжні м'язи.",
        ]

        wisdom = hoff_wisdom_ua if lang == "ua" else hoff_wisdom
        phrase = random.choice(wisdom)

        QMessageBox.information(
            self,
            "*** HOFF WISDOM ***" if lang == "en" else "*** МУДРІСТЬ ХОФФА ***",
            f"\n{phrase}\n\n— David Hasselhoff, probably",
        )
        self.hoff_event.emit(phrase)

    def refresh_all(self):
        """Re-check all tool statuses."""
        for card in self._cards.values():
            card.refresh_status()
        self._update_install_all_btn()
        self._update_subtitle()
