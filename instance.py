"""Forward desktop-menu launches to the running app."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QIODevice
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name() -> str:
    user = hashlib.sha256(str(Path.home()).casefold().encode("utf-8")).hexdigest()[:16]
    return f"SHDDesktop-{user}"


def _forward(name: str, request: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(name, QIODevice.WriteOnly)
    if not socket.waitForConnected(350):
        return False
    socket.write(request.encode("ascii") + b"\n")
    sent = socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return sent


def claim_or_forward(app, request: str = "center") -> QLocalServer | None:
    """Return a server for the primary app, or None after forwarding."""
    name = server_name()
    if _forward(name, request):
        return None
    server = QLocalServer(app)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if server.listen(name):
        return server
    if _forward(name, request):
        return None
    raise OSError(f"无法建立 SHD Desktop 单实例通道：{server.errorString()}")


def receive_requests(server: QLocalServer, open_center, new_note=None) -> None:
    def connected():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()

            def consume(current=socket):
                request = bytes(current.readAll()).strip()
                if request == b"center":
                    open_center()
                elif request == b"note" and new_note is not None:
                    new_note()
                current.disconnectFromServer()
                current.deleteLater()

            socket.readyRead.connect(consume)
            if socket.bytesAvailable():
                consume()

    server.newConnection.connect(connected)
