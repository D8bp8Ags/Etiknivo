"""Look and feel: colour tokens, light/dark palettes, the style sheet and icons.

Everything visual that is not specific to one widget lives here, so the
panels only refer to semantic names (``theme.tokens().muted``) and pick up a
theme switch automatically.  The style is Fusion plus a style sheet: that
renders the same on every platform and lets the app follow the system's light
or dark appearance.

Icons are Lucide line icons (ISC licence, see ``icons/LICENSE-lucide.txt``),
recoloured at runtime to match the current text colour.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from functools import cache, lru_cache
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

THEMES = {"system": "Systeem", "light": "Licht", "dark": "Donker"}


@dataclass(frozen=True)
class Tokens:
    dark: bool
    window: str  # main background
    sidebar: str  # library and inspector background
    surface: str  # inputs, cards, tables
    canvas: str  # behind the label in the editor
    hover: str
    pressed: str
    border: str
    border_strong: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    on_accent: str
    selection: str  # selected list rows
    track: str  # progress bar background, scrollbar handles
    success: str
    warning: str
    danger: str


LIGHT = Tokens(
    dark=False, window="#f6f6f8", sidebar="#efeff3", surface="#ffffff", canvas="#e7e7ec",
    hover="#e4e4ea", pressed="#d8d8e0", border="#dcdce2", border_strong="#c4c4cc",
    text="#1d1d1f", muted="#6e6e76", accent="#3b6ef5", accent_hover="#2c5de0",
    on_accent="#ffffff", selection="#dde6fd", track="#d9d9df", success="#1e9e57",
    warning="#c47600", danger="#d93025",
)
DARK = Tokens(
    dark=True, window="#1f1f22", sidebar="#242428", surface="#2c2c30", canvas="#18181b",
    hover="#34343a", pressed="#3e3e45", border="#38383e", border_strong="#4b4b52",
    text="#f1f1f3", muted="#9c9ca5", accent="#5b8cff", accent_hover="#7aa2ff",
    on_accent="#ffffff", selection="#2c3b60", track="#45454c", success="#3cc774",
    warning="#f2a33a", danger="#ff6259",
)


class _ThemeManager(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.mode = "system"
        self.tokens = LIGHT
        self._listening = False


_manager: _ThemeManager | None = None


def manager() -> _ThemeManager:
    global _manager
    if _manager is None:
        _manager = _ThemeManager()
    return _manager


def tokens() -> Tokens:
    return manager().tokens


def _system_is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def apply(mode: str = "system") -> None:
    """Apply *mode* (system, light or dark) to the running application."""
    app = QApplication.instance()
    if app is None:
        return
    m = manager()
    m.mode = mode if mode in THEMES else "system"
    hints = QGuiApplication.styleHints()
    if not m._listening:
        hints.colorSchemeChanged.connect(lambda _s: m.mode == "system" and _refresh(app))
        m._listening = True
    if m.mode == "system":
        hints.unsetColorScheme()
    else:
        hints.setColorScheme(Qt.ColorScheme.Dark if m.mode == "dark" else Qt.ColorScheme.Light)
    _refresh(app)


def _refresh(app: QApplication) -> None:
    m = manager()
    dark = _system_is_dark() if m.mode == "system" else m.mode == "dark"
    t = DARK if dark else LIGHT
    m.tokens = t
    app.setStyle("Fusion")
    app.setPalette(_palette(t))
    app.setStyleSheet(stylesheet(t))
    m.changed.emit()


def _palette(t: Tokens) -> QPalette:
    p = QPalette()
    c = QColor
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        p.setColor(group, QPalette.ColorRole.Window, c(t.window))
        p.setColor(group, QPalette.ColorRole.WindowText, c(t.text))
        p.setColor(group, QPalette.ColorRole.Base, c(t.surface))
        p.setColor(group, QPalette.ColorRole.AlternateBase, c(t.sidebar))
        p.setColor(group, QPalette.ColorRole.Text, c(t.text))
        p.setColor(group, QPalette.ColorRole.Button, c(t.surface))
        p.setColor(group, QPalette.ColorRole.ButtonText, c(t.text))
        p.setColor(group, QPalette.ColorRole.Highlight, c(t.accent))
        p.setColor(group, QPalette.ColorRole.HighlightedText, c(t.on_accent))
        p.setColor(group, QPalette.ColorRole.ToolTipBase, c(t.text))
        p.setColor(group, QPalette.ColorRole.ToolTipText, c(t.window))
        p.setColor(group, QPalette.ColorRole.PlaceholderText, c(t.muted))
        p.setColor(group, QPalette.ColorRole.Link, c(t.accent))
        p.setColor(group, QPalette.ColorRole.Mid, c(t.border_strong))
        p.setColor(group, QPalette.ColorRole.Midlight, c(t.border))
        p.setColor(group, QPalette.ColorRole.Light, c(t.surface))
        p.setColor(group, QPalette.ColorRole.Dark, c(t.border_strong))
        p.setColor(group, QPalette.ColorRole.Shadow, c("#000000"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c(t.muted))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, c(t.window))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, c(t.window))
    return p


# -- icons --------------------------------------------------------------------------------


@cache
def _svg(name: str) -> str:
    return resources.files("etiknivo.gui.icons").joinpath(f"{name}.svg").read_text("utf-8")


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    data = _svg(name).replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(data.encode()))
    px = round(size * ratio)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """A Lucide icon in *color* (default: the text colour), with a muted disabled state."""
    t = tokens()
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if app is not None else 1.0
    ic = QIcon()
    ic.addPixmap(_pixmap(name, color or t.text, size, ratio), QIcon.Mode.Normal)
    ic.addPixmap(_pixmap(name, t.border_strong, size, ratio), QIcon.Mode.Disabled)
    if color is None:
        ic.addPixmap(_pixmap(name, t.on_accent, size, ratio), QIcon.Mode.Selected)
    return ic


def icon_file(name: str, color: str, size: int = 12) -> str:
    """Write a tinted icon to a temporary PNG (style sheets need a file path)."""
    folder = Path(tempfile.gettempdir()) / "etiknivo-icons"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}-{size}.png"
    if not path.exists():
        _pixmap(name, color, size, 2.0).save(str(path))
    return path.as_posix()


def dot(color: str, size: int = 10) -> QIcon:
    """A filled status dot."""
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if app is not None else 1.0
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(1, 1, pm.width() - 2, pm.height() - 2))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return QIcon(pm)


ICON_SIZE = QSize(18, 18)


# -- style sheet --------------------------------------------------------------------------


def stylesheet(t: Tokens) -> str:
    down = icon_file("chevron-down", t.muted)
    up = icon_file("chevron-up", t.muted)
    check = icon_file("check", t.on_accent, 14)
    return f"""
