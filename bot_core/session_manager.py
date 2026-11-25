import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from bot_core.config import BASE_DIR

STATE_FILE = BASE_DIR / "session_state.json"
HISTORY_FILE = BASE_DIR / "session_history.json"

class SessionManager:
    def __init__(self):
        self.state_file = STATE_FILE
        self.history_file = HISTORY_FILE
        self.sessions: Dict[str, Dict[str, Any]] = self._load_state()
        self.history: Dict[str, List[Dict[str, str]]] = self._load_history()

    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_state(self):
        try:
            self.state_file.write_text(json.dumps(self.sessions, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[SessionManager save_state error]: {e}")

    def _load_history(self) -> Dict[str, List[Dict[str, str]]]:
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_history(self):
        try:
            self.history_file.write_text(json.dumps(self.history, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[SessionManager save_history error]: {e}")

    def get_state(self, chat_id: str) -> Dict[str, Any]:
        cid = str(chat_id)
        if cid not in self.sessions:
            self.sessions[cid] = {
                "action": "IDLE",
                "last_intent": None,
                "target_streamer": None,
                "pending_data": {},
                "updated_at": time.time()
            }
        return self.sessions[cid]

    def set_action(self, chat_id: str, action: str, data: Optional[Dict[str, Any]] = None):
        cid = str(chat_id)
        st = self.get_state(cid)
        st["action"] = action
        if data:
            st["pending_data"].update(data)
        st["updated_at"] = time.time()
        self._save_state()

    def clear_action(self, chat_id: str):
        cid = str(chat_id)
        st = self.get_state(cid)
        st["action"] = "IDLE"
        st["pending_data"] = {}
        st["updated_at"] = time.time()
        self._save_state()

    def add_history(self, chat_id: str, role: str, content: str):
        cid = str(chat_id)
        if not content or not content.strip():
            return
        if cid not in self.history:
            self.history[cid] = []
        self.history[cid].append({
            "role": role,
            "content": content.strip(),
            "timestamp": time.time()
        })
        # Keep last 20 messages for context
        if len(self.history[cid]) > 20:
            self.history[cid] = self.history[cid][-20:]
        self._save_history()

    def get_recent_history(self, chat_id: str, limit: int = 10) -> List[Dict[str, str]]:
        cid = str(chat_id)
        return self.history.get(cid, [])[-limit:]
