"""Persistent LLM profiles and endpoint normalization."""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlsplit


def api_base(value: str) -> str:
    """Accept a service root, /v1 base, or a complete request endpoint."""
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("API 地址需要以 http:// 或 https:// 开头")
    for suffix in ("/chat/completions", "/responses", "/models"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value if value.endswith("/v1") else value + "/v1"


def endpoint(value: str, mode: str) -> str:
    return api_base(value) + ("/responses" if mode == "responses" else "/chat/completions")


class ProfileStore:
    def __init__(self, store, secret_class):
        self.store = store
        self.secret_class = secret_class
        profiles = store.data.get("llm_profiles")
        if not isinstance(profiles, list) or not profiles:
            old = store.data.get("llm", {})
            profiles = [{"id": uuid.uuid4().hex, "name": "默认配置", "mode": "chat",
                         "base_url": old.get("endpoint", "https://api.openai.com/v1"),
                         "model": old.get("model", ""), "models_url": "",
                         "secret_file": "llm-key.dpapi"}]
            store.data["llm_profiles"] = profiles
            store.data["active_llm_profile"] = profiles[0]["id"]
            self._save()
        self.profiles = profiles
        migrated = False
        for profile in self.profiles:
            names = profile.get("models")
            if not isinstance(names, list):
                names = []
            names = list(dict.fromkeys(str(name).strip() for name in names if str(name).strip()))
            current = str(profile.get("model") or "").strip()
            if current and current not in names:
                names.append(current)
            if profile.get("models") != names:
                profile["models"] = names
                migrated = True
            if not current and names:
                profile["model"] = names[0]
                migrated = True
        if migrated:
            self._save()
        if not self.get(store.data.get("active_llm_profile")):
            store.data["active_llm_profile"] = profiles[0]["id"]
            self._save()

    def _save(self):
        if hasattr(self.store, "save"):
            self.store.save()

    def get(self, profile_id: str | None) -> dict | None:
        return next((p for p in self.store.data["llm_profiles"] if p.get("id") == profile_id), None)

    def active(self) -> dict:
        return self.get(self.store.data.get("active_llm_profile")) or self.store.data["llm_profiles"][0]

    def activate(self, profile_id: str) -> None:
        if not self.get(profile_id):
            raise ValueError("模型配置不存在")
        self.store.data["active_llm_profile"] = profile_id
        self._save()

    def activate_model(self, profile_id: str, model: str) -> None:
        profile = self.get(profile_id)
        if not profile or model not in profile.get("models", []):
            raise ValueError("模型不在此配置的已保存列表中")
        profile["model"] = model
        self.store.data["active_llm_profile"] = profile_id
        self._save()

    def add(self, source: dict | None = None) -> dict:
        profile_id = uuid.uuid4().hex
        profile = {"id": profile_id, "name": "新配置", "mode": "chat",
                   "base_url": "https://api.openai.com/v1", "model": "", "models": [], "models_url": "",
                   "secret_file": f"llm-{profile_id}.dpapi"}
        if source:
            profile.update({key: source.get(key, profile[key]) for key in
                            ("name", "mode", "base_url", "model", "models_url")})
            profile["models"] = list(source.get("models", []))
            profile["name"] += " 副本"
        self.store.data["llm_profiles"].append(profile)
        self._save()
        return profile

    def update(self, profile_id: str, *, name: str, mode: str, base_url: str,
               model: str, models_url: str = "") -> dict:
        profile = self.get(profile_id)
        if not profile:
            raise ValueError("模型配置不存在")
        if mode not in ("chat", "responses"):
            raise ValueError("不支持的 API 模式")
        api_base(base_url)
        profile.update(name=name.strip() or "未命名", mode=mode,
                       base_url=base_url.strip(), model=model.strip(),
                       models_url=models_url.strip())
        if profile["model"] and profile["model"] not in profile["models"]:
            profile["models"].append(profile["model"])
        self._save()
        return profile

    def remove_model(self, profile_id: str, model: str) -> None:
        profile = self.get(profile_id)
        if not profile:
            raise ValueError("模型配置不存在")
        profile["models"] = [name for name in profile.get("models", []) if name != model]
        if profile.get("model") == model:
            profile["model"] = profile["models"][0] if profile["models"] else ""
        self._save()

    def remove(self, profile_id: str) -> None:
        if len(self.store.data["llm_profiles"]) <= 1:
            raise ValueError("至少保留一个模型配置")
        profile = self.get(profile_id)
        if not profile:
            return
        self.store.data["llm_profiles"] = [p for p in self.store.data["llm_profiles"] if p["id"] != profile_id]
        self.profiles = self.store.data["llm_profiles"]
        if self.store.data.get("active_llm_profile") == profile_id:
            self.store.data["active_llm_profile"] = self.profiles[0]["id"]
        self._save()
        secret = self.secret_path(profile)
        if secret.name != "llm-key.dpapi":
            secret.unlink(missing_ok=True)

    def secret_path(self, profile: dict) -> Path:
        return self.store.file.parent / profile.get("secret_file", f"llm-{profile['id']}.dpapi")

    def secret(self, profile: dict):
        return self.secret_class(self.secret_path(profile))