* {{ font-size: 13px; }}
QMainWindow, QDialog {{ background: {t.window}; }}
QWidget#sidebar, QWidget#inspector, QScrollArea#inspectorScroll > QWidget > QWidget {{
    background: {t.sidebar};
}}
QWidget#canvas {{ background: {t.canvas}; }}
QWidget#inspectorFooter {{ background: {t.sidebar}; border-top: 1px solid {t.border}; }}
QLabel#dirty {{ color: {t.warning}; font-size: 11px; font-weight: 600; }}
QLabel {{ background: transparent; }}
QLabel#heading {{ font-size: 15px; font-weight: 600; }}
QLabel#title {{ font-size: 14px; font-weight: 600; }}
QLabel#subtitle, QLabel#hint, QLabel#muted {{ color: {t.muted}; }}
QLabel#hint {{ font-size: 11px; }}
QLabel#caption {{ color: {t.muted}; font-size: 11px; font-weight: 600; }}
QLabel#pill {{ border-radius: 11px; padding: 3px 10px; font-weight: 500; }}
QLabel#pill[state="ok"] {{ color: {t.success}; background: {_alpha(t.success, 0.13)}; }}
QLabel#pill[state="warn"] {{ color: {t.danger}; background: {_alpha(t.danger, 0.13)}; }}

