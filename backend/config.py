from pathlib import Path
import os
import json
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
if getattr(sys, "frozen", False):
    LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    ROOT = LOCAL_APP_DATA / "Universal Converter"
else:
    ROOT = SOURCE_ROOT
STORAGE = ROOT / "storage"
UPLOADS = STORAGE / "uploads"
CONVERTED = STORAGE / "converted"
HOSTED = STORAGE / "hosted"
TEMP = STORAGE / "temp"
DATABASE = ROOT / "database"
DATABASE.mkdir(parents=True, exist_ok=True)
for directory in (STORAGE, UPLOADS, CONVERTED, HOSTED, TEMP):
    directory.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("UC_HOST", "127.0.0.1")
PORT = int(os.getenv("UC_PORT", "8765"))
MAX_UPLOAD_SIZE = int(os.getenv("UC_MAX_UPLOAD_SIZE", str(2 * 1024 * 1024 * 1024)))
API_KEY = os.getenv("UC_API_KEY", "")

CONFIG_DIR = ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "settings.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "max_upload_size": MAX_UPLOAD_SIZE,
    "api_key": API_KEY,
    "worker_count": int(os.getenv("UC_WORKER_COUNT", "2")),
    "cleanup_enabled": True,
    "cleanup_days": 7,
}


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    if CONFIG_FILE.exists():
        try:
            stored = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                settings.update(stored)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict):
    valid = {key: settings[key] for key in DEFAULT_SETTINGS if key in settings}
    CONFIG_FILE.write_text(json.dumps(valid, ensure_ascii=False, indent=2), encoding="utf-8")


_runtime_settings = load_settings()
MAX_UPLOAD_SIZE = int(_runtime_settings["max_upload_size"])
API_KEY = str(_runtime_settings["api_key"] or "")
