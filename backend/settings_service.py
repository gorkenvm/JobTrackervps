import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULT = {
    "provider": "Gemini",
    "api_key": "",
    "model_name": "gemini-1.5-pro",
    "download_path": "",
    "summary_language": "TR",
    "user_code": "",
}


def load() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULT)


def save(data: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
