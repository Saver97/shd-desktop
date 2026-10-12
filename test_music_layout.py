"""Music browsing has the space; search, paging, login and resume remain usable."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import ConfigStore, Controller
from theme import apply_hud, HUD_DEFAULTS


app = QApplication([])
songs = [{"kind": "song", "mid": f"test-{i}", "title": f"歌曲 {i + 1:02d}",
          "artist": "示例歌手", "song_type": 0} for i in range(40)]
with TemporaryDirectory() as temp:
    root = Path(temp)
    (root / "music-state.json").write_text(json.dumps({
        "current_song": songs[0], "queue": songs, "results": songs,
        "position_ms": 42000, "volume": 45,
        "current_playlist": {"id": 123, "page": 1, "total": 120},
    }), encoding="utf-8")
    controller = Controller(app, ConfigStore(root), enable_hotkeys=False)
    center = controller.center
    pane = center.music
    calls = []
    pane.bridge.submit = lambda kind, value: calls.append((kind, value))
    center.centralWidget().setCurrentWidget(center.music)
    center.show()
    QTest.qWait(40)
    view = pane.results
    metrics = {"window_height": center.height(), "list_viewport_height": view.viewport().height(),
               "row_height": view.visualItemRect(view.item(0)).height(),
               "fully_visible_rows": sum(view.viewport().rect().contains(view.visualItemRect(view.item(i)))
                                          for i in range(view.count()))}
    assert metrics["list_viewport_height"] >= center.height() * .60, metrics
    assert metrics["fully_visible_rows"] >= 12, metrics
    assert not pane.login_dialog.isVisible() and not pane.qr_label.isVisible()
    center.grab().save(str(Path(__file__).parent / "preview-0.5.12-music.png"))

    pane.search.setText("示例搜索")
    pane.search_button.click()
    pane.search_type.setCurrentIndex(1)
    pane.search.returnPressed.emit()
    pane.mine_button.click()
    assert calls == [("songs", "示例搜索"), ("playlists", "示例搜索"), ("my_playlists", "")]
    pane.next_page.click()
    assert calls[-1] == ("playlist_songs", {"id": 123, "page": 2})
    pane.on_completed("playlist_songs", {"id": 123, "page": 2, "total": 120, "items": songs})
    assert pane.prev_page.isEnabled() and pane.next_page.isEnabled()
    pane.toggle_play()
    assert calls[-1] == ("url", songs[0]) and pane._resume_ms == 42000
    pane.open_item(view.item(3))
    assert calls[-1] == ("url", songs[3]) and pane._resume_ms == 0

    height = view.viewport().height()
    pane.login()
    pane.login()
    assert calls.count(("login", "")) == 1
    pane.show_qr((Path(__file__).parent / "assets/icons/cat-media-gen-64.png").read_bytes())
    QTest.qWait(20)
    assert pane.login_dialog.isVisible() and pane.qr_label.pixmap() is not None
    assert view.viewport().height() == height
    pane.login_dialog.grab().save(str(Path(__file__).parent / "preview-0.5.12-music-login.png"))
    pane.on_failed("login", "模拟过期")
    assert not pane._login_pending and "模拟过期" in pane.login_status.text()
    pane.login()
    with patch.object(pane.secret, "save") as save:
        pane.on_completed("login", "test-credential")
        save.assert_called_once_with("test-credential")
    assert not pane.login_dialog.isVisible()

    center.resize(720, 580)
    apply_hud(app, {**HUD_DEFAULTS, "font_size": 16})
    QTest.qWait(60)
    assert view.viewport().height() >= center.height() * .50, (center.height(), view.viewport().height())
    assert pane.search.width() >= 100 and pane.mine_button.isVisible()
    center.grab().save(str(Path(__file__).parent / "preview-0.5.12-music-large-font.png"))
    pane._save_timer.stop()
    pane.bridge.close()
    controller.events.close()
    center.hide()
print(json.dumps(metrics))
print("music list space, search modes, paging, separate login and resume passed")
