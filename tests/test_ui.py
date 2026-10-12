"""Offscreen regression for desktop frames, ISAC pinning, and model settings."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QToolButton

from app import ConfigStore, Controller, ICON_DIR
from shd_desktop.ui.theme import STYLE


app = QApplication([])
app.setStyleSheet(STYLE)
with TemporaryDirectory() as temp:
    store = ConfigStore(Path(temp))
    store.data["weather_location"] = {"name": "香港", "latitude": 22.3,
                                      "longitude": 114.2, "timezone": "Asia/Hong_Kong"}
    store.data["weather_cache"] = {"fetched_at": 1790460000, "data": {
        "current": {"temperature_2m": 27, "relative_humidity_2m": 72,
                    "weather_code": 2, "wind_speed_10m": 14},
        "daily": {"time": ["2026-09-27", "2026-09-28"],
                  "temperature_2m_max": [29, 30], "temperature_2m_min": [24, 25],
                  "precipitation_probability_max": [30, 55], "weather_code": [2, 61]},
    }}
    controller = Controller(app, store)
    opened = []
    controller.open_center = lambda: opened.append(True)
    controller.on_tray_activated(QSystemTrayIcon.Context)
    assert not opened
    controller.on_tray_activated(QSystemTrayIcon.Trigger)
    assert len(opened) == 1
    controller.llm.profiles.active()["model"] = "example-model-42"
    controller.llm.profiles.active()["models"].append("example-model-42")
    controller.llm.profile_changed.emit()
    app.processEvents()
    assert "example-model-42" in controller.chat.model_button.text()
    second_profile = controller.llm.profiles.add()
    controller.llm.profiles.update(second_profile["id"], name="第二配置", mode="chat",
                                   base_url="https://api.openai.com/v1", model="second-model")
    controller.llm.profile_changed.emit()
    app.processEvents()
    controller.chat.model_menu.actions()[1].menu().actions()[0].trigger()
    app.processEvents()
    assert controller.llm.profiles.active()["id"] == second_profile["id"]
    assert controller.llm.profiles.active()["model"] == "second-model"
    controller.chat.append_message("你", "发言者测试")
    controller.chat.append_message("ISAC", "回复测试")
    assert "你" in controller.chat.log.toPlainText()
    assert "ISAC" in controller.chat.log.toPlainText()
    folder = next(iter(controller.panels.values()))
    assert folder.view_action.text() == "切到列表"
    folder.view_action.trigger()
    assert folder.view_action.text() == "切到图标"
    folder.toggle_view()
    folder.close_panel()
    assert folder.config["hidden"] and not folder.isVisible()
    assert len(controller.panels) == 1
    controller.show_all()
    assert not folder.config["hidden"] and folder.isVisible()
    controller.set_widget_visible("weather", False)
    assert controller.widgets["weather"].config["hidden"]
    assert not controller.widgets["weather"].isVisible()
    assert ConfigStore(Path(temp)).data["widgets"]["weather"]["hidden"]
    controller.populate_tray_menu()
    components = next(action.menu() for action in controller.tray_menu.actions()
                      if action.text() == "桌面组件")
    weather_action = next(action for action in components.actions() if action.text() == "天气")
    assert not weather_action.isChecked()
    weather_action.trigger()
    assert controller.widgets["weather"].isVisible()
    assert not controller.widgets["weather"].config["hidden"]
    settings = next(button.menu() for button in controller.center.findChildren(QToolButton)
                    if button.text() == "设置")
    settings_components = next(action.menu() for action in settings.actions()
                               if action.text() == "桌面组件")
    settings_components.aboutToShow.emit()
    settings_weather = next(action for action in settings_components.actions()
                            if action.text() == "天气")
    assert settings_weather.isChecked()
    settings_weather.trigger()
    assert controller.widgets["weather"].config["hidden"]
    controller.show_all()
    controller.widgets["weather"].open_feature()
    assert controller.center.tabs.currentWidget() is controller.center.weather
    previous = folder.height()
    folder.toggle_collapsed()
    assert folder.config["collapsed"] and folder.height() == 55
    assert folder.collapse_button.text() == "展开" and folder.list.isHidden()
    assert folder.manage_button.isVisible()
    folder.toggle_collapsed()
    assert not folder.config["collapsed"] and folder.height() >= previous
    assert folder.collapse_button.text() == "折叠" and not folder.list.isHidden()
    assert len(folder.panel_menu.actions()) >= 6
    second_folder = Path(temp) / "Work"
    second_folder.mkdir()
    controller.add_folder(second_folder, "工作", "cat-logistics-gen-64.png")
    assert len(controller.panels) == 2
    assert any(panel.config.get("title") == "工作" for panel in controller.panels.values())
    controller.chat.show()
    controller.chat.toggle_pin()
    assert controller.chat.pinned and controller.chat.config["pinned"]
    controller.chat.toggle_pin()
    assert not controller.chat.pinned
    controller.center.show()
    controller.settings.show()
    app.processEvents()
    assert controller.center.centralWidget().count() == 4
    assert controller.settings.profile_list.count() >= 1
    assert len(list(ICON_DIR.glob("*-gen-64.png"))) == 20
    outputs = Path(__file__).resolve().parent
    folder.grab().save(str(outputs / "preview-panel.png"))
    controller.center.centralWidget().setCurrentWidget(controller.center.weather)
    controller.center.grab().save(str(outputs / "preview-center.png"))
    controller.chat.grab().save(str(outputs / "preview-chat.png"))
    controller.settings.grab().save(str(outputs / "preview-settings.png"))
    controller.events.close()
print("desktop frames, ISAC pin, profiles, and 20 icons passed")
