"""Exercise the real Windows Shell menu against disposable files."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import win32gui

from shd_desktop.integration.shell_context_menu import RESTORE_COMMAND, show_file_menu


if os.name == "nt":
    with TemporaryDirectory() as temp:
        root = Path(temp)
        first = root / "一号.txt"
        second = root / "二号.txt"
        first.write_text("one", encoding="utf-8")
        second.write_text("two", encoding="utf-8")
        with patch.object(win32gui, "TrackPopupMenu", return_value=0) as popup:
            assert show_file_menu([first, second], 0, 100, 100) is None
            assert popup.called
        with patch.object(win32gui, "TrackPopupMenu", return_value=RESTORE_COMMAND):
            assert show_file_menu([first], 0, 100, 100, allow_restore=True)
        other = root / "sub"
        other.mkdir()
        third = other / "三号.txt"
        third.write_text("three", encoding="utf-8")
        try:
            show_file_menu([first, third], 0, 100, 100)
        except ValueError:
            pass
        else:
            raise AssertionError("Mixed-parent selections must not reach Shell")
print("shell menu: native commands loaded for one and two files")
