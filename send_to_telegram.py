"""Send a finished vertical clip + 1-tap copyable caption directly to Telegram.
Automatically sends both the inline playable preview (sendVideo) and the raw
uncompressed original MP4 file (sendDocument) so social uploads never lose quality.

Usage:
    python send_to_telegram.py <video_path> --caption "Caption text #hashtags" [--credit "@Creator"]
                                [--song-title "Title"] [--artist "Artist"] [--song-start "00:45"]
                                [--campaign-url "https://..."] [--no-document]
"""
import argparse
import html
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import requests
import urllib3.util.connection

# Force IPv4 so Windows dual-stack networks do not stall mid-upload on IPv6 TLS sockets
urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

try:
    from local_secrets import TELEGRAM_BOT_TOKEN as _LOCAL_TOKEN, TELEGRAM_CHAT_ID as _LOCAL_CHAT_ID
except ImportError:
    _LOCAL_TOKEN = ""
    _LOCAL_CHAT_ID = ""

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or _LOCAL_TOKEN
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _LOCAL_CHAT_ID


def _post_tg(endpoint: str, data: dict, file_path: Path = None, file_field: str = "", upload_name: str = ""):
    url = f"https://api.telegram.org/bot{TOKEN}/{endpoint}"
    for attempt in range(5):
        cap_tmp = None
        try:
            if file_path is not None:
                fname = upload_name or file_path.name
                cmd = [
                    "curl.exe", "-sS", "-4", "--http1.1",
                    "--max-time", "600", "--speed-limit", "2048", "--speed-time", "45",
                    "-w", "\n__STATS__:%{speed_upload}:%{time_total}",
                ]
                for k, v in data.items():
                    if k == "caption":
                        tf = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt")
                        tf.write(str(v))
                        tf.close()
                        cap_tmp = Path(tf.name)
                        cmd += ["-F", f"caption=<{cap_tmp}"]
                    else:
                        cmd += ["-F", f"{k}={v}"]
                cmd += ["-F", f"{file_field}=@{file_path.resolve()};filename={fname};type=video/mp4", url]
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if proc.returncode != 0:
                    raise RuntimeError(f"curl exit {proc.returncode}: {proc.stderr.strip()}")
                body, _, stats = proc.stdout.rpartition("\n__STATS__:")
                if stats.strip():
                    spd, _, dur = stats.strip().partition(":")
                    print(f"  [curl {endpoint}] {fname} -> {float(spd)/1024:.0f} KB/s in {float(dur):.1f}s")
                res = json.loads(body)
            else:
                r = requests.post(url, data=data, headers={"Connection": "close"}, timeout=30)
                res = r.json()
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            wait_s = 5 * (attempt + 1)
            print(f"Network/parse error on {endpoint} ({exc}), retrying in {wait_s}s...")
            time.sleep(wait_s)
            continue
        finally:
            if cap_tmp is not None:
                cap_tmp.unlink(missing_ok=True)
        if res.get("ok"):
            return res
        if res.get("error_code") == 429:
            wait_s = int((res.get("parameters") or {}).get("retry_after", 10)) + 1
            print(f"Telegram 429 on {endpoint}, waiting {wait_s}s...")
            time.sleep(wait_s)
            continue
        return res
    return {"ok": False, "description": "Max retries exceeded"}


def send_clip(
    video_path: Path,
    caption: str,
    credit: str = "",
    song_title: str = "",
    artist: str = "",
    song_start: str = "",
    campaign_url: str = "",
    as_document: bool = False,
    send_raw_document: bool = True,
    guide_text: str = "",
    preview_path: Path = None,
    send_preview: bool = True,
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
        msg_caption = f"📋 <b>1-Tap Copy Caption:</b>\n<code>{html.escape(copy_text)}</code>"
        followup_needed = True
        music_guide = "\n🎵 <b>Info Musik / Audio Wajib:</b>\n" + "\n".join(music_lines) if music_lines else ""
        followup_text = music_guide + ("\n\n" + followup_text if followup_text else "")

    endpoint = "sendDocument" if as_document else "sendVideo"
    file_field = "document" if as_document else "video"
    payload = {"chat_id": CHAT_ID, "caption": msg_caption, "parse_mode": "HTML"}
    if not as_document:
        payload["supports_streaming"] = "true"

    if send_preview:
        vid_src = preview_path if (not as_document and preview_path and preview_path.exists()) else video_path
        res = _post_tg(endpoint, payload, vid_src, file_field, upload_name=video_path.name)
        if not res.get("ok"):
            print(f"{endpoint} failed: {res}", file=sys.stderr)
            return False
        print(f"Sent {video_path.name} via {endpoint} to Telegram chat {CHAT_ID}")

    # Send raw uncompressed document right below preview so uploads to TikTok/IG never pixelate
    if not as_document and send_raw_document:
        doc_caption = (
            "📂 <b>File Master Asli (Tanpa Kompresi Telegram)</b>\n"
            "<i>Download/Simpan file ini untuk di-upload ke TikTok &amp; IG Reels agar gambar tajam &amp; tidak pecah!</i>"
        )
        res_doc = _post_tg(
            "sendDocument",
            {"chat_id": CHAT_ID, "caption": doc_caption, "parse_mode": "HTML"},
            video_path,
            "document",
            upload_name=video_path.name,
        )
        if not res_doc.get("ok"):
            print(f"sendDocument raw failed: {res_doc}", file=sys.stderr)
            return False
        print(f"Sent raw document {video_path.name} via sendDocument ok!")

    if followup_needed and followup_text.strip():
        res_msg = _post_tg("sendMessage", {
            "chat_id": CHAT_ID,
            "text": followup_text.strip(),
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        })
        if not res_msg.get("ok"):
            print(f"sendMessage followup failed: {res_msg}", file=sys.stderr)
            return False

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
    ap.add_argument("--document", action="store_true", help="Kirim HANYA sebagai dokumen (tanpa preview video)")
    ap.add_argument("--no-document", action="store_true", help="Jangan kirim salinan dokumen asli")
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
        send_raw_document=not args.no_document,
        guide_text=args.guide
    )
    if not success:
        sys.exit(1)
