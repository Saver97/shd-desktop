"""Native registration, dispatcher delivery, conflict rollback and release."""

import ctypes
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from shd_desktop.integration.search_hotkey import SearchHotkey, shortcut_parts


app = QApplication([])
calls = []
hotkey = SearchHotkey(app, lambda: calls.append(True))
native = hotkey.native
blocked = 0x5310
try:
    assert hotkey.configure(True, "Ctrl+Alt+Shift+F11") == "Ctrl+Alt+Shift+F11"
    thread = ctypes.windll.kernel32.GetCurrentThreadId()
    assert native.PostThreadMessageW(thread, 0x0312, hotkey.identifier, 0)
    QTest.qWait(80)
    assert len(calls) == 1, calls
    _, modifiers, key = shortcut_parts("Ctrl+Alt+Shift+F10")
    assert native.RegisterHotKey(None, blocked, modifiers, key)
    try:
        hotkey.configure(True, "Ctrl+Alt+Shift+F10")
    except ValueError:
        pass
    else:
        raise AssertionError("Conflicting shortcut must fail")
    assert hotkey.active == "Ctrl+Alt+Shift+F11"
    assert native.PostThreadMessageW(thread, 0x0312, hotkey.identifier, 0)
    QTest.qWait(80)
    assert len(calls) == 2
    hotkey.configure(True, "Ctrl+Alt+Shift+F9")
    old_id = hotkey.identifier
    hotkey.configure(False, "Ctrl+Alt+Shift+F9")
    native.PostThreadMessageW(thread, 0x0312, old_id, 0)
    QTest.qWait(50)
    assert len(calls) == 2
    _, modifiers, key = shortcut_parts("Ctrl+Alt+Shift+F9")
    assert native.RegisterHotKey(None, blocked + 1, modifiers, key)
finally:
    hotkey.close()
    native.UnregisterHotKey(None, blocked)
    native.UnregisterHotKey(None, blocked + 1)
print("Native global hotkey, callback, conflict preservation, switching and unregister passed")
