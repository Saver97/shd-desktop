"""OpenAI-compatible chat with bounded local tool calls."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import win32crypt
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtMultimedia import QMediaPlayer

from services import ScheduleStore
from llm_profiles import ProfileStore, endpoint


class SecretStore:
    def __init__(self, path: Path):
        self.path = path

    def save(self, value: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        protected = win32crypt.CryptProtectData(value.encode("utf-8"), "SHD Desktop API key", None, None, None, 0)
        temp = self.path.with_suffix(".tmp")
        temp.write_bytes(protected)
        temp.replace(self.path)

    def load(self) -> str:
        try:
            return win32crypt.CryptUnprotectData(self.path.read_bytes(), None, None, None, 0)[1].decode("utf-8")
        except Exception:
            return ""


TOOLS = [
    {"type": "function", "function": {"name": "create_event", "description": "创建本地日程",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": "本地时间 YYYY-MM-DD HH:mm"},
            "remind_minutes": {"type": "integer", "minimum": 0}},
            "required": ["title", "start"]}}},
    {"type": "function", "function": {"name": "list_events", "description": "查看日程及其稳定 ID",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "complete_event", "description": "按 ID 完成日程",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "delete_event", "description": "按稳定 ID 删除一项本地日程或提醒；先用 list_events 查到 ID",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "get_weather", "description": "读取已设置地区的最近一次天气",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_folder_panels", "description": "列出桌面文件夹面板及其 ID",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "show_folder_panel", "description": "显示一个已有桌面文件夹面板",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "music_control", "description": "控制应用内 QQ 音乐播放器",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["play", "pause", "next", "status"]}},
            "required": ["action"]}}},
    {"type": "function", "function": {"name": "list_notes", "description": "列出便签的标题、分组、预览及稳定 ID",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_note", "description": "按稳定 ID 阅读一张便签的完整内容",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "create_note", "description": "创建桌面便签",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}, "text": {"type": "string"}, "group": {"type": "string"}},
            "required": ["title", "text"]}}},
    {"type": "function", "function": {"name": "update_note", "description": "按稳定 ID 更新便签标题、正文或分组；先查看便签 ID",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"},
            "text": {"type": "string"}, "group": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "delete_note", "description": "按稳定 ID 将便签移入可恢复的回收区；先查看便签 ID",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
]


class ToolDispatcher:
    def __init__(self, events: ScheduleStore, store, panels: dict):
        self.events = events
        self.store = store
        self.panels = panels
        self.music = None
        self.notes = None

    def execute(self, name: str, args: dict) -> str:
        try:
            if name == "create_event":
                start = datetime.strptime(args["start"], "%Y-%m-%d %H:%M")
                event_id = self.events.add(args["title"], int(start.timestamp() * 1000),
                                           int(args.get("remind_minutes", 5)))
                return json.dumps({"id": event_id, "result": "已创建"}, ensure_ascii=False)
            if name == "list_events":
                return json.dumps(self.events.list()[:50], ensure_ascii=False)
            if name == "complete_event":
                event_id = args["id"]
                if not self.events.get(event_id):
                    return "未找到日程 ID"
                self.events.complete(event_id)
                return "已完成"
            if name == "delete_event":
                event_id = args["id"]
                event = self.events.get(event_id)
                if not event:
                    return "未找到日程 ID，未删除任何日程"
                self.events.delete(event_id)
                return json.dumps({"id": event_id, "title": event["title"], "result": "已删除"}, ensure_ascii=False)
            if name == "get_weather":
                cached = self.store.data.get("weather_cache")
                if not cached:
                    return "尚无天气数据，请先在天气页设置地区并刷新"
                return json.dumps({"location": self.store.data.get("weather_location"),
                                   "fetched_at": cached["fetched_at"],
                                   "current": cached["data"].get("current", {})}, ensure_ascii=False)
            if name == "list_folder_panels":
                return json.dumps([{"id": panel_id, "path": str(panel.folder)}
                                   for panel_id, panel in self.panels.items()], ensure_ascii=False)
            if name == "show_folder_panel":
                panel = self.panels.get(args["id"])
                if not panel:
                    return "未找到面板 ID"
                panel.show()
                return "已显示面板"
            if name == "music_control":
                if self.music is None:
                    return "音乐播放器尚未就绪"
                action = args["action"]
                if action == "status":
                    song = self.music.current_song
                    return json.dumps({"song": song, "state": str(self.music.player.playbackState())}, ensure_ascii=False)
                if action == "play":
                    if not self.music.current_song:
                        return "请先在音乐页搜索并选择歌曲"
                    if self.music.player.playbackState() != QMediaPlayer.PlayingState:
                        self.music.toggle_play()
                elif action == "pause":
                    self.music.player.pause()
                elif action == "next":
                    self.music.next_song()
                else:
                    return "未知播放命令"
                return "已执行播放器命令"
            if name in {"list_notes", "get_note", "create_note", "update_note", "delete_note"}:
                if self.notes is None:
                    return "便签功能尚未就绪"
                if name == "list_notes":
                    self.notes.flush()
                    return json.dumps([{"id": note["id"], "title": note.get("title", "新便签"),
                                        "group": note.get("group", "未分类"),
                                        "preview": note.get("text", "")[:160],
                                        "locked": bool(note.get("locked"))}
                                       for note in self.notes.store.notes if not note.get("deleted")][:100],
                                      ensure_ascii=False)
                if name == "create_note":
                    note = self.notes.new_note()
                    self.notes.update_note(note["id"], title=args["title"], text=args["text"],
                                           group=args.get("group"))
                    return json.dumps({"id": note["id"], "result": "已创建"}, ensure_ascii=False)
                note = self.notes.store.get(args["id"])
                if not note or note.get("deleted"):
                    return "未找到便签 ID"
                if name == "get_note":
                    self.notes.flush()
                    return json.dumps({key: note.get(key) for key in ("id", "title", "text", "group")},
                                      ensure_ascii=False)
                if name == "update_note":
                    self.notes.update_note(note["id"], title=args.get("title"), text=args.get("text"),
                                           group=args.get("group"))
                    return "已更新便签"
                self.notes.delete_note(note, confirm=False)
                return "已移入便签回收区" if note.get("deleted") else "便签未删除"
            return "未知工具"
        except (KeyError, ValueError, TypeError, OSError) as exc:
            return f"工具执行失败：{exc}"


SYSTEM_PROMPT = ("你是 SHD Desktop 的简洁中文桌面助手。需要操作日程、便签、天气、桌面面板或音乐时调用工具。"
                 "时间均为用户本地时间。删除提醒前先用 list_events 查到准确 ID；删除或更新便签前先用 list_notes 查到准确 ID；若有多条可能匹配，先请用户确认。"
                 "不要声称未执行的操作已完成。")
RESPONSES_TOOLS = [{"type": "function", **tool["function"]} for tool in TOOLS]


class LlmClient(QObject):
    answer = Signal(str)
    error = Signal(str)
    busy_changed = Signal(bool)
    tools_changed = Signal()
    profile_changed = Signal()
    interrupted = Signal()

    def __init__(self, store, dispatcher: ToolDispatcher, parent: QObject | None = None):
        super().__init__(parent)
        self.store = store
        self.profiles = ProfileStore(store, SecretStore)
        self.dispatcher = dispatcher
        self.network = QNetworkAccessManager(self)
        self.messages: list[dict] = []
        self.response_id: str | None = None
        self.response_input: list[dict] = []
        self.busy = False
        self.round = 0
        self._generation = 0
        self._reply = None
        self._turn_start = 0
        self._turn_response_id: str | None = None

    def activate(self, profile_id: str) -> None:
        if self.busy:
            raise ValueError("当前回复完成后再切换配置")
        self.profiles.activate(profile_id)
        self.clear_history()
        self.profile_changed.emit()

    def activate_model(self, profile_id: str, model: str) -> None:
        if self.busy:
            raise ValueError("请先中断或等待当前回复")
        self.profiles.activate_model(profile_id, model)
        self.clear_history()
        self.profile_changed.emit()

    def clear_history(self) -> None:
        self.messages.clear()
        self.response_id = None
        self.response_input.clear()

    def ask(self, prompt: str) -> None:
        if self.busy or not prompt.strip():
            return
        profile = self.profiles.active()
        if not profile.get("base_url") or not profile.get("model") or not self.profiles.secret(profile).load():
            self.error.emit("请先在模型配置窗口填写 API 地址、模型名和密钥")
            return
        self._turn_start = len(self.messages)
        self._turn_response_id = self.response_id
        self._generation += 1
        if profile.get("mode") == "responses":
            self.response_input = [{"role": "user", "content": prompt.strip()}]
        else:
            if not self.messages:
                self.messages.append({"role": "system", "content": SYSTEM_PROMPT})
            self.messages.append({"role": "user", "content": prompt.strip()})
        self.round = 0
        self.busy = True
        self.busy_changed.emit(True)
        self._request()

    def cancel(self) -> bool:
        if not self.busy:
            return False
        self._generation += 1
        reply = self._reply
        self._reply = None
        self.messages = self.messages[:self._turn_start]
        self.response_id = self._turn_response_id
        self.response_input.clear()
        self.busy = False
        if reply is not None:
            reply.abort()
        self.busy_changed.emit(False)
        self.interrupted.emit()
        return True

    def _finish(self, answer: str | None = None, error: str | None = None) -> None:
        self.busy = False
        self.busy_changed.emit(False)
        if error:
            self.error.emit(error)
        elif answer is not None:
            if self.profiles.active().get("mode") != "responses":
                self.messages.append({"role": "assistant", "content": answer})
            self.answer.emit(answer)

    def _request(self) -> None:
        if self.round >= 5:
            self._finish(error="工具调用次数超过上限")
            return
        profile = self.profiles.active()
        mode = profile.get("mode", "chat")
        try:
            address = endpoint(profile["base_url"], mode)
        except ValueError as exc:
            self._finish(error=str(exc))
            return
        request = QNetworkRequest(QUrl(address))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setRawHeader(b"Authorization", ("Bearer " + self.profiles.secret(profile).load()).encode("utf-8"))
        if mode == "responses":
            payload = {"model": profile["model"], "instructions": SYSTEM_PROMPT,
                       "input": self.response_input, "tools": RESPONSES_TOOLS, "store": True}
            if self.response_id:
                payload["previous_response_id"] = self.response_id
        else:
            payload = {"model": profile["model"], "messages": self.messages,
                       "tools": TOOLS, "tool_choice": "auto"}
        reply = self.network.post(request, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self._reply = reply
        generation = self._generation

        def finished():
            if generation != self._generation:
                reply.deleteLater()
                return
            self._reply = None
            try:
                raw = bytes(reply.readAll()).decode("utf-8", "replace")
                status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
                if status and int(status) >= 400:
                    raise RuntimeError(f"HTTP {status}: {raw[:400]}")
                if reply.error() != QNetworkReply.NoError:
                    raise RuntimeError(reply.errorString())
                result = json.loads(raw)
                if mode == "responses":
                    self._handle_responses(result)
                else:
                    self._handle_chat(result)
            except (KeyError, IndexError, TypeError, ValueError, RuntimeError) as exc:
                self._finish(error=str(exc))
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)

    def _handle_chat(self, result: dict) -> None:
        message = result["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            self._finish(answer=message.get("content") or "（模型未返回文字）")
            return
        self.messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        for call in calls:
            args = json.loads(call["function"].get("arguments") or "{}")
            outcome = self.dispatcher.execute(call["function"]["name"], args)
            self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": outcome})
        self.tools_changed.emit()
        self.round += 1
        self._request()

    def _handle_responses(self, result: dict) -> None:
        calls = [item for item in result.get("output", []) if item.get("type") == "function_call"]
        self.response_id = result.get("id")
        if calls:
            if not self.response_id:
                raise ValueError("Responses 返回工具调用但缺少 response ID")
            self.response_input = []
            for call in calls:
                args = json.loads(call.get("arguments") or "{}")
                outcome = self.dispatcher.execute(call["name"], args)
                self.response_input.append({"type": "function_call_output", "call_id": call["call_id"],
                                            "output": outcome})
            self.tools_changed.emit()
            self.round += 1
            self._request()
            return
        answer = result.get("output_text")
        if not answer:
            parts = [content.get("text", "") for item in result.get("output", [])
                     if item.get("type") == "message" for content in item.get("content", [])
                     if content.get("type") == "output_text"]
            answer = "\n".join(part for part in parts if part)
        self._finish(answer=answer or "（模型未返回文字）")
