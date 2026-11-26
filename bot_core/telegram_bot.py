import os
import re
import sys
import html
import json
import time
import requests
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from bot_core.config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BASE_DIR, DOCS_DIR, JOBS_DIR
)
from bot_core.graph import ask_co_founder
from bot_core.session_manager import SessionManager
from bot_core.pipeline import (
    scan_youtube_trends, extract_moments, render_vertical_clip,
    verify_clip, log_payout, find_top_video, generate_viral_hook,
    find_live_streams, translate_clip_subtitles
)
from bot_core.guardrails import (
    ConcurrencyGuard, check_and_enforce_disk_space, sanitize_input,
    safe_html, validate_content_safety, check_video_duration_limit
)

class GTACoFounderBot:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.allowed_chat_id = str(TELEGRAM_CHAT_ID)
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.last_update_id = 0
        self.running = False
        self.session_mgr = SessionManager()
        self.pending_states = {}  # chat_id -> state dict

    def send_message(self, chat_id: str, text: str, reply_markup: Optional[Dict] = None, parse_mode: str = "HTML") -> Optional[int]:
        def _plain(s: str) -> str:
            return html.unescape(re.sub(r"<[^>]+>", "", s))[:3500]
        try:
            send_text = text
            send_mode = parse_mode
            if len(send_text) > 3800:
                send_text = _plain(send_text) + "\n... [teks dipotong]"
                send_mode = ""
            payload = {
                "chat_id": str(chat_id),
                "text": send_text,
            }
            if send_mode:
                payload["parse_mode"] = send_mode
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
                
            r = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=20)
            res = r.json()
            if res.get("ok"):
                return res["result"]["message_id"]
            else:
                print(f"[Telegram error send_message]: {res}")
                # Fallback to stripped plain text on any HTML or length rejection
                payload["text"] = _plain(text)
                payload.pop("parse_mode", None)
                r2 = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=20)
                return r2.json().get("result", {}).get("message_id")
        except Exception as e:
            print(f"[Telegram exception send_message]: {e}")
        return None

    def download_file(self, file_id: str, dest_path: Path) -> bool:
        try:
            r = requests.get(f"{self.api_url}/getFile", params={"file_id": file_id}, timeout=20)
            res = r.json()
            if not res.get("ok"):
                return False
            file_path = res["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            r2 = requests.get(file_url, stream=True, timeout=120)
            if r2.status_code == 200:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as f:
                    for chunk in r2.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
        except Exception as e:
            print(f"[download_file error]: {e}")
        return False

    def send_video_card(self, chat_id: str, video_path: str, caption_text: str, credit: str = "", tags: str = "", job_id: str = "job", clip_name: str = "clip_1", song_title: str = "", artist: str = "", song_start: str = "", campaign_url: str = "") -> bool:
        path = Path(video_path)
        if not path.exists():
            self.send_message(chat_id, f"❌ File video tidak ditemukan di: {safe_html(video_path)}")
            return False

        credit_tag = credit if credit else "@ContentRewards"
        tag_str = tags.strip() if tags.strip() else "#GTA6 #GTAVI #GamingClips"
        full_caption_raw = f"{caption_text[:200]}\n\nCredit: {credit_tag}\n{tag_str}"

        music_block = ""
        music_lines = []
        if song_title:
            music_lines.append(f"• Judul Lagu (1-Tap): <code>{safe_html(song_title)}</code>")
        if artist:
            music_lines.append(f"• Penyanyi (1-Tap): <code>{safe_html(artist)}</code>")
        if song_start:
            music_lines.append(f"• Menit di Video (Slider Audio): <code>{safe_html(song_start)}</code>")
        if music_lines:
            music_block = "\n\n🎵 <b>Info Musik / Audio Wajib:</b>\n" + "\n".join(music_lines)

        url_block = f"\n\n🔗 <b>Link Submit:</b> {campaign_url}" if campaign_url else ""

        html_caption = (
            f"🎬 <b>Klip Siap Posting!</b>\n\n"
            f"<i>Ketuk teks caption untuk langsung menyalin (1-Tap Copy):</i>\n\n"
            f"<code>{safe_html(full_caption_raw)}</code>"
            f"{music_block}"
            f"{url_block}\n\n"
            f"⚡ <i>Buka TikTok / Reels di HP, upload video ini, paste caption di atas!</i>"
        )
        if len(html_caption) > 1000:
            html_caption = f"🎬 <b>Klip Siap Posting!</b>\n\n<code>{safe_html(full_caption_raw[:700])}</code>{music_block}{url_block}"

        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Sudah Diposting (Catat Payout)", "callback_data": f"posted:{job_id}:{clip_name}"}
                ],
                [
                    {"text": "🔄 Ganti Hook / Re-Cut", "callback_data": f"recut:{job_id}"},
                    {"text": "🌐 Versi Indonesia (ID)", "callback_data": f"trans:{job_id}:{clip_name}:id"},
                    {"text": "🌐 Spanyol (ES)", "callback_data": f"trans:{job_id}:{clip_name}:es"}
                ]
            ]
        }

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > 49.0:
            self.send_message(chat_id, f"⚠️ Ukuran file {size_mb:.1f} MB mendekati batas Telegram 50MB; mengirim sebagai dokumen...")

        self.send_message(chat_id, f"🚀 <i>Mengirimkan video ({size_mb:.1f} MB) ke Telegram Anda...</i>")
        try:
            with open(path, "rb") as vf:
                data = {
                    "chat_id": str(chat_id),
                    "caption": html_caption,
                    "parse_mode": "HTML",
                    "supports_streaming": "true",
                    "reply_markup": json.dumps(inline_keyboard)
                }
                if size_mb <= 49.0:
                    r = requests.post(f"{self.api_url}/sendVideo", data=data, files={"video": vf}, timeout=240)
                    res = r.json()
                    if res.get("ok"):
                        # Also send uncompressed raw document so social media uploads don't pixelate
                        vf.seek(0)
                        doc_data = {
                            "chat_id": str(chat_id),
                            "caption": "📂 <b>File Master Asli (Tanpa Kompresi Telegram)</b>\n<i>Download file ini untuk upload ke TikTok / Reels agar kualitas tetap tajam &amp; tidak pecah!</i>",
                            "parse_mode": "HTML"
                        }
                        requests.post(f"{self.api_url}/sendDocument", data=doc_data, files={"document": vf}, timeout=240)
                        return True
                    print(f"[Telegram sendVideo failed]: {res}")
                    vf.seek(0)
                r2 = requests.post(f"{self.api_url}/sendDocument", data=data, files={"document": vf}, timeout=240)
                res2 = r2.json()
                if not res2.get("ok"):
                    print(f"[Telegram sendDocument failed]: {res2}")
                    self.send_message(chat_id, f"⚠️ Telegram menolak unggahan video: {safe_html(str(res2.get('description', 'error'))[:200])}")
                return res2.get("ok", False)
        except Exception as e:
            print(f"[Telegram exception sendVideo]: {e}")
            self.send_message(chat_id, f"⚠️ Gagal mengirim video via Telegram: {safe_html(str(e)[:200])}")
            return False

    def get_main_keyboard(self) -> Dict[str, Any]:
        return {
            "keyboard": [
                [{"text": "🔥 Tren GTA Hari Ini"}, {"text": "🔴 Live Streams"}],
                [{"text": "🎬 Klip Reaksi Windah"}, {"text": "⚡ Buat Klip IShowSpeed"}],
                [{"text": "💰 Cek Kampanye Whop"}, {"text": "📊 Rekap Payouts"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }

    # --- HANDLERS ---

    def handle_message(self, message: Dict[str, Any]):
        chat_id = str(message.get("chat", {}).get("id"))
        raw_text = (message.get("text") or message.get("caption") or "").strip()
        user_name = safe_html(message.get("from", {}).get("first_name", "Partner"))

        # Security check: only owner can talk to co-founder
        if self.allowed_chat_id and chat_id != self.allowed_chat_id:
            self.send_message(chat_id, "🔒 Akses ditolak. Bot ini diprivatisasi khusus untuk Co-Founder.")
            return

        # Handle Document uploads (e.g. cookies.txt or video file)
        if "document" in message:
            doc = message["document"]
            doc_name = doc.get("file_name", "").lower()
            if "cookie" in doc_name and doc_name.endswith((".txt", ".json")):
                dest = BASE_DIR / "cookies.txt"
                self.send_message(chat_id, "📥 <i>Menerima file cookies.txt... Memasang di sistem...</i>")
                if self.download_file(doc["file_id"], dest):
                    self.send_message(
                        chat_id,
                        "✅ <b>File cookies.txt Berhasil Terpasang!</b>\n\n"
                        "Mesin yt-dlp di VPS sekarang dapat mengunduh video YouTube langsung tanpa terblokir anti-bot."
                    )
                else:
                    self.send_message(chat_id, "❌ Gagal mengunduh file cookies.")
                return
            elif doc_name.endswith((".mp4", ".mov", ".mkv", ".avi", ".webm")):
                self.send_message(chat_id, f"📥 <i>Menerima video '{safe_html(doc_name)}'... Mulai memproses di VPS...</i>")
                threading.Thread(target=self._process_uploaded_video, args=(chat_id, doc["file_id"], doc_name), daemon=True).start()
                return

        # Handle Video uploads directly
        if "video" in message:
            vid = message["video"]
            self.send_message(chat_id, "📥 <i>Menerima video dari Telegram... Mulai memproses di VPS...</i>")
            threading.Thread(target=self._process_uploaded_video, args=(chat_id, vid["file_id"], "video_input.mp4"), daemon=True).start()
            return

        # Sanitize text
        text = sanitize_input(raw_text)
        if not text:
            return

        print(f"[Telegram IN] from {chat_id}: {text[:80]}")

        # Save message in session history
        self.session_mgr.add_history(chat_id, "user", text)
        curr_state = self.session_mgr.get_state(chat_id)
        tl = text.lower()

        # Check pending interactive states (URL input or payout view input)
        state = self.pending_states.get(chat_id)
        if state:
            st_type = state.get("type")
            if st_type == "await_clip_url":
                del self.pending_states[chat_id]
                self.send_message(chat_id, f"⚡ <i>Siap Bro! Sedang menganalisis VOD & mendeteksi momen terbaik dari:</i>\n<code>{safe_html(text)}</code>")
                threading.Thread(target=self._process_url_clip, args=(chat_id, text), daemon=True).start()
                return
            elif st_type == "await_payout_views":
                del self.pending_states[chat_id]
                camp = state.get("campaign", "Whop Pool")
                url = state.get("post_url", "https://tiktok.com/@clip")
                try:
                    views = int(text.replace(",", "").replace(".", "").replace("k", "000").replace("K", "000"))
                    log_payout(camp, "tiktok", url, views, rate_per_1k=1.0)
                    est = (views / 1000) * 1.0
                    self.send_message(chat_id, f"✅ <b>Klaim Tercatat!</b>\n\nKampanye: <b>{safe_html(camp)}</b>\nViews: <b>{views:,}</b>\nEstimasi Payout: <b>${est:.2f}</b>\nStatus: <i>Pending Review</i>")
                except Exception:
                    self.send_message(chat_id, "⚠️ Format angka tidak valid. Contoh ketik: <code>15000</code>")
                return

        # 1. Command /start
        if text.startswith("/start"):
            welcome = (
                f"👋 <b>Halo {user_name}! Alex di sini, Co-Founder Media GTA VI kamu.</b>\n\n"
                f"Gue udah siapin semua sistem di VPS ini lengkap dengan Guardrail keamanan:\n"
                f"🛡️ <b>Guardrail Aktif:</b> Anti-OOM Concurrency Lock, Auto-Purge Disk, Safe Area Validator, Content TOS Filter.\n\n"
                f"<i>Fokus kita jelas: Cashflow First! Produksi klip viral, submit ke bounty Whop/Clip.tech, dan bangun channel.</i>\n\n"
                f"Pilih menu di bawah atau ketik chat bebas apa aja (contoh: <i>'Buatin video clipping lucu ishowspeed'</i>)!"
            )
            self.send_message(chat_id, welcome, reply_markup=self.get_main_keyboard())
            return

        # 2. Button: Tren GTA Hari Ini
        if text == "🔥 Tren GTA Hari Ini":
            self.send_message(chat_id, "🔍 <i>Sedang memindai video GTA 6 trending di YouTube dengan velocity views tertinggi...</i>")
            try:
                trends = scan_youtube_trends(query="gta 6", hours=48, limit=5)
                if not trends:
                    self.send_message(chat_id, "Belum ada data tren baru, coba sesaat lagi.")
                    return
                msg = ["🔥 <b>Top 5 Video GTA 6 Paling Meledak (48 Jam Terakhir):</b>\n"]
                for t in trends:
                    tl = t['title_link']
                    url = ""
                    title = tl
                    if "[" in tl and "](" in tl and tl.endswith(")"):
                        title = tl[1:tl.rfind("](")]
                        url = tl[tl.rfind("](") + 2:-1]
                    link_html = f'<a href="{url}">{safe_html(title)}</a>' if url else safe_html(title)
                    msg.append(
                        f"• <b>#{safe_html(t['rank'])} {safe_html(t['channel'])}</b>\n"
                        f"  Judul: {link_html}\n"
                        f"  🚀 <b>{safe_html(t['views_per_hour'])} views/jam</b> (Total: {safe_html(t['views'])} views, Durasi: {safe_html(t['duration_min'])}m)\n"
                    )
                msg.append("💡 <i>Ketik /clip diikuti link video di atas jika mau langsung gua potongin!</i>")
                self.send_message(chat_id, "\n".join(msg))
            except Exception as e:
                self.send_message(chat_id, f"⚠️ Error memindai tren: {e}")
            return

        # Button: Live Streams (Skill: stream-finder)
        if text == "🔴 Live Streams":
            self.send_message(chat_id, "📡 <i>Memindai live stream GTA 6 aktif di YouTube dan Twitch (Skill: stream-finder)...</i>")
            try:
                streams = find_live_streams(query="gta 6", limit=5)
                if not streams:
                    self.send_message(chat_id, "Belum ada live stream besar aktif saat ini.")
                    return
                msg = ["🔴 <b>Live Stream GTA 6 Sedang Tayang:</b>\n"]
                for s in streams:
                    plat = s.get("platform", "stream").upper()
                    viewers = s.get("viewers", 0)
                    ch = s.get("channel", "Streamer")
                    tit = s.get("title", "")
                    u = s.get("url", "")
                    msg.append(f"• <b>[{plat}] {safe_html(ch)}</b> ({viewers:,} penonton)\n  {safe_html(tit[:60])}\n  👉 {u}\n")
                msg.append("💡 <i>Kirimkan link salah satu stream di atas untuk langsung dipotong momen serunya!</i>")
                self.send_message(chat_id, "\n".join(msg))
            except Exception as e:
                self.send_message(chat_id, f"⚠️ Error memindai stream: {e}")
            return

        # Button: Klip Reaksi Windah (Skill: twitch-reaction)
        if text == "🎬 Klip Reaksi Windah":
            streamer = "Windah Basudara"
            query = "windah basudara gta 6 gameplay lucu"
            layout = "react"
            self.session_mgr.set_action(chat_id, "processing_clip", {"target_streamer": streamer, "query": query, "layout": layout})
            self.send_message(
                chat_id,
                f"🚀 <b>Siap Bro! Alex langsung eksekusi klip reaksi Windah Basudara!</b>\n\n"
                f"🎯 <b>Target:</b> {safe_html(streamer)}\n"
                f"⚙️ <b>Layout:</b> Split-Screen Reaksi (Muka di atas + Game di bawah)\n"
                f"📝 <b>Subtitles:</b> Dynamic Word-by-Word Captions\n\n"
                f"⚡ <i>Mencari video VOD, mengekstrak momen puncak, dan merender di VPS...</i>"
            )
            threading.Thread(target=self._auto_clip_pipeline, args=(chat_id, query, layout, streamer), daemon=True).start()
            return

        # 3. Button: Potong Klip Baru
        if text == "🎬 Potong Klip Baru" or text.startswith("/clip"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1 and "http" in parts[1]:
                url = parts[1].strip()
                self.send_message(chat_id, f"⚡ <i>Mulai memproses video dari:</i>\n<code>{safe_html(url)}</code>")
                threading.Thread(target=self._process_url_clip, args=(chat_id, url), daemon=True).start()
            else:
                self.pending_states[chat_id] = {"type": "await_clip_url"}
                self.send_message(chat_id, "🎬 <b>Kirimkan link YouTube / Twitch VOD yang mau dipotong Bro!</b>\n\nAtau lu bisa langsung kirim/forward file video MP4 ke chat ini.")
            return

        # 3b. Re-cut with custom hook/title (/cut <job_id> --hook "TEXT")
        if text.startswith("/cut"):
            m_cmd = re.match(r"^/cut\s+([A-Za-z0-9_-]+)(?:\s+--hook\s+\"?(.+?)\"?)?$", raw_text.strip())
            if not m_cmd:
                self.send_message(chat_id, "Format: <code>/cut job_id --hook \"Judul Baru\"</code>")
                return
            jid = m_cmd.group(1)
            new_hook = (m_cmd.group(2) or "VIRAL GAMING MOMENT 💀").strip().strip('"')
            jdir = JOBS_DIR / jid
            if not jdir.exists() and (Path("/root/jobs") / jid).exists():
                jdir = Path("/root/jobs") / jid
            if not (jdir / "candidates.json").exists():
                self.send_message(chat_id, f"❌ Job <code>{safe_html(jid)}</code> tidak ditemukan.")
                return
            self.send_message(chat_id, f"🔄 <i>Re-cutting klip dengan hook baru:</i> <b>{safe_html(new_hook)}</b>")
            def _recut():
                if not ConcurrencyGuard.try_acquire(f"Recut {jid}"):
                    self.send_message(chat_id, "⏳ VPS sedang memproses render lain, coba sebentar lagi.")
                    return
                try:
                    mp4 = render_vertical_clip(jdir, pick=1, layout="react", hook=new_hook, title=new_hook, title_style="box", captions="word")
                    if mp4 and mp4.exists():
                        self.send_video_card(chat_id, str(mp4), new_hook, "@Streamer", job_id=jid, clip_name="clip_1")
                    else:
                        self.send_message(chat_id, "❌ Gagal me-render ulang video.")
                finally:
                    ConcurrencyGuard.release()
            threading.Thread(target=_recut, daemon=True).start()
            return

        # 4. Button: Cek Kampanye Whop
        if text == "💰 Cek Kampanye Whop":
            camp_file = DOCS_DIR / "campaigns.md"
            if camp_file.exists():
                txt = camp_file.read_text(encoding="utf-8")
                self.send_message(chat_id, f"💰 <b>Status Kampanye Paid Clipping Aktif:</b>\n\n<pre>{safe_html(txt[:1500])}</pre>")
            else:
                self.send_message(chat_id, "File campaigns.md belum tersedia.")
            return

        # 5. Button: Rekap Payouts
        if text == "📊 Rekap Payouts":
            payouts_file = BASE_DIR / "payouts.csv"
            if payouts_file.exists():
                lines = payouts_file.read_text(encoding="utf-8").splitlines()
                self.send_message(chat_id, f"📊 <b>Rekap Pembukuan Payouts:</b>\n\n<pre>{safe_html(chr(10).join(lines[-10:]))}</pre>")
            else:
                self.send_message(chat_id, "📊 Belum ada klaim payout tercatat di payouts.csv.")
            return

        # 6. Direct URL Detection
        if "youtube.com" in text or "youtu.be" in text or "twitch.tv" in text:
            words = text.split()
            url_target = next((w for w in words if "http" in w), text)
            self.send_message(chat_id, f"⚡ <i>Mulai memproses video dari:</i>\n<code>{safe_html(url_target)}</code>")
            threading.Thread(target=self._process_url_clip, args=(chat_id, url_target), daemon=True).start()
            return

        # 7. Check Confirmation / Resume Commands ("1", "lanjutkan", "gas", "ok", "eksekusi", "lanjutin bikin videonya")
        resume_keywords = [
            "1", "lanjutkan", "lanjut", "lanjutin", "terusin", "gas", "ok", "eksekusi", "sikat",
            "ya bikin contentnya", "bikin contentnya", "buat kontennya", "jalanin",
            "coba lagi", "retry", "ulang", "render ulang", "bisa lanjutin", "tolong fix", "fix ini",
            "lanjutkan prosesnya", "lanjutin prosesnya", "lanjutin bikin", "lanjutkan bikin",
            "bikin videonya", "buat videonya", "prosesnya"
        ]
        is_resume_cmd = any(cmd in tl for cmd in resume_keywords) and not any(kw in tl for kw in ["buat klip baru", "potong video baru", "cari video baru"])

        if is_resume_cmd:
            last_job = curr_state.get("pending_data", {}).get("job_dir")
            # If not in pending_data, find the most recent valid job in JOBS_DIR
            if not last_job or not (Path(last_job) / "candidates.json").exists() or not (Path(last_job) / "source.mp4").exists():
                recent_jobs = sorted(
                    [j for j in JOBS_DIR.glob("*-*") if j.is_dir() and (j / "candidates.json").exists() and (j / "source.mp4").exists()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                if recent_jobs:
                    last_job = str(recent_jobs[0])

            last_target = curr_state.get("target_streamer") or curr_state.get("pending_data", {}).get("target_streamer") or "Streamer"
            last_query = curr_state.get("pending_data", {}).get("query") or f"{last_target} funny moments"
            layout = "react"  # Streamer reaction layout: face on top, game on bottom (auto-fallback to blur if no face)

            if last_job and (Path(last_job) / "candidates.json").exists():
                self.send_message(
                    chat_id,
                    f"🚀 <b>Siap Bro! Melanjutkan dari checkpoint:</b>\n"
                    f"🎯 Target: <b>{safe_html(last_target)}</b>\n"
                    f"⚙️ Mode: 9:16 Vertikal + Subtitle Dinamis (Tanpa scan/download ulang!)"
                )
                self.session_mgr.set_action(chat_id, "processing_clip", {"target_streamer": last_target, "query": last_query, "job_dir": last_job, "layout": layout})
                threading.Thread(target=self._auto_clip_pipeline, args=(chat_id, last_query, layout, last_target, last_job), daemon=True).start()
                return

        # 8. Check Direct Clip Request ("ishowspeed", "speed", "clipping", "potong video", "bikin video", "buat video lucu")
        is_clip_req = any(kw in tl for kw in [
            "clipping", "klip", "clip", "potong", "bikin video", "buatin video", "buatkan video", "buat video",
            "ishowspeed", "speed", "streamer", "video lucu", "momen lucu", "buat klip ishowspeed", "trending di atas", "funny moment di atas"
        ])

        if is_clip_req or text == "⚡ Buat Klip IShowSpeed":
            # Determine target streamer and search query with full Indonesian NLP prefix support
            is_trend_target = any(k in tl for k in ["trending", "tren", "di atas", "populer", "radar", "salah satu"])
            
            if is_trend_target:
                streamer = "GTA 6 Trending"
                query = "trending gta 6 funny moments"
            elif "speed" in tl:
                streamer = "IShowSpeed"
                query = "ishowspeed gta 6 funny moments gameplay" if "gta" in tl else "ishowspeed funny moments highlights"
            elif "kai" in tl:
                streamer = "Kai Cenat"
                query = "kai cenat gta 6 funny moments"
            elif "windah" in tl:
                streamer = "Windah Basudara"
                query = "windah basudara gta 6 lucu"
            elif "tagback" in tl:
                streamer = "TagBackTV"
                query = "tagbacktv gta 6 secrets"
            else:
                clean_text = text
                for pfx in [
                    "buatin video clipping lucu dari", "buatin video clipping dari", "buatin video clipping", "buatin video clip",
                    "buatkan video clipping lucu dari", "buatkan video clipping dari", "buatkan video clipping", "buatkan video lucu dari", "buatkan video lucu", "buatkan video",
                    "buat klip video lucu dari", "buat klip video dari", "buat klip video", "buat klip", "buatin klip", "buatkan klip",
                    "bikin video clipping dari", "bikin video clipping", "bikin video lucu dari", "bikin video lucu", "bikin video", "bikin klip",
                    "potongin video dari", "potongin video", "potong video dari", "potong video", "potong klip",
                    "clipping video", "clipping"
                ]:
                    if clean_text.lower().startswith(pfx.lower()):
                        clean_text = clean_text[len(pfx):].strip()
                        break
                
                clean_target = clean_text.replace("dari", "").replace("lucu", "").replace("video", "").strip()
                streamer = clean_target.title() if clean_target else "GTA 6"
                query = f"{streamer} gta 6 funny moments" if "gta" not in streamer.lower() else f"{streamer} funny moments"

            layout = "react"  # Streamer reaction layout: face on top, game on bottom (auto-fallback to blur if no face)

            self.session_mgr.set_action(chat_id, "processing_clip", {"target_streamer": streamer, "query": query, "layout": layout})

            self.send_message(
                chat_id,
                f"🚀 <b>Siap Bro! Alex langsung eksekusi klip baru tanpa basa-basi!</b>\n\n"
                f"🎯 <b>Target:</b> {safe_html(streamer)}\n"
                f"🔍 <b>Topik:</b> <code>{safe_html(query)}</code>\n"
                f"⚙️ <b>Pipeline:</b> Scan VOD ➔ Whisper Transcribe ➔ 9:16 Vertical Subtitle\n\n"
                f"⚡ <i>Mencari video baru di YouTube dan memproses klip di VPS...</i>"
            )

            threading.Thread(target=self._auto_clip_pipeline, args=(chat_id, query, layout, streamer), daemon=True).start()
            return

        # 9. General Conversation with Co-Founder LangGraph
        self.send_message(chat_id, "🧠 <i>Alex sedang memikirkan strategi...</i>")
        try:
            recent_hist = self.session_mgr.get_recent_history(chat_id, limit=6)
            hist_objs = []
            for h in recent_hist:
                if h["role"] == "user":
                    hist_objs.append(HumanMessage(content=h["content"]))
                else:
                    hist_objs.append(AIMessage(content=h["content"]))

            # Inject checkpoint awareness to Co-Founder AI if available
            last_job = curr_state.get("pending_data", {}).get("job_dir")
            last_title = curr_state.get("pending_data", {}).get("video_title", "")
            if last_job and Path(last_job).exists():
                hist_objs.append(SystemMessage(content=f"[Context Server]: Video mentah & transkrip AI untuk '{last_title}' sudah siap di server (Job ID: {Path(last_job).name}). Jika user ingin melanjutkan proses render atau bikin videonya, sampaikan bahwa bahannya sudah siap dan mereka cukup ketik 'Lanjutkan' untuk langsung merender tanpa download ulang."))

            reply_text, clip_path = ask_co_founder(text, history=hist_objs)
            self.send_message(chat_id, reply_text)
            self.session_mgr.add_history(chat_id, "assistant", reply_text)
            
            if clip_path and Path(clip_path).exists():
                self.send_video_card(
                    chat_id=chat_id,
                    video_path=clip_path,
                    caption_text="Viral Gaming Moment!",
                    credit="@Streamer"
                )
        except Exception as e:
            self.send_message(chat_id, f"⚠️ Error AI: {safe_html(str(e))}")

    def handle_callback(self, callback_query: Dict[str, Any]):
        cq_id = callback_query.get("id")
        data = callback_query.get("data", "")
        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id"))
        
        try:
            requests.post(f"{self.api_url}/answerCallbackQuery", json={"callback_query_id": cq_id}, timeout=5)
        except Exception:
            pass

        if data.startswith("posted:"):
            parts = data.split(":")
            job_id = parts[1] if len(parts) > 1 else "job"
            clip_name = parts[2] if len(parts) > 2 else "clip_1"
            self.pending_states[chat_id] = {
                "type": "await_payout_views",
                "campaign": "Whop Gaming Bounty",
                "post_url": f"https://tiktok.com/@myclips/{job_id}"
            }
            self.send_message(chat_id, f"🎉 <b>Mantap Bro! Klip {safe_html(clip_name)} sudah tayang.</b>\n\nBerapa views yang sudah didapat sejauh ini? Ketik angkanya saja ya (misal: <code>25000</code>).")
        elif data.startswith("recut:"):
            job_id = data.split(":")[-1]
            self.send_message(chat_id, f"🔄 Mau diganti hook apa untuk job <code>{safe_html(job_id)}</code>? Ketik perintah: <code>/cut {safe_html(job_id)} --hook \"Judul Baru\"</code>")
        elif data.startswith("trans:"):
            parts = data.split(":")
            job_id, clip_name, lang = parts[1], parts[2], parts[3]
            pick_n = int(clip_name.split("_")[-1]) if "_" in clip_name and clip_name.split("_")[-1].isdigit() else 1
            job_dir = JOBS_DIR / job_id
            if not job_dir.exists() and (Path("/root/jobs") / job_id).exists():
                job_dir = Path("/root/jobs") / job_id
            self.send_message(chat_id, f"🌐 <i>Sedang menerjemahkan klip {safe_html(clip_name)} ke bahasa {safe_html(lang.upper())}...</i>")
            def _do_trans():
                if not ConcurrencyGuard.try_acquire(f"Trans {job_id}"):
                    self.send_message(chat_id, "⏳ VPS sedang memproses render lain, coba sebentar lagi.")
                    return
                try:
                    mp4 = translate_clip_subtitles(job_dir, pick=pick_n, langs=lang)
                    if mp4 and mp4.exists():
                        self.send_video_card(chat_id, str(mp4), f"Translated clip ({lang.upper()})", "@Streamer", job_id=job_id, clip_name=f"clip_{pick_n}_{lang}")
                    else:
                        self.send_message(chat_id, "❌ Gagal menerjemahkan klip.")
                finally:
                    ConcurrencyGuard.release()
            threading.Thread(target=_do_trans, daemon=True).start()

    def _render_and_deliver_best(
        self, chat_id: str, job_dir: Path, candidates: List[Dict[str, Any]],
        streamer_name: str, channel: str, video_title: str,
        query: str = "", layout: str = "react", allow_checkpoint: bool = False
    ) -> bool:
        """Selects safe exciting candidate, builds viral hook, renders 9:16 until complete, verifies SOP, and delivers."""
        best_cand = None
        cand_text = ""
        violations: List[str] = []
        for c in candidates:
            txt = (c.get("text") or "").strip()
            ok, viols = validate_content_safety(txt)
            if ok:
                best_cand = c
                cand_text = txt
                break
            violations = viols

        if not best_cand:
            self.send_message(
                chat_id,
                f"⚠️ <b>Guardrail Konten Aktif</b>\n\n"
                f"Momen terdeteksi memuat istilah terlarang/berisiko: <code>{safe_html(', '.join(violations))}</code>.\n"
                f"Dibatalkan demi keselamatan akun."
            )
            return False

        score = best_cand.get("score", 0)
        dur = int(best_cand.get("end", 0) - best_cand.get("start", 0))
        why_str = best_cand.get("why_ai") or ", ".join(best_cand.get("why", ["ekspresi seru"]))
        pick_n = int(best_cand.get("n", 1))
        hook, title = generate_viral_hook(streamer_name, cand_text, video_title, candidate=best_cand)

        self.send_message(
            chat_id,
            f"✂️ 3️⃣ <b>Momen Seru Terpilih!</b> (Skor: {score}, Durasi: {dur}s)\n"
            f"🎭 <b>Alasan:</b> {safe_html(why_str[:180])}\n"
            f"🏷️ <b>Judul Hook:</b> <i>{safe_html(title)}</i>\n"
            f"Transkrip: <i>\"{safe_html(cand_text[:100])}...\"</i>\n\n"
            f"⚙️ <i>Merender 1080x1920 (9:16) sampai tuntas (auto-facecam + subtitles)...</i>"
        )

        clip_file = render_vertical_clip(
            job_dir=job_dir,
            pick=pick_n,
            layout=layout,
            hook=hook,
            title=title,
            title_style="box",
            captions="word"
        )

        if not clip_file or not Path(clip_file).exists():
            if allow_checkpoint:
                self.session_mgr.set_action(chat_id, "render_failed", {
                    "job_dir": str(job_dir),
                    "target_streamer": streamer_name,
                    "video_title": video_title,
                    "channel": channel,
                    "query": query,
                    "layout": "react"
                })
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Rendering Klip Terkendala</b>\n\n"
                    f"File mentah & transkrip untuk <b>{safe_html(video_title[:65])}</b> tersimpan di server (Job ID: <code>{job_dir.name}</code>).\n\n"
                    f"💡 <i>Ketik <b>Lanjutkan</b> untuk langsung merender ulang tanpa download ulang!</i>"
                )
            else:
                self.send_message(chat_id, "❌ Gagal me-render video MP4.")
            return False

        self.send_message(chat_id, "4️⃣ <i>Memverifikasi kualitas klip sesuai SOP TikTok/Reels/Shorts...</i>")
        verify_clip(str(clip_file))

        caption_text = f"{title} 😭🔥 {cand_text[:80]}"
        credit_clean = channel if channel.startswith("@") else f"@{channel.replace(' ', '')}"
        delivered = self.send_video_card(
            chat_id=chat_id,
            video_path=str(clip_file),
            caption_text=caption_text,
            credit=credit_clean,
            job_id=job_dir.name,
            clip_name=f"clip_{pick_n}"
        )
        if delivered:
            self.session_mgr.add_history(chat_id, "assistant", f"Klip {video_title} berhasil dirender tuntas dan dikirim ke Telegram.")
        return delivered

    def _process_uploaded_video(self, chat_id: str, file_id: str, filename: str):
        job_label = f"Upload {filename[:20]}"
        if not ConcurrencyGuard.try_acquire(job_label):
            curr = ConcurrencyGuard.current_job()
            self.send_message(
                chat_id,
                f"⏳ <b>VPS Sedang Memproses Job Lain!</b>\n\n"
                f"Saat ini sedang berjalan: <b>{safe_html(curr)}</b>\n\n"
                f"<i>Mohon tunggu sebentar agar memori server tidak overload.</i>"
            )
            return

        try:
            disk_ok, disk_msg = check_and_enforce_disk_space(min_free_gb=1.5)
            if not disk_ok:
                self.send_message(chat_id, f"⚠️ <b>Guardrail Disk:</b> {safe_html(disk_msg)}")
                return

            timestamp = int(time.time())
            job_dir = JOBS_DIR / f"upload-{timestamp}"
            job_dir.mkdir(parents=True, exist_ok=True)
            src_file = job_dir / "source.mp4"

            self.send_message(chat_id, "1️⃣ <i>Mengunduh video ke server...</i>")
            if not self.download_file(file_id, src_file):
                self.send_message(chat_id, "❌ Gagal mengunduh video dari Telegram.")
                return

            self.send_message(chat_id, "2️⃣ <i>Mendeteksi ekspresi wajah seru, audio puncak & transkrip Whisper...</i>")
            job_res, candidates, err = extract_moments(src_file, top=6, max_minutes=15)
            if not candidates:
                self.send_message(chat_id, f"❌ Gagal mendeteksi momen dalam video: {safe_html((err or 'kosong')[:500])}")
                return

            self._render_and_deliver_best(
                chat_id, job_res or job_dir, candidates,
                streamer_name="Streamer", channel="@UploadedContent",
                video_title=filename, layout="react"
            )
        except Exception as e:
            print(f"[_process_uploaded_video error]: {e}")
            self.send_message(chat_id, f"⚠️ Error memproses video unggahan: {safe_html(str(e)[:400])}")
        finally:
            ConcurrencyGuard.release()

    def _auto_clip_pipeline(self, chat_id: str, query: str, layout: str = "react", streamer_name: str = "Streamer", resume_job_dir: Optional[str] = None):
        job_label = f"AutoClip {streamer_name} ({query[:20]})"
        if not ConcurrencyGuard.try_acquire(job_label):
            curr = ConcurrencyGuard.current_job()
            self.send_message(
                chat_id,
                f"⏳ <b>VPS Sedang Sibuk Memproses Render Lain!</b>\n\n"
                f"Saat ini sedang berjalan: <b>{safe_html(curr)}</b>\n\n"
                f"<i>Untuk mencegah kehabisan memori server, sistem memproses klip secara bergantian. Mohon tunggu sekitar 1-2 menit ya Bro!</i>"
            )
            return

        keep_checkpoint = False
        try:
            disk_ok, disk_msg = check_and_enforce_disk_space(min_free_gb=2.0)
            if not disk_ok:
                self.send_message(chat_id, f"⚠️ <b>Guardrail Penyimpanan:</b>\n{safe_html(disk_msg)}")
                return

            job_dir = None
            candidates = []
            video_title = "Target Video"
            channel = streamer_name

            if resume_job_dir and Path(resume_job_dir).exists() and (Path(resume_job_dir) / "candidates.json").exists():
                job_dir = Path(resume_job_dir)
                try:
                    cand_data = json.loads((job_dir / "candidates.json").read_text(encoding="utf-8"))
                    candidates = cand_data.get("candidates", [])
                except Exception:
                    candidates = []
                info_file = job_dir / "info.json"
                if info_file.exists():
                    try:
                        info = json.loads(info_file.read_text(encoding="utf-8"))
                        video_title = info.get("title") or video_title
                        channel = info.get("channel") or info.get("uploader") or channel
                    except Exception:
                        pass
                
                self.send_message(
                    chat_id,
                    f"⚡ <b>Melanjutkan dari Checkpoint:</b>\n"
                    f"• Video: <b>{safe_html(video_title[:65])}</b>\n"
                    f"• Channel: <b>{safe_html(channel)}</b>\n\n"
                    f"💡 <i>Video & transkrip siap. Langsung memotong dan merender 9:16 sampai tuntas...</i>"
                )

            if not job_dir or not candidates:
                clean_q = sanitize_input(query)
                if "trend" in clean_q.lower() or streamer_name == "GTA 6 Trending":
                    self.send_message(chat_id, "🔍 1️⃣ <i>Memindai radar tren YouTube & memilih video GTA 6 viral...</i>")
                else:
                    self.send_message(chat_id, f"🔍 1️⃣ <i>Mencari video terpopuler untuk '{safe_html(clean_q)}'...</i>")
                target = find_top_video(clean_q)
                if not target:
                    self.send_message(chat_id, f"❌ Tidak dapat menemukan video YouTube untuk query: <code>{safe_html(clean_q)}</code>")
                    return

                video_url = target["url"]
                video_title = target.get("title", "Target Video")
                channel = target.get("channel", streamer_name)

                self.send_message(
                    chat_id,
                    f"📥 2️⃣ <b>Target ditemukan!</b>\n"
                    f"• Judul: <b>{safe_html(video_title[:65])}</b>\n"
                    f"• Channel: <b>{safe_html(channel)}</b>\n\n"
                    f"⚡ <i>Mengunduh video, memindai ekspresi seru & transkrip Whisper...</i>"
                )
                job_dir, candidates, err = extract_moments(video_url, top=6, max_minutes=12)
                
                if err == "YOUTUBE_ANTIBOT_BLOCKED":
                    self.send_message(
                        chat_id,
                        "⚠️ <b>YouTube Membatasi IP Datacenter VPS</b>\n\n"
                        "YouTube mendeteksi server VPS dan memunculkan gate bot.\n\n"
                        "💡 <b>Solusi:</b> Pastikan reverse tunnel aktif atau forward file MP4 / cookies.txt langsung ke chat ini."
                    )
                    return

                if not candidates or not job_dir:
                    self.send_message(chat_id, f"❌ Gagal mendeteksi momen dalam video: {safe_html((err or 'kosong')[:500])}")
                    return

            self.session_mgr.set_action(chat_id, "ready_to_render", {
                "job_dir": str(job_dir),
                "target_streamer": streamer_name,
                "video_title": video_title,
                "channel": channel,
                "query": query,
                "layout": layout
            })

            ok = self._render_and_deliver_best(
                chat_id, job_dir, candidates,
                streamer_name=streamer_name, channel=channel, video_title=video_title,
                query=query, layout=layout, allow_checkpoint=True
            )
            if not ok and self.session_mgr.get_state(chat_id).get("action") == "render_failed":
                keep_checkpoint = True

        except Exception as e:
            print(f"[_auto_clip_pipeline error]: {e}")
            self.send_message(chat_id, f"⚠️ Error pipeline clipping: {safe_html(str(e)[:400])}")
        finally:
            if not keep_checkpoint:
                self.session_mgr.clear_action(chat_id)
            ConcurrencyGuard.release()

    def _process_url_clip(self, chat_id: str, url: str):
        clean_url = sanitize_input(url)
        job_label = f"URLClip ({clean_url[:20]})"
        if not ConcurrencyGuard.try_acquire(job_label):
            curr = ConcurrencyGuard.current_job()
            self.send_message(
                chat_id,
                f"⏳ <b>VPS Sedang Memproses Render Lain!</b>\n\n"
                f"Saat ini sedang berjalan: <b>{safe_html(curr)}</b>\n\n"
                f"<i>Mohon tunggu sebentar agar tidak crash.</i>"
            )
            return

        try:
            disk_ok, disk_msg = check_and_enforce_disk_space(min_free_gb=1.5)
            if not disk_ok:
                self.send_message(chat_id, f"⚠️ <b>Guardrail Disk:</b> {safe_html(disk_msg)}")
                return

            self.send_message(chat_id, "1️⃣ <i>Mengunduh video, menganalisis ekspresi seru & transkrip Whisper...</i>")
            job_dir, candidates, err = extract_moments(clean_url, top=6, max_minutes=15)
            if err == "YOUTUBE_ANTIBOT_BLOCKED":
                self.send_message(
                    chat_id,
                    "⚠️ <b>YouTube Membatasi IP Datacenter VPS</b>\n\n"
                    "YouTube meminta verifikasi login untuk link tersebut.\n\n"
                    "💡 <b>Solusi:</b> Kirim file video MP4 langsung atau file <code>cookies.txt</code>."
                )
                return

            if not candidates or not job_dir:
                self.send_message(chat_id, f"❌ Gagal menemukan momen seru dalam video: {safe_html((err or 'kosong')[:500])}")
                return

            info_file = job_dir / "info.json"
            video_title, channel = "Target Video", "@Creator"
            if info_file.exists():
                try:
                    info = json.loads(info_file.read_text(encoding="utf-8"))
                    video_title = info.get("title") or video_title
                    channel = info.get("channel") or info.get("uploader") or channel
                except Exception:
                    pass

            self._render_and_deliver_best(
                chat_id, job_dir, candidates,
                streamer_name=channel, channel=channel, video_title=video_title, layout="react"
            )
        except Exception as e:
            self.send_message(chat_id, f"⚠️ Terjadi error dalam alur pemotongan: {safe_html(str(e)[:400])}")
        finally:
            ConcurrencyGuard.release()

    # --- POLLING LOOP ---

    def start_polling(self):
        self.running = True
        print(f"[Telegram Bot] Polling started on @mein_clipping_studio_bot (Authorized chat: {self.allowed_chat_id})")
        
        while self.running:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 25}
                r = requests.get(f"{self.api_url}/getUpdates", params=params, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        if "message" in update:
                            self.handle_message(update["message"])
                        elif "callback_query" in update:
                            self.handle_callback(update["callback_query"])
                elif r.status_code == 409:
                    print("[Telegram Bot] Conflict (another instance running). Waiting 5s...")
                    time.sleep(5)
            except requests.exceptions.RequestException:
                time.sleep(3)
            except Exception as e:
                print(f"[Telegram Bot Polling Error]: {e}")
                time.sleep(3)

    def stop_polling(self):
        self.running = False
