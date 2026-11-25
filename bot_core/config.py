import os
import json
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
BOT_CORE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
SCRIPTS_DIR = BASE_DIR / "gtavi-claudecode" / "scripts" if (BASE_DIR / "gtavi-claudecode" / "scripts").exists() else BASE_DIR / "scripts"
JOBS_DIR = BASE_DIR / "jobs"
DATA_DIR = BASE_DIR / "data"

JOBS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = BOT_CORE_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
    "gemini_model": "gemini-3.5-flash-lite",
    "morning_briefing_time": "08:30",
    "evening_briefing_time": "21:00",
    "auto_clean_hours": 24
}

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)

def save_settings(data):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

SETTINGS = load_settings()
TELEGRAM_BOT_TOKEN = SETTINGS.get("telegram_bot_token")
TELEGRAM_CHAT_ID = str(SETTINGS.get("telegram_chat_id"))
GEMINI_API_KEY = SETTINGS.get("gemini_api_key")
GEMINI_MODEL = SETTINGS.get("gemini_model", "gemini-3.5-flash-lite")
