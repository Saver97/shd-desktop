"""Optional QQ Music adapter and a small in-app player.

The community API is deliberately kept behind this module: failures are shown
to the user and never prevent the other desktop features from starting.
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from music_network import bypass_music_proxy, direct_music_client, direct_playback_url

bypass_music_proxy()

from PySide6.QtCore import QObject, Signal, QTimer, QUrl, Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QSlider,
    QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget,
)
from theme import hud_section, scaled_style

from llm import SecretStore

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def _song(item) -> dict:
    singers = getattr(item, "singer", []) or []
    return {"kind": "song", "mid": str(item.mid), "title": str(item.name),
            "artist": " / ".join(s.name for s in singers),
            "song_type": getattr(item, "type", 0)}


def _playlist(item) -> dict:
    return {"kind": "playlist", "id": int(item.id),
            "title": str(item.title),
            "artist": str(getattr(item, "nickname", getattr(item, "nick", "")))}


def _query(kind: str, value: str | dict, credential_json: str, qr_ready) -> object:
    from qqmusic_api import Credential
    from qqmusic_api.models.login import QRLoginType
    from qqmusic_api.modules.search import SearchType
    from qqmusic_api.modules.song import SongFileInfo
    from qqmusic_api.modules.login_utils import QRCodeLoginSession

    async def run():
        credential = Credential.model_validate_json(credential_json) if credential_json and kind != "login" else None
        client = direct_music_client(credential)
        try:
            if kind == "login":
                session = QRCodeLoginSession(client.login, QRLoginType.QQ)
                qr = await session.get_qrcode()
                qr_ready(qr.data)
                result = await session.wait_qrcode_login()
                return result.model_dump_json()
            if kind == "my_playlists":
                if credential is None:
                    raise RuntimeError("请先扫码登录 QQ 音乐")
                response = await client.user.get_created_songlist(int(credential.musicid))
                return [_playlist(x) for x in response.playlists]
            if kind == "songs":
                items = await client.search.search_by_type(str(value), SearchType.SONG, num=20).collect_items(limit=20)
                return [_song(x) for x in items]
            if kind == "playlists":
                items = await client.search.search_by_type(str(value), SearchType.SONGLIST, num=20).collect_items(limit=20)
                return [_playlist(x) for x in items]
            if kind == "playlist_songs":
                playlist_id = int(value["id"] if isinstance(value, dict) else value)
                page_number = int(value.get("page", 1) if isinstance(value, dict) else 1)
                page = await client.songlist.get_detail(playlist_id, num=50, page=page_number)
                return {"items": [_song(x) for x in page.songs], "total": page.total,
                        "page": page_number, "id": playlist_id}
            if kind == "url":
                info = SongFileInfo(mid=value["mid"], song_type=value.get("song_type") or 0)
                urls = await client.song.get_song_urls([info])
                dispatch = await client.song.get_cdn_dispatch()
                item = next((x for x in urls.data if x.mid == value["mid"] and x.purl), None)
                if not item:
                    raise RuntimeError("未取得播放地址；歌曲可能需要登录、会员或受版权限制")
                if not dispatch.sip:
                    raise RuntimeError("未取得音频服务器地址")
                return direct_playback_url(dispatch.sip, item.purl)
            raise ValueError("未知音乐请求")
        finally:
            await client.close()

    return asyncio.run(run())


class MusicBridge(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str)
    qr_ready = Signal(bytes)

    def __init__(self, secret: SecretStore, parent=None):
        super().__init__(parent)
        self.secret = secret
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="qqmusic")

    def submit(self, kind: str, value: str | dict) -> None:
        future = self.pool.submit(_query, kind, value, self.secret.load(), self.qr_ready.emit)

        def finished(done):
            try:
                self.completed.emit(kind, done.result())
            except Exception as exc:
                self.failed.emit(kind, str(exc))

        future.add_done_callback(finished)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)


class MusicItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(18, option.fontMetrics.height()) + 14)
        return size


class MusicPane(QWidget):
    def __init__(self, data_root: Path):
        super().__init__()
        self.setObjectName("MusicPane")
        self.state_file = data_root / "music-state.json"
        self.saved_state = self._load_state()
        self._last_position_ms = int(self.saved_state.get("position_ms") or 0)
        self._resume_ms = 0
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(2000)
        self._save_timer.timeout.connect(self.persist)
        self.secret = SecretStore(data_root / "qq-credential.dpapi")
        self.bridge = MusicBridge(self.secret, self)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.6)
        self.current_song: dict | None = self.saved_state.get("current_song")
        self.queue: list[dict] = self.saved_state.get("queue") or []
        self.current_playlist: dict | None = self.saved_state.get("current_playlist")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(hud_section("音乐", ICON_DIR / "cat-media-gen-64.png"))
        self.search = QLineEdit()
        self.search.setObjectName("MusicSearch")
        self.search.setPlaceholderText("搜索歌曲或歌单")
        self.search.setMinimumWidth(100)
        self.search.returnPressed.connect(self.search_selected)
        row.addWidget(self.search, 1)
        self.search_type = QComboBox()
        self.search_type.setObjectName("MusicSearchType")
        self.search_type.addItem("歌曲", "songs")
        self.search_type.addItem("歌单", "playlists")
        row.addWidget(self.search_type)
        self.search_button = QPushButton("搜索")
        self.search_button.setObjectName("MusicAction")
        self.search_button.clicked.connect(self.search_selected)
        row.addWidget(self.search_button)
        self.mine_button = QPushButton("我的歌单")
        self.mine_button.setObjectName("MusicAction")
        self.mine_button.clicked.connect(lambda: self.bridge.submit("my_playlists", ""))
        row.addWidget(self.mine_button)
        account_button = QToolButton()
        account_button.setObjectName("MusicAccount")
        account_button.setText("账号")
        account_button.setPopupMode(QToolButton.InstantPopup)
        account_menu = QMenu(account_button)
        account_menu.addAction("QQ 扫码登录", self.login)
        account_button.setMenu(account_menu)
        row.addWidget(account_button)
        root.addLayout(row)

        self._login_pending = False
        self.login_dialog = QDialog(self)
        self.login_dialog.setWindowTitle("QQ 音乐扫码登录")
        self.login_dialog.setMinimumWidth(340)
        login_layout = QVBoxLayout(self.login_dialog)
        login_layout.setContentsMargins(20, 20, 20, 20)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumHeight(180)
        login_layout.addWidget(self.qr_label)
        self.login_status = QLabel()
        self.login_status.setWordWrap(True)
        login_layout.addWidget(self.login_status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.login_dialog.reject)
        login_layout.addWidget(buttons)
        self.results = QListWidget()
        self.results.setObjectName("MusicResults")
        self.results.setUniformItemSizes(True)
        self.results.setItemDelegate(MusicItemDelegate(self.results))
        self.results.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.results.itemDoubleClicked.connect(self.open_item)
        root.addWidget(self.results, 1)
        pages = QHBoxLayout()
        self.status = QLabel("双击歌曲播放；双击歌单查看。部分内容需要 QQ 音乐账号或会员。")
        self.status.setObjectName("MusicStatus")
        self.status.setWordWrap(True)
        pages.addWidget(self.status, 1)
        self.prev_page = QPushButton("上一页")
        self.prev_page.setObjectName("MusicAction")
        self.prev_page.clicked.connect(lambda: self.change_page(-1))
        self.prev_page.setEnabled(False)
        self.next_page = QPushButton("下一页")
        self.next_page.setObjectName("MusicAction")
        self.next_page.clicked.connect(lambda: self.change_page(1))
        self.next_page.setEnabled(False)
        pages.addWidget(self.prev_page)
        pages.addWidget(self.next_page)
        root.addLayout(pages)
        controls = QHBoxLayout()
        self.play_button = QPushButton("播放 / 暂停")
        self.play_button.setProperty("hudRole", "primary")
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)
        next_button = QPushButton("下一首")
        next_button.setObjectName("MusicAction")
        next_button.clicked.connect(self.next_song)
        controls.addWidget(next_button)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setMaximumWidth(160)
        self.volume.setToolTip("播放音量")
        self.volume.setRange(0, 100)
        self.volume.setValue(int(self.saved_state.get("volume", 60)))
        self.volume.valueChanged.connect(lambda x: self.audio.setVolume(x / 100))
        self.volume.valueChanged.connect(lambda _: self._save_timer.start())
        self.audio.setVolume(self.volume.value() / 100)
        controls.addStretch()
        controls.addWidget(QLabel("音量"))
        controls.addWidget(self.volume)
        root.addLayout(controls)
        self.bridge.completed.connect(self.on_completed)
        self.bridge.failed.connect(self.on_failed)
        self.bridge.qr_ready.connect(self.show_qr)
        self.player.errorOccurred.connect(lambda _error, message: self.status.setText(f"播放失败：{message}"))
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.playbackStateChanged.connect(lambda _: self._save_timer.start())
        self.apply_hud()
        self._render_items(self.saved_state.get("results") or [])
        if self.current_playlist:
            page = self.current_playlist.get("page", 1)
            total = self.current_playlist.get("total", 0)
            self.prev_page.setEnabled(page > 1)
            self.next_page.setEnabled(page * 50 < total)
        if self.current_song:
            self.status.setText(f"上次播放：{self.current_song['title']}；点击播放可续播")
        elif self.results.count():
            self.status.setText("已恢复上次列表；双击歌曲播放")

    def apply_hud(self) -> None:
        self.setStyleSheet(scaled_style('''
            QListWidget#MusicResults { background: transparent; border: 0;
                padding: 0; border-radius: 0; }
            QListWidget#MusicResults::item { padding: 7px 10px;
                border-bottom: 1px solid #303238; border-left: 2px solid transparent; }
            QListWidget#MusicResults::item:selected { background: #332B24;
                border-left: 2px solid #F48A35; color: #FFFFFF; }
            QListWidget#MusicResults::item:hover { background: #27292D; }
            QLineEdit#MusicSearch, QComboBox#MusicSearchType { padding: 5px 7px; }
            QLabel#MusicStatus { color: #9399A2; font-size: 11px; }
            QPushButton#MusicAction, QToolButton#MusicAccount { background: transparent;
                border: 0; padding: 5px 10px; }
            QPushButton#MusicAction:hover, QToolButton#MusicAccount:hover {
                background: #303238; color: #FFAE70; }
            QPushButton#MusicAction:disabled { color: #656A72; background: transparent; }
        '''))

    def _load_state(self) -> dict:
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def persist(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"current_song": self.current_song, "queue": self.queue,
                "current_playlist": self.current_playlist,
                "results": [self.results.item(index).data(Qt.UserRole)
                            for index in range(self.results.count())],
                "position_ms": self._last_position_ms, "volume": self.volume.value()}
        temp = self.state_file.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.state_file)

    def _render_items(self, items: list[dict]) -> None:
        self.results.clear()
        for record in items:
            if not isinstance(record, dict) or "title" not in record:
                continue
            label = f"{record['title']}  ·  {record.get('artist', '')}"
            item = QListWidgetItem(label)
            item.setToolTip(label)
            item.setData(Qt.UserRole, record)
            self.results.addItem(item)

    def _search(self, kind: str):
        query = self.search.text().strip()
        if query:
            self.status.setText("正在搜索…")
            self.bridge.submit(kind, query)

    def search_songs(self):
        self._search("songs")

    def search_selected(self):
        self._search(self.search_type.currentData())

    def search_playlists(self):
        self._search("playlists")

    def login(self):
        self.login_dialog.open()
        if self._login_pending:
            return
        self._login_pending = True
        self.qr_label.clear()
        self.login_status.setText("正在获取 QQ 登录二维码…")
        self.bridge.submit("login", "")

    def on_failed(self, kind, error):
        self.status.setText(f"{kind} 失败：{error}")
        if kind == "login":
            self._login_pending = False
            self.login_status.setText(f"登录失败：{error}")

    def show_qr(self, data: bytes):
        picture = QPixmap()
        if picture.loadFromData(data):
            self.qr_label.setPixmap(picture.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.login_status.setText("请用 QQ 扫码并确认登录；二维码约 3 分钟后过期")
        else:
            self.login_status.setText("二维码格式无法显示")

    def on_completed(self, kind: str, data: object):
        if kind == "login":
            self._login_pending = False
            self.secret.save(str(data))
            self.qr_label.clear()
            self.login_dialog.accept()
            self.status.setText("QQ 音乐账号已连接，可查看我的歌单")
            return
        if kind == "url":
            bypass_music_proxy(str(data))
            self.player.setSource(QUrl(str(data)))
            self.player.play()
            self.status.setText(f"正在播放：{self.current_song['title']} — {self.current_song['artist']}")
            self.persist()
            return
        if kind == "playlist_songs":
            self.current_playlist = data
            items = data["items"]
            self.prev_page.setEnabled(data["page"] > 1)
            self.next_page.setEnabled(data["page"] * 50 < data["total"])
        else:
            items = list(data)
            self.current_playlist = None
            self.prev_page.setEnabled(False)
            self.next_page.setEnabled(False)
        self._render_items(items)
        if kind in ("songs", "playlist_songs"):
            self.queue = items
        if kind == "playlist_songs":
            self.status.setText(f"第 {data['page']} 页 · {len(items)} 首 / 共 {data['total']} 首；双击播放")
        else:
            self.status.setText(f"{len(items)} 项结果；双击打开" if items else "没有结果")
        self.persist()

    def open_item(self, item: QListWidgetItem):
        record = item.data(Qt.UserRole)
        if record["kind"] == "playlist":
            self.status.setText("正在读取歌单…")
            self.bridge.submit("playlist_songs", {"id": record["id"], "page": 1})
        else:
            self.play_song(record)

    def play_song(self, record: dict, resume: bool = False):
        self.current_song = record
        self._resume_ms = self._last_position_ms if resume else 0
        if not resume:
            self._last_position_ms = 0
        self.status.setText("正在获取播放地址…")
        self.persist()
        self.bridge.submit("url", record)

    def change_page(self, delta: int):
        if self.current_playlist:
            page = self.current_playlist["page"] + delta
            if page >= 1 and (page - 1) * 50 < self.current_playlist["total"]:
                self.status.setText("正在读取歌单…")
                self.bridge.submit("playlist_songs", {"id": self.current_playlist["id"], "page": page})

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.player.source().isValid():
            self.player.play()
        elif self.current_song:
            self.play_song(self.current_song, resume=True)
        else:
            self.status.setText("请先选择歌曲")

    def next_song(self):
        if self.current_song in self.queue:
            index = self.queue.index(self.current_song) + 1
            if index < len(self.queue):
                self.play_song(self.queue[index])

    def on_media_status(self, status):
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia) and self._resume_ms:
            self.player.setPosition(self._resume_ms)
            self._resume_ms = 0
        if status == QMediaPlayer.EndOfMedia:
            self.next_song()

    def on_position_changed(self, position: int) -> None:
        if position >= 0 and self.player.source().isValid():
            self._last_position_ms = position
            self._save_timer.start()

    def closeEvent(self, event):
        self.persist()
        self.player.stop()
        self.bridge.close()
        super().closeEvent(event)
