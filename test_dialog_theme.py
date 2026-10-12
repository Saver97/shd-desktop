"""The native Windows message box body must have legible dark styling."""

from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from theme import STYLE


app = QApplication([])
app.setStyleSheet(STYLE)
message = QMessageBox(
    QMessageBox.Warning,
    "无法一键整理",
    "Windows 桌面开启了“自动排列图标”。\n\n"
    "请在桌面空白处右键 → 查看 → 取消勾选“自动排列图标”，然后重试。",
)
message.show()
app.processEvents()
pixmap = message.grab()
assert pixmap.toImage().pixelColor(3, 45).lightness() < 100
pixmap.save(str(Path(__file__).resolve().parent / "preview-warning-native.png"))
message.close()
print("native message box contrast passed")
