"""Saved weather locations keep separate caches and switch without losing data."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app import ConfigStore
from shd_desktop.ui.center import WeatherPane


class FakeWeather(QObject):
    locations = Signal(list)
    forecast_for = Signal(str, dict)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls = []

    def search(self, query):
        pass

    def fetch(self, latitude, longitude, timezone="auto", request_id=""):
        self.calls.append(request_id)


app = QApplication([])
with TemporaryDirectory() as temp:
    store = ConfigStore(Path(temp))
    store.data["weather_location"] = {"name": "香港", "latitude": 22.3,
                                      "longitude": 114.2, "timezone": "Asia/Hong_Kong"}
    store.data["weather_cache"] = {"fetched_at": 1790460000, "data": {"current": {"temperature_2m": 25}}}
    client = FakeWeather()
    pane = WeatherPane(store, client)
    first_id = store.data["weather_active_id"]
    assert len(store.data["weather_locations"]) == 1
    assert store.data["weather_caches"][first_id]["data"]["current"]["temperature_2m"] == 25
    second = {"id": "second", "name": "上海", "latitude": 31.2,
              "longitude": 121.5, "timezone": "Asia/Shanghai"}
    pane.saved_locations.append(second)
    pane.refresh_location_list()
    pane.select_location(1)
    assert store.data["weather_location"]["name"] == "上海"
    assert client.calls[-1] == "second"
    client.forecast_for.emit("second", {"current": {"temperature_2m": 28}})
    assert store.data["weather_caches"]["second"]["data"]["current"]["temperature_2m"] == 28
    pane.select_location(0)
    assert store.data["weather_cache"]["data"]["current"]["temperature_2m"] == 25
print("multiple weather locations passed")
