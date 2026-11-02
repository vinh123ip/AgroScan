"""Application-wide font and stylesheet loading."""

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

_UI_DIR = Path(__file__).parent


def apply_theme(app: QApplication) -> None:
    """Nạp font Inter và QSS dark theme cho toàn ứng dụng (cả Login và MainWindow)."""
    fonts_dir = _UI_DIR / "resources" / "fonts"
    if fonts_dir.exists():
        for font_file in fonts_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font_file))
    app.setFont(QFont("Inter", 10))

    style_path = _UI_DIR / "styles" / "light_theme.qss"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))
