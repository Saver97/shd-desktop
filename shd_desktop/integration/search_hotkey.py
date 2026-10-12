"""Windows global search shortcut, with transactional conflict handling."""

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, Qt, QTimer
from PySide6.QtGui import QKeySequence

DEFAULT_SHORTCUT = "Ctrl+Alt+Space"


def shortcut_parts(text: str):
    sequence = QKeySequence.fromString(text, QKeySequence.PortableText)
    if sequence.count() != 1:
        raise ValueError("请设置一组快捷键，例如 Ctrl+Alt+Space")
    combo = sequence[0]
    modifiers = combo.keyboardModifiers()
    native = 0
    for qt, bit in ((Qt.ControlModifier, 2), (Qt.AltModifier, 1),
                    (Qt.ShiftModifier, 4), (Qt.MetaModifier, 8)):
        if modifiers & qt:
            native |= bit
    if not native & (1 | 2 | 8):
        raise ValueError("快捷键需要包含 Ctrl、Alt 或 Win")
    key = int(combo.key())
    special = {int(Qt.Key_Space): 0x20, int(Qt.Key_Return): 0x0D,
               int(Qt.Key_Tab): 9, int(Qt.Key_Home): 0x24, int(Qt.Key_End): 0x23}
    if int(Qt.Key_F1) <= key <= int(Qt.Key_F24):
        vk = 0x70 + key - int(Qt.Key_F1)
    elif 0x30 <= key <= 0x5A:
        vk = key
    else:
        vk = special.get(key)
    if vk is None or vk == 0x7B:
        raise ValueError("请选择字母、数字、空格或功能键（F12 除外）")
    return sequence.toString(QKeySequence.PortableText), native | 0x4000, vk


class SearchHotkey(QAbstractNativeEventFilter):
    def __init__(self, app, callback):
        super().__init__()
        self.app, self.callback = app, callback
        self.active = None
        self.identifier = 0x5344
        self.native = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
        if self.native:
            self.native.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
            self.native.RegisterHotKey.restype = wintypes.BOOL
            self.native.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        app.installNativeEventFilter(self)
        app.aboutToQuit.connect(self.close)

    def configure(self, enabled: bool, text: str):
        canonical, modifiers, key = shortcut_parts(text)
        if not enabled:
            self.unregister()
            return canonical
        if self.active == canonical:
            return canonical
        if not self.native:
            raise ValueError("全局快捷键仅支持 Windows；仍可从托盘打开查找")
        new_id = 0x5345 if self.identifier == 0x5344 else 0x5344
        if not self.native.RegisterHotKey(None, new_id, modifiers, key):
            raise ValueError("快捷键已被其他程序占用或系统不允许，请换一组；原快捷键仍保留")
        self.unregister()
        self.identifier, self.active = new_id, canonical
        return canonical

    def unregister(self):
        if self.active and self.native:
            self.native.UnregisterHotKey(None, self.identifier)
        self.active = None

    def nativeEventFilter(self, event_type, message):
        if self.active and bytes(event_type) in (b"windows_dispatcher_MSG", b"windows_generic_MSG"):
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == 0x0312 and msg.wParam == self.identifier:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0

    def close(self):
        self.unregister()
        self.app.removeNativeEventFilter(self)
