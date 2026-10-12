"""Forecast remains visible while location management is out of the daily view."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog

from app import ConfigStore, Controller
from theme import apply_hud, HUD_DEFAULTS


app = QApplication([])
with TemporaryDirectory() as temp:
    store = ConfigStore(Path(temp))
    store.data["weather_location"] = {
        "name": "重庆 · 重庆市 · 中国", "latitude": 29.56, "longitude": 106.55,
        "timezone": "Asia/Shanghai",
    }
    store.data["weather_cache"] = {"fetched_at": 1790556656, "data": {
        "current": {"temperature_2m": 24.6, "relative_humidity_2m": 95,
                    "weather_code": 61, "wind_speed_10m": .6},
        "daily": {"time": ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"],
                  "temperature_2m_max": [28, 27, 26, 25], "temperature_2m_min": [24, 23, 22, 21],
                  "precipitation_probability_max": [71, 60, 50, 40], "weather_code": [95, 61, 3, 0]},
    }}
    controller = Controller(app, store, enable_hotkeys=False)
    calls = []
    controller.weather.fetch = lambda *args: calls.append(args)
    pane = controller.center.weather
    center = controller.center
    center.centralWidget().setCurrentWidget(center.weather)
    center.show()
    QTest.qWait(40)
    assert not pane.location_editor.isVisible()
    assert not pane.city.isVisible()
    assert pane.days.count() == 4
    assert all(pane.days.viewport().rect().contains(pane.days.visualItemRect(pane.days.item(i)))
               for i in range(4))
    metrics = {"window_height": center.height(), "forecast_viewport_height": pane.days.viewport().height(),
               "row_height": pane.days.visualItemRect(pane.days.item(0)).height()}
    assert metrics["forecast_viewport_height"] > 250, metrics
    center.grab().save(str(Path(__file__).parent / "preview-0.5.12-weather.png"))

    first_id = store.data["weather_active_id"]
    pane.manage_button.click()
    QTest.qWait(20)
    assert pane.location_editor.isVisible() and pane.city.isVisible()
    pane.location_editor.grab().save(str(Path(__file__).parent / "preview-0.5.12-weather-regions.png"))
    labels = [{"name": "香港", "latitude": 22.3, "longitude": 114.2, "country": "中国"}]
    with patch.object(QInputDialog, "getItem", return_value=("香港 ·  · 中国", True)):
        pane.choose_location(labels)
    second_id = store.data["weather_active_id"]
    assert second_id != first_id and len(pane.saved_locations) == 2
    assert pane.locations_combo.currentData() == pane.manage_combo.currentData() == second_id
    assert calls[-1][-1] == second_id
    pane.manage_combo.setCurrentIndex(pane.manage_combo.findData(first_id))
    assert store.data["weather_active_id"] == first_id
    assert pane.days.count() == 4  # previously cached region appears immediately
    pane.manage_combo.setCurrentIndex(pane.manage_combo.findData(second_id))
    pane.remove_location()
    assert len(pane.saved_locations) == 1 and store.data["weather_active_id"] == first_id
    pane.location_editor.reject()

    center.resize(720, 580)
    apply_hud(app, {**HUD_DEFAULTS, "font_size": 16})
    QTest.qWait(60)
    assert all(pane.days.viewport().rect().contains(pane.days.visualItemRect(pane.days.item(i)))
               for i in range(4)), (pane.days.viewport().height(), pane.days.visualItemRect(pane.days.item(0)))
    center.grab().save(str(Path(__file__).parent / "preview-0.5.12-weather-large-font.png"))
    controller.center.music.bridge.close()
    controller.events.close()
    center.hide()
print(json.dumps(metrics))
print("four-day forecast visible, region editor, cache switching and large font passed")