QToolBar {{
    background: {t.window}; border: none; border-bottom: 1px solid {t.border};
    padding: 6px 10px; spacing: 4px;
}}
QToolBar::separator {{ background: {t.border}; width: 1px; margin: 6px 6px; }}
QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 7px;
    padding: 4px 7px; color: {t.text};
}}
QToolButton:hover {{ background: {t.hover}; }}
QToolButton:pressed, QToolButton:checked {{ background: {t.pressed}; }}
QToolButton:disabled {{ color: {t.muted}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#chip {{ border: 1px solid {t.border}; border-radius: 13px; padding: 3px 10px; }}
QToolButton#chip:hover {{ background: {t.hover}; }}

QPushButton {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 7px;
    padding: 5px 14px; color: {t.text}; min-height: 18px;
}}
QPushButton:hover {{ border-color: {t.border_strong}; background: {t.hover}; }}
QPushButton:pressed {{ background: {t.pressed}; }}
QPushButton:disabled {{ color: {t.muted}; background: {t.window}; border-color: {t.border}; }}
QPushButton[primary="true"] {{
    background: {t.accent}; border-color: {t.accent}; color: {t.on_accent}; font-weight: 600;
}}
QPushButton[primary="true"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[primary="true"]:disabled {{
    background: {t.track}; border-color: {t.track}; color: {t.surface};
}}

QLineEdit, QComboBox, QAbstractSpinBox, QPlainTextEdit {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 7px;
    padding: 4px 8px; color: {t.text}; min-height: 18px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:hover, QComboBox:hover, QAbstractSpinBox:hover, QPlainTextEdit:hover {{
    border-color: {t.border_strong};
}}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {t.accent};
}}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled, QPlainTextEdit:disabled {{
    background: {t.window}; color: {t.muted};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent}; outline: none;
}}
QAbstractSpinBox {{ padding-left: 8px; padding-right: 20px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border; width: 18px; border: none; background: transparent;
}}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin-top: 2px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin-bottom: 2px; }}
QAbstractSpinBox::up-arrow {{ image: url("{up}"); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url("{down}"); width: 10px; height: 10px; }}

QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator, QGroupBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {t.border_strong}; border-radius: 4px;
    background: {t.surface};
}}
QCheckBox::indicator:hover, QGroupBox::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked, QGroupBox::indicator:checked {{
    background: {t.accent}; border-color: {t.accent}; image: url("{check}");
}}
QCheckBox::indicator:disabled, QGroupBox::indicator:disabled {{
    background: {t.window}; border-color: {t.border};
}}
QGroupBox {{
    border: none; border-top: 1px solid {t.border}; margin-top: 22px; padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; left: 0; top: 6px;
    padding: 0 4px 0 0; color: {t.text};
}}

QTabWidget::pane {{ border: none; border-top: 1px solid {t.border}; top: -1px; }}
QTabWidget::tab-bar {{ alignment: center; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: {t.hover}; color: {t.muted}; padding: 5px 18px; margin: 8px 0 8px 0;
    border: 1px solid {t.hover}; font-weight: 500;
}}
QTabBar::tab:first {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
QTabBar::tab:last {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QTabBar::tab:selected {{ background: {t.surface}; color: {t.text}; border-color: {t.border}; }}

QTreeView, QListView, QTableView {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px;
    outline: none; alternate-background-color: {t.sidebar};
}}
QTreeView#libraryList {{ background: transparent; border: none; }}
QListView::item {{ padding: 5px 6px; border-radius: 6px; }}
QListView::item:selected, QTableView::item:selected {{
    background: {t.selection}; color: {t.text};
}}
QTableView {{ gridline-color: transparent; }}
QTableView::item {{ padding: 2px 6px; }}
QHeaderView::section {{
    background: {t.surface}; color: {t.muted}; border: none; border-bottom: 1px solid {t.border};
    padding: 5px 8px; font-weight: 600; font-size: 11px;
}}

QProgressBar {{
    background: {t.track}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}
QProgressBar[level="low"]::chunk {{ background: {t.danger}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t.track}; border-radius: 3px; }}
QScrollBar::handle:hover {{ background: {t.border_strong}; }}
QScrollBar::handle:vertical {{ min-height: 30px; margin: 0 2px; }}
QScrollBar::handle:horizontal {{ min-width: 30px; margin: 2px 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QSplitter::handle {{ background: {t.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QMainWindow::separator {{ background: {t.border}; width: 1px; height: 1px; }}
QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{
    background: {t.window}; padding: 7px 12px; border-top: 1px solid {t.border};
    font-weight: 600;
}}
QStatusBar {{ background: {t.window}; color: {t.muted}; border-top: 1px solid {t.border}; }}
QStatusBar QLabel {{ color: {t.muted}; padding: 0 8px; }}
QStatusBar::item {{ border: none; }}

QSlider::groove:horizontal {{ background: {t.track}; height: 4px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {t.surface}; border: 1px solid {t.border_strong}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 8px;
}}

QMenuBar {{ background: {t.window}; }}
QMenuBar::item:selected {{ background: {t.hover}; border-radius: 5px; }}
QMenu {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 5px;
}}
QMenu::item {{ padding: 5px 22px 5px 10px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t.accent}; color: {t.on_accent}; }}
QMenu::item:disabled {{ color: {t.muted}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QToolTip {{
    background: {t.text}; color: {t.window}; border: none; padding: 4px 8px;
}}
"""


def _alpha(hex_color: str, a: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a:.2f})"
