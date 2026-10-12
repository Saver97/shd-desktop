"""Model profile migration and /models lookup against a local server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app import ConfigStore
from isac_ui import LlmSettingsWindow
from llm import LlmClient, SecretStore, ToolDispatcher
from services import ScheduleStore


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        assert self.path == "/v1/models"
        assert self.headers["Authorization"] == "Bearer local-key"
        payload = json.dumps({"data": [{"id": "model-z"}, {"id": "model-a"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = QApplication([])
with TemporaryDirectory() as temp:
    store = ConfigStore(Path(temp))
    store.data["llm"] = {"endpoint": f"http://127.0.0.1:{server.server_port}/v1", "model": "model-a"}
    SecretStore(store.file.parent / "llm-key.dpapi").save("local-key")
    events = ScheduleStore(store.file.parent / "state.db")
    client = LlmClient(store, ToolDispatcher(events, store, {}), app)
    assert client.profiles.active()["model"] == "model-a"
    assert client.profiles.active()["models"] == ["model-a"]
    assert client.profiles.secret(client.profiles.active()).load() == "local-key"
    second = client.profiles.add(client.profiles.active())
    assert len(client.profiles.profiles) == 2
    client.profiles.update(second["id"], name="second", mode="chat",
                           base_url=f"http://127.0.0.1:{server.server_port}/v1", model="model-z")
    assert second["models"] == ["model-a", "model-z"]
    assert client.profiles.active()["models"] == ["model-a"]
    client.profiles.activate_model(second["id"], "model-a")
    assert client.profiles.active()["model"] == "model-a"
    client.profiles.remove(second["id"])
    window = LlmSettingsWindow(client)
    window.show()
    QTimer.singleShot(1000, app.quit)
    app.exec()
    assert window.model.count() == 2, window.status.text()
    assert [window.model.itemText(i) for i in range(2)] == ["model-a", "model-z"]
    assert window.saved_models.count() == 1
    events.close()
server.shutdown()
server.server_close()
print("profile migration and model discovery passed")
