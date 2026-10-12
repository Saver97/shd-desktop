"""Local schedule storage and an Open-Meteo weather client."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, QUrlQuery, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class ScheduleStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                remind_minutes INTEGER NOT NULL DEFAULT 5,
                done INTEGER NOT NULL DEFAULT 0,
                notified_at INTEGER,
                snooze_until INTEGER,
                created_at INTEGER NOT NULL
            )
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def add(self, title: str, start_ms: int, remind_minutes: int = 5) -> str:
        title = title.strip()
        if not title or remind_minutes < 0:
            raise ValueError("日程标题不能为空，提醒分钟数不能为负")
        event_id = uuid.uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO events(id,title,start_ms,remind_minutes,created_at) VALUES(?,?,?,?,?)",
                (event_id, title, int(start_ms), int(remind_minutes), int(time.time() * 1000)),
            )
        return event_id

    def list(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events ORDER BY start_ms, created_at").fetchall()
        return [dict(row) for row in rows]

    def get(self, event_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return dict(row) if row else None

    def complete(self, event_id: str, done: bool = True) -> None:
        with self.db:
            self.db.execute("UPDATE events SET done=? WHERE id=?", (int(done), event_id))

    def rename(self, event_id: str, title: str) -> None:
        with self.db:
            self.db.execute("UPDATE events SET title=? WHERE id=?", (title, event_id))

    def delete(self, event_id: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM events WHERE id=?", (event_id,))

    def delete_many(self, event_ids: list[str]) -> int:
        ids = list(dict.fromkeys(event_ids))
        if not ids:
            return 0
        with self.db:
            before = self.db.total_changes
            self.db.executemany("DELETE FROM events WHERE id=?", ((event_id,) for event_id in ids))
            return self.db.total_changes - before

    def snooze(self, event_id: str, minutes: int = 10) -> None:
        if minutes <= 0:
            raise ValueError("稍后提醒分钟数必须大于 0")
        until = int(time.time() * 1000) + minutes * 60000
        with self.db:
            self.db.execute("UPDATE events SET snooze_until=?, notified_at=NULL WHERE id=?", (until, event_id))

    def due(self, now_ms: int | None = None) -> list[dict]:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        pending = self.db.execute(
            "SELECT * FROM events WHERE done=0 AND notified_at IS NULL ORDER BY start_ms"
        ).fetchall()
        result = []
        for row in pending:
            target = row["snooze_until"] or row["start_ms"] - row["remind_minutes"] * 60000
            if target <= now < target + 300000:
                result.append(dict(row))
        return result

    def mark_notified(self, event_id: str, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        with self.db:
            self.db.execute("UPDATE events SET notified_at=? WHERE id=?", (now, event_id))


class WeatherClient(QObject):
    locations = Signal(list)
    forecast = Signal(dict)
    forecast_for = Signal(str, dict)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)

    def _get(self, base: str, params: dict, callback) -> None:
        url = QUrl(base)
        query = QUrlQuery()
        for key, value in params.items():
            query.addQueryItem(key, str(value))
        url.setQuery(query)
        reply = self.network.get(QNetworkRequest(url))

        def finished():
            import json
            try:
                if reply.error() != QNetworkReply.NoError:
                    raise RuntimeError(reply.errorString())
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
                if data.get("error"):
                    raise RuntimeError(data.get("reason", "天气服务返回错误"))
                callback(data)
            except (ValueError, RuntimeError) as exc:
                self.error.emit(str(exc))
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)

    def search(self, city: str) -> None:
        self._get("https://geocoding-api.open-meteo.com/v1/search",
                  {"name": city, "count": 10, "language": "zh", "format": "json"},
                  lambda data: self.locations.emit(data.get("results", [])))

    def fetch(self, latitude: float, longitude: float, timezone: str = "auto",
              request_id: str = "") -> None:
        self._get("https://api.open-meteo.com/v1/forecast", {
            "latitude": latitude, "longitude": longitude, "timezone": timezone,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
            "forecast_days": 4,
        }, lambda data: (self.forecast_for.emit(request_id, data), self.forecast.emit(data)))
