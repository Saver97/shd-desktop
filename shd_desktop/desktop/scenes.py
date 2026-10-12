"""Named snapshots of desktop panel and widget layout."""

from __future__ import annotations

import uuid


PANEL_FIELDS = ("x", "y", "w", "h", "expanded_h", "collapsed", "hidden")
WIDGET_FIELDS = ("x", "y", "w", "h", "hidden")


class SceneStore:
    def __init__(self, store):
        self.store = store
        scenes = store.data.setdefault("scenes", [])
        if not scenes:
            scene = {"id": uuid.uuid4().hex, "name": "日常"}
            scenes.append(scene)
            store.data["active_scene"] = scene["id"]
            self.capture(scene)
        elif not self.active():
            store.data["active_scene"] = scenes[0]["id"]
        store.save()

    def active(self) -> dict | None:
        scene_id = self.store.data.get("active_scene")
        return next((scene for scene in self.store.data.get("scenes", [])
                     if scene.get("id") == scene_id), None)

    def capture(self, scene: dict | None = None) -> None:
        scene = scene or self.active()
        if scene is None:
            return
        scene["panels"] = {
            p["id"]: {field: p[field] for field in PANEL_FIELDS if field in p}
            for p in self.store.data.get("panels", []) if isinstance(p, dict) and p.get("id")}
        scene["widgets"] = {
            kind: {field: config[field] for field in WIDGET_FIELDS if field in config}
            for kind, config in self.store.data.get("widgets", {}).items()
            if isinstance(config, dict)}
        launcher = self.store.data.get("isac_launcher", {})
        scene["isac_launcher"] = {key: launcher[key] for key in ("x", "y", "hidden")
                                  if key in launcher}
        self.store.save()

    def create(self, name: str) -> dict:
        self.capture()
        scene = {"id": uuid.uuid4().hex, "name": name.strip()}
        self.store.data["scenes"].append(scene)
        self.capture(scene)
        self.store.data["active_scene"] = scene["id"]
        self.store.save()
        return scene

    def switch(self, scene_id: str) -> dict:
        target = next((s for s in self.store.data["scenes"] if s["id"] == scene_id), None)
        if target is None:
            raise KeyError(scene_id)
        if self.store.data.get("active_scene") == scene_id:
            return target
        self.capture()
        for panel in self.store.data.get("panels", []):
            if not isinstance(panel, dict) or not panel.get("id"):
                continue
            values = target.get("panels", {}).get(panel["id"])
            if values is None:
                panel["hidden"] = True
            else:
                panel.update({key: value for key, value in values.items() if key in PANEL_FIELDS})
                panel["hidden"] = bool(values.get("hidden", False))
        for kind, config in self.store.data.get("widgets", {}).items():
            values = target.get("widgets", {}).get(kind)
            if values is not None:
                config.update({key: value for key, value in values.items() if key in WIDGET_FIELDS})
                config["hidden"] = bool(values.get("hidden", False))
        launcher = self.store.data.setdefault("isac_launcher", {})
        launcher.update(target.get("isac_launcher", {}))
        launcher["hidden"] = bool(target.get("isac_launcher", {}).get("hidden", False))
        self.store.data["active_scene"] = scene_id
        self.store.save()
        return target

    def delete(self, scene_id: str) -> bool:
        scenes = self.store.data["scenes"]
        if len(scenes) < 2:
            return False
        target = next((scene for scene in scenes if scene["id"] == scene_id), None)
        if target is None or target is self.active():
            return False
        scenes.remove(target)
        self.store.save()
        return True
