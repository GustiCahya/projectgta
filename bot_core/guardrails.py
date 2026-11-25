import os
import re
import html
import shutil
import threading
from pathlib import Path
from typing import Tuple, List, Optional, Any
from bot_core.config import BASE_DIR, JOBS_DIR
from bot_core.pipeline import cleanup_raw_media

# Blacklisted terms that trigger platform bans or Whop bounty disqualification
BANNED_KEYWORDS = [
    "leak", "leaked build", "source code", "play early", "early access download",
    "free download", "crack", "piracy", "mod menu", "money glitch", "afk bot",
    "scam", "cheat engine", "trojan", "stealer"
]

class ConcurrencyGuard:
    """
    Prevents multiple heavy rendering/Whisper tasks from executing at once
    to prevent VPS CPU/RAM OOM (Out Of Memory) crashes.
    """
    _lock = threading.Lock()
    _active_job: Optional[str] = None

    @classmethod
    def try_acquire(cls, job_name: str) -> bool:
        acquired = cls._lock.acquire(blocking=False)
        if acquired:
            cls._active_job = job_name
            return True
        return False

    @classmethod
    def release(cls):
        cls._active_job = None
        try:
            cls._lock.release()
        except RuntimeError:
            pass

    @classmethod
    def is_busy(cls) -> bool:
        return cls._active_job is not None

    @classmethod
    def current_job(cls) -> str:
        return cls._active_job or "Tidak ada"


def check_and_enforce_disk_space(min_free_gb: float = 2.0) -> Tuple[bool, str]:
    """
    Guardrail: Checks available VPS disk space.
    If below min_free_gb, automatically purges raw media older than 1 hour.
    If still below 1.0 GB, returns False to prevent disk-full crashes.
    """
    try:
        stat = shutil.disk_usage(str(BASE_DIR))
        free_gb = stat.free / (1024 ** 3)
        
        if free_gb < min_free_gb:
            # Emergency purge old raw downloads
            freed = cleanup_raw_media(keep_hours=1)
            # Recheck
            stat = shutil.disk_usage(str(BASE_DIR))
            free_gb = stat.free / (1024 ** 3)
            if free_gb < 1.0:
                return False, f"Penyimpanan VPS kritis! Sisa {free_gb:.2f} GB (Minimal butuh 1.0 GB). Harap bersihkan file jobs lama."
            return True, f"Penyimpanan dibersihkan ({freed:.1f} MB freed). Sisa {free_gb:.2f} GB."
            
        return True, f"Sisa penyimpanan aman: {free_gb:.2f} GB."
    except Exception as e:
        return True, f"Gagal mengecek disk: {e}"


def sanitize_input(text: str, max_len: int = 150) -> str:
    """
    Guardrail: Strips shell control characters, command injection patterns,
    and limits string length.
    """
    if not text:
        return ""
    # Strip dangerous shell characters
    cleaned = re.sub(r"[;&|`$<>\r\n\t]", " ", text)
    # Collapse extra whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def safe_html(text: Any) -> str:
    """
    Guardrail: Safely escapes text so Telegram HTML parse_mode
    never throws '400 Bad Request: can't parse entities'.
    """
    if text is None:
        return ""
    s = str(text)
    return html.escape(s, quote=False)


def validate_content_safety(text: str) -> Tuple[bool, List[str]]:
    """
    Guardrail: Scans text (titles, transcript, hooks) for banned terms,
    copyright-risky leaks, and TOS violations.
    """
    if not text:
        return True, []
    low = text.lower()
    violations = [kw for kw in BANNED_KEYWORDS if kw in low]
    is_safe = len(violations) == 0
    return is_safe, violations


def check_video_duration_limit(duration_seconds: float, max_minutes: float = 45.0) -> Tuple[bool, str]:
    """
    Guardrail removed: Long videos and live stream VODs are automatically sliced
    by moments.py via --download-sections without downloading the entire file.
    """
    return True, "Durasi diizinkan (auto-slice aktif)"
