"""Direct connections for QQ Music without changing Windows proxy settings."""

import os
from urllib.parse import urlsplit

MUSIC_HOSTS = ("qqmusic.qq.com", "aqqmusic.tc.qq.com", "y.qq.com")


def bypass_music_proxy(media_url: str = "") -> None:
    """FFmpeg/Paho read process proxy variables; bypass only music hosts.

    Qt has no per-player proxy option. Keep existing bypass entries and proxy
    URLs; the added entries live only in this application's environment.
    The CDN suffix also covers redirects to other QQ Music streaming nodes.
    """
    hosts = list(MUSIC_HOSTS)
    host = urlsplit(media_url).hostname
    if host:
        hosts.append(host)
    # Preserve both spellings on case-sensitive platforms; Windows aliases them.
    for name in ("no_proxy", "NO_PROXY"):
        value = os.environ.get(name, "")
        entries = {part.strip().lower() for part in value.split(",")}
        additions = [host for host in hosts if host.lower() not in entries]
        if additions:
            os.environ[name] = ",".join(filter(None, [value, *additions]))


def direct_playback_url(servers: list[str], path: str) -> str:
    # FFmpeg on Windows caches its own C runtime environment. Use a DNS CDN
    # covered by the startup bypass instead of the dispatch's changing raw IPs.
    for suffix in MUSIC_HOSTS:
        for server in servers:
            host = urlsplit(server).hostname or ""
            if host == suffix or host.endswith("." + suffix):
                return server.rstrip("/") + "/" + path.lstrip("/")
    raise RuntimeError("未取得可直连的音乐服务器地址，请重试")


def direct_music_client(credential=None):
    from qqmusic_api import Client

    bypass_music_proxy()
    client = Client(credential=credential, proxies={})
    # SDK 0.7.3 shares this session with login, device bootstrap and QIMEI.
    # An empty proxies dict alone still inherits environment/system proxies.
    client._session.trust_env = False
    client._session.proxies.clear()
    return client
