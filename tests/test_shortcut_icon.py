"""Check Windows Internet Shortcut icons resolve from IconFile."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileIconProvider

from app import icon_for_item


app = QApplication([])
icon_file = Path(__file__).resolve().parents[1] / "assets" / "app.ico"
with TemporaryDirectory() as temp:
    shortcut = Path(temp) / "Steam game.url"
    shortcut.write_text("[InternetShortcut]\nURL=steam://rungameid/1\n"
                        f"IconFile={icon_file}\nIconIndex=0\n", encoding="utf-8")
    icon = icon_for_item(shortcut, QFileIconProvider())
    assert not icon.isNull()
    assert icon.pixmap(40, 40).toImage() == QIcon(str(icon_file)).pixmap(40, 40).toImage()
print("Internet Shortcut icon passed")
