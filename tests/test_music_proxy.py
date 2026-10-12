"""Verify actual SDK/FFmpeg routing in fresh processes, as in an EXE launch."""

import asyncio
import io
import os
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shd_desktop.music.music_network import bypass_music_proxy, direct_music_client, direct_playback_url


def playback_child(url, direct):
    if direct:
        # Must precede multimedia DLL loading on Windows.
        bypass_music_proxy(url)
    from PySide6.QtCore import QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    player, audio = QMediaPlayer(), QAudioOutput()
    audio.setVolume(0)
    player.setAudioOutput(audio)
    player.setSource(QUrl(url))
    player.play()
    deadline = time.monotonic() + 10
    while player.position() == 0 and time.monotonic() < deadline:
        QTest.qWait(20)
    assert player.position() > 0, player.errorString()
    player.setPosition(1000)
    QTest.qWait(100)
    assert player.position() >= 1000
    player.stop()
    player.setSource(QUrl())
    assert os.environ["HTTP_PROXY"] == os.environ["HTTPS_PROXY"]


def run():
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 8000 * 3)
    payload = audio.getvalue()
    hits = {"origin": 0, "proxy": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits[self.server.kind] += 1
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    origin = ThreadingHTTPServer(("127.0.0.2", 0), Handler)
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    origin.kind, proxy.kind = "origin", "proxy"
    for server in (origin, proxy):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.2:{origin.server_port}/track.wav"
    proxy_url = f"http://127.0.0.1:{proxy.server_port}"
    names = ("http_proxy", "https_proxy", "all_proxy", "mqtt_proxy", "no_proxy",
             "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "MQTT_PROXY", "NO_PROXY")
    saved = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ[name] = "existing.invalid" if name.lower() == "no_proxy" else proxy_url
        for direct in (False, True):
            before = hits.copy()
            subprocess.run([sys.executable, "-m", "tests.test_music_proxy", "--play", url,
                            str(int(direct))],
                           check=True, timeout=45)
            target = "origin" if direct else "proxy"
            other = "proxy" if direct else "origin"
            assert hits[target] > before[target] and hits[other] == before[other], hits
        print("FFmpeg: baseline used proxy; startup music bypass played and sought directly")

        async def api_request():
            client = direct_music_client()
            try:
                response = await client._session.get(url, timeout=5)
                await client._session.gather(response)
                assert response.content == payload
                assert not client._context._qimei_manager._session.trust_env
            finally:
                await client.close()

        before = hits.copy()
        asyncio.run(api_request())
        assert hits["origin"] > before["origin"] and hits["proxy"] == before["proxy"]
        assert "127.0.0.2" not in os.environ["NO_PROXY"]
        print("QQ Music SDK reached origin directly without an origin bypass entry")
        bypass_music_proxy()
        assert os.environ["NO_PROXY"].split(",").count("qqmusic.qq.com") == 1
        assert "existing.invalid" in os.environ["NO_PROXY"]
        assert os.environ["HTTP_PROXY"] == proxy_url
        assert os.environ["HTTPS_PROXY"] == proxy_url
        from qqmusic_api.modules.login import MqttClient
        mqtt = MqttClient(client_id="test", host="mu.y.qq.com", port=443)
        assert mqtt._create_paho_client()._get_proxy() is None
        # Real dispatch ordering includes raw IPs before DNS streaming nodes.
        servers = ["http://119.84.242.50/", "http://aqqmusic.tc.qq.com/amobile.music.tc.qq.com/",
                   "http://sjy6.stream.qqmusic.qq.com/"]
        assert direct_playback_url(servers, "song.m4a") == "http://sjy6.stream.qqmusic.qq.com/song.m4a"
        print("Proxy URLs/bypass entries preserved; MQTT bypass and CDN selection passed")
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        for server in (origin, proxy):
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        playback_child(sys.argv[2], bool(int(sys.argv[3])))
    else:
        run()
