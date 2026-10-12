"""End-to-end local tool-call check without an external API key."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QTimer

from shd_desktop.ai.llm import LlmClient, SecretStore, ToolDispatcher
from shd_desktop.data.services import ScheduleStore


class Handler(BaseHTTPRequestHandler):
    calls = {"chat": 0, "responses": 0}

    def do_POST(self):
        size = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(size))
        assert request["model"] == "test-model", request
        mode = "responses" if self.path.endswith("/responses") else "chat"
        Handler.calls[mode] += 1
        if mode == "responses":
            if Handler.calls[mode] == 1:
                body_obj = {"id": "resp-1", "output": [{"type": "function_call", "name": "list_events",
                    "call_id": "r-call-1", "arguments": "{}"}]}
            else:
                assert request["previous_response_id"] == "resp-1"
                assert request["input"][0]["type"] == "function_call_output"
                body_obj = {"id": "resp-2", "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "已列出日程"}]}]}
        elif Handler.calls[mode] == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call-1", "type": "function", "function": {"name": "create_event",
                "arguments": json.dumps({"title": "本地接口测试", "start": "2030-01-01 09:00"})}}]}
            body_obj = {"choices": [{"message": message}]}
        else:
            assert any(x.get("role") == "tool" for x in request["messages"])
            message = {"role": "assistant", "content": "日程已创建"}
            body_obj = {"choices": [{"message": message}]}
        body = json.dumps(body_obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
app = QCoreApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    events = ScheduleStore(root / "state.db")
    secret = SecretStore(root / "llm-key.dpapi")
    secret.save("test-key")
    store = type("Store", (), {"data": {"llm": {"endpoint":
        f"http://127.0.0.1:{server.server_port}/v1", "model": "test-model"}},
        "file": root / "layout.json", "save": lambda self: None})()
    client = LlmClient(store, ToolDispatcher(events, store, {}), app)
    answers = []
    errors = []
    client.answer.connect(lambda message: (answers.append(message), app.quit()))
    client.error.connect(lambda message: (errors.append(message), app.quit()))
    QTimer.singleShot(5000, app.quit)
    client.ask("2030 年 1 月 1 日 9 点提醒我")
    app.exec()
    assert not errors, errors
    assert answers == ["日程已创建"], answers
    assert [x["title"] for x in events.list()] == ["本地接口测试"]
    assert Handler.calls["chat"] == 2
    profile = client.profiles.active()
    client.profiles.update(profile["id"], name="Responses 测试", mode="responses",
                           base_url=f"http://127.0.0.1:{server.server_port}/v1", model="test-model")
    client.clear_history()
    answers.clear()
    client.ask("列出日程")
    app.exec()
    assert not errors, errors
    assert answers == ["已列出日程"], answers
    assert Handler.calls["responses"] == 2
    events.close()
server.shutdown()
server.server_close()
print("LLM tool-call round trip passed")
