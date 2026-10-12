"""A second launch forwards desktop actions to the primary app."""

import uuid
import subprocess
import sys

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

import instance


app = QCoreApplication([])
instance.server_name = lambda: f"SHDDesktop-test-{uuid.uuid4().hex}"
name = instance.server_name()
instance.server_name = lambda: name
server = instance.claim_or_forward(app)
assert server is not None
opened = []
instance.receive_requests(server, lambda: opened.append("center"),
                          lambda: opened.append("note"))
for request in ("center", "note"):
    child = subprocess.Popen([sys.executable, "-c",
        "import sys, instance; from PySide6.QtCore import QCoreApplication; "
        "app=QCoreApplication([]); instance.server_name=lambda:sys.argv[1]; "
        "sys.exit(0 if instance.claim_or_forward(app, sys.argv[2]) is None else 2)",
        name, request])
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if len(opened) >= (1 if request == "center" else 2) else None)
    timer.start()
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    timer.stop()
    assert child.wait(timeout=3) == 0
assert opened == ["center", "note"]
server.close()
print("single-instance forwarding passed")
