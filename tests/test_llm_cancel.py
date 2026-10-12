"""Aborted replies cannot surface as a late answer or alter the next turn."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QTimer

from shd_desktop.ai.llm import LlmClient, SecretStore, ToolDispatcher
from shd_desktop.data.services import ScheduleStore


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        time.sleep(0.6)
        data = json.dumps({"choices": [{"message": {"content": "迟到的回答"}}]}).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = QCoreApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    events = ScheduleStore(root / "state.db")
    SecretStore(root / "llm-key.dpapi").save("test-key")
    store = type("Store", (), {"data": {"llm": {"endpoint":
        f"http://127.0.0.1:{server.server_port}/v1", "model": "test-model"}},
        "file": root / "layout.json", "save": lambda self: None})()
    client = LlmClient(store, ToolDispatcher(events, store, {}), app)
    answers, interrupted = [], []
    client.answer.connect(answers.append)
    client.interrupted.connect(lambda: interrupted.append(True))
    client.ask("请等一下")
    QTimer.singleShot(80, client.cancel)
    QTimer.singleShot(900, app.quit)
    app.exec()
    assert not client.busy and interrupted == [True]
    assert not answers and not client.messages
    events.close()
server.shutdown()
server.server_close()
print("LLM interruption passed")
