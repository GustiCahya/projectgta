"""Send a finished vertical clip + 1-tap copyable caption directly to Telegram.
Supports 1-tap copy song title, artist, audio start minute (slider position),
and sending as uncompressed document to prevent quality loss.

Usage:
    python send_to_telegram.py <video_path> --caption "Caption text #hashtags" [--credit "@Creator"]
                                [--song-title "Title"] [--artist "Artist"] [--song-start "00:45"]
                                [--campaign-url "https://..."] [--document]
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


def send_clip(
    video_path: Path,
    caption: str,
    credit: str = "",
    song_title: str = "",
    artist: str = "",
    song_start: str = "",
    campaign_url: str = "",
    as_document: bool = False,
    guide_text: str = ""
) -> bool:
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")

    copy_text = f"{caption.strip()}\n\nCredit: {credit.strip()}".strip() if credit else caption.strip()
    msg_caption = f"📋 <b>1-Tap Copy Caption:</b>\n<code>{html.escape(copy_text)}</code>"

    music_lines = []
    if song_title:
        music_lines.append(f"• Judul Lagu (1-Tap): <code>{html.escape(song_title.strip())}</code>")
    if artist:
        music_lines.append(f"• Penyanyi (1-Tap): <code>{html.escape(artist.strip())}</code>")
    if song_start:
        music_lines.append(f"• Menit di Video (Slider Audio): <code>{html.escape(song_start.strip())}</code>")

    if music_lines:
        msg_caption += "\n\n🎵 <b>Info Musik / Audio Wajib:</b>\n" + "\n".join(music_lines)

    followup_needed = False
    followup_text = ""

    if campaign_url:
        link_line = f"\n\n🔗 <b>Link Submit Campaign:</b>\n{campaign_url.strip()}"
        if len(msg_caption + link_line) <= 1024:
            msg_caption += link_line
        else:
            followup_needed = True
            followup_text += link_line.strip() + "\n\n"

    if guide_text:
        followup_needed = True
        followup_text += guide_text.strip()

    if len(msg_caption) > 1024:
        # Split caption if it exceeds Telegram 1024 char video limit
        msg_caption = f"📋 <b>1-Tap Copy Caption:</b>\n<code>{html.escape(copy_text)}</code>"
        followup_needed = True
        music_guide = "\n🎵 <b>Info Musik / Audio Wajib:</b>\n" + "\n".join(music_lines) if music_lines else ""
        followup_text = music_guide + ("\n\n" + followup_text if followup_text else "")

    endpoint = "sendDocument" if as_document else "sendVideo"
    file_field = "document" if as_document else "video"
    url = f"https://api.telegram.org/bot{TOKEN}/{endpoint}"

    with open(video_path, "rb") as vf:
        payload = {"chat_id": CHAT_ID, "caption": msg_caption, "parse_mode": "HTML"}
        if not as_document:
            payload["supports_streaming"] = "true"
        r = requests.post(url, data=payload, files={file_field: vf}, timeout=180)

    res = r.json()
    if not res.get("ok"):
        print(f"{endpoint} failed: {res}", file=sys.stderr)
        return False

    print(f"Sent {video_path.name} via {endpoint} to Telegram chat {CHAT_ID}")

    if followup_needed and followup_text.strip():
        r_msg = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": followup_text.strip(),
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=30
        )
        if not r_msg.json().get("ok"):
            print(f"sendMessage followup failed: {r_msg.text}", file=sys.stderr)

    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--caption", required=True)
    ap.add_argument("--credit", default="")
    ap.add_argument("--song-title", default="", help="Judul lagu (1-tap copyable)")
    ap.add_argument("--artist", default="", help="Penyanyi / artis lagu (1-tap copyable)")
    ap.add_argument("--song-start", default="", help="Menit/detik audio dimulai pada video (posisi slider TikTok/Reels)")
    ap.add_argument("--campaign-url", default="", help="Link submit campaign ContentRewards/Whop")
    ap.add_argument("--guide", default="", help="Teks panduan tambahan")
    ap.add_argument("--document", action="store_true", help="Kirim sebagai file dokumen asli tanpa kompresi")
    args = ap.parse_args()

    success = send_clip(
        video_path=args.video,
        caption=args.caption,
        credit=args.credit,
        song_title=args.song_title,
        artist=args.artist,
        song_start=args.song_start,
        campaign_url=args.campaign_url,
        as_document=args.document,
        guide_text=args.guide
    )
    if not success:
        sys.exit(1)
