"""Last QQ Music list and song survive a new player instance."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from shd_desktop.music.music import MusicPane


app = QApplication([])
song = {"kind": "song", "mid": "test-mid", "title": "测试歌曲",
        "artist": "测试歌手", "song_type": 0}
with TemporaryDirectory() as temp:
    root = Path(temp)
    first = MusicPane(root)
    first.current_song = song
    first.queue = [song]
    first._render_items([song])
    first._last_position_ms = 42000
    first.persist()
    first.bridge.close()
    second = MusicPane(root)
    assert second.current_song == song
    assert second.queue == [song]
    assert second.results.count() == 1
    assert second._last_position_ms == 42000
    calls = []
    second.bridge.submit = lambda kind, value: calls.append((kind, value))
    second.toggle_play()
    assert calls == [("url", song)] and second._resume_ms == 42000
    second.bridge.close()
print("QQ Music state and resume passed")
