"""Send a finished vertical clip + 1-tap copyable caption directly to Telegram.

Usage:
    python send_to_telegram.py <video_path> --caption "Caption text #hashtags" [--credit "@Creator"]
"""
import argparse
import html
import os
import sys
from pathlib import Path
import requests

try:
    from local_secrets import TELEGRAM_BOT_TOKEN as _LOCAL_TOKEN, TELEGRAM_CHAT_ID as _LOCAL_CHAT_ID
except ImportError:
    _LOCAL_TOKEN = ""
    _LOCAL_CHAT_ID = ""

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or _LOCAL_TOKEN
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _LOCAL_CHAT_ID


def send_clip(video_path: Path, caption: str, credit: str = "") -> bool:
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")

    copy_text = f"{caption.strip()}\n\nCredit: {credit.strip()}".strip() if credit else caption.strip()
    msg_caption = f"📋 <b>1-Tap Copy Caption:</b>\n<code>{html.escape(copy_text)}</code>"
    if len(msg_caption) > 1024:
        msg_caption = msg_caption[:1010] + "...</code>"

    url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
    with open(video_path, "rb") as vf:
        r = requests.post(
            url,
            data={"chat_id": CHAT_ID, "caption": msg_caption, "parse_mode": "HTML"},
            files={"video": vf},
            timeout=180,
        )
    res = r.json()
    if not res.get("ok"):
        print(f"sendVideo failed: {res}", file=sys.stderr)
        return False
    print(f"Sent {video_path.name} to Telegram chat {CHAT_ID}")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--caption", required=True)
    ap.add_argument("--credit", default="")
    args = ap.parse_args()
    if not send_clip(args.video, args.caption, args.credit):
        sys.exit(1)
