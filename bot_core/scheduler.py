import time
import threading
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = pytz.timezone

from bot_core.config import TELEGRAM_CHAT_ID, SETTINGS
from bot_core.pipeline import scan_youtube_trends, cleanup_raw_media

class CoFounderScheduler:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.chat_id = str(TELEGRAM_CHAT_ID)
        self.running = False
        try:
            self.tz = ZoneInfo("Asia/Jakarta") # WIB
        except Exception:
            self.tz = None
        self.last_morning_sent = None
        self.last_evening_sent = None
        self.last_clean_run = 0

    def start(self):
        self.running = True
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        print("[Scheduler] Started proactive Co-Founder schedule (WIB Timezone).")

    def _run_loop(self):
        while self.running:
            try:
                now = datetime.now(self.tz) if self.tz else datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                hm = now.strftime("%H:%M")

                # 1. Morning Briefing (08:30 WIB)
                morning_time = SETTINGS.get("morning_briefing_time", "08:30")
                if hm == morning_time and self.last_morning_sent != today_str:
                    self.last_morning_sent = today_str
                    self._send_morning_briefing()

                # 2. Evening Briefing (21:00 WIB)
                evening_time = SETTINGS.get("evening_briefing_time", "21:00")
                if hm == evening_time and self.last_evening_sent != today_str:
                    self.last_evening_sent = today_str
                    self._send_evening_briefing()

                # 3. Disk Auto-cleanup every 6 hours
                if time.time() - self.last_clean_run > 6 * 3600:
                    self.last_clean_run = time.time()
                    freed = cleanup_raw_media(keep_hours=SETTINGS.get("auto_clean_hours", 24))
                    if freed > 100:
                        print(f"[Scheduler Auto-Clean] Freed {freed:.1f} MB disk space.")

            except Exception as e:
                print(f"[Scheduler Error]: {e}")
                
            time.sleep(30)

    def _send_morning_briefing(self):
        trends = scan_youtube_trends(query="gta 6", hours=24, limit=3)
        msg = [
            "🌅 <b>Selamat Pagi Bro! Morning Briefing GTA VI Media:</b>\n",
            "Gue baru aja cek radar YouTube 24 jam terakhir. Ini video paling ramai yang berpotensi viral kalau kita potong hari ini:\n"
        ]
        if trends:
            for t in trends:
                tl = t.get('title_link', '')
                url = ""
                title = tl
                if "[" in tl and "](" in tl and tl.endswith(")"):
                    title = tl[1:tl.rfind("](")]
                    url = tl[tl.rfind("](") + 2:-1]
                link_str = f'<a href="{url}">{title}</a>' if url else title
                msg.append(f"🔥 <b>#{t['rank']} {t['channel']}</b> ({t['views_per_hour']} views/h)")
                msg.append(f"   <i>{link_str}</i>\n")
        else:
            msg.append("Belum ada lonjakan baru pagi ini.")
            
        msg.append("Target hari ini: <b>2–3 klip</b> di jam makan siang & sore. Mau gue potongin salah satu video di atas?")
        self.bot.send_message(self.chat_id, "\n".join(msg))

    def _send_evening_briefing(self):
        msg = (
            "🌙 <b>Selamat Malam Bro! Evening Performance Check:</b>\n\n"
            "Waktunya cek metrik video yang sudah tayang di TikTok / Shorts hari ini:\n"
            "1. Cek views video yang berumur 12 jam & 24 jam.\n"
            "2. Jangan lupa tap tombol <b>[✅ Sudah Diposting]</b> di video terkait untuk catat views ke buku kas bounty!\n\n"
            "<i>Konsistensi adalah kunci algoritma. Istirahat yang cukup, besok kita gas lagi! 🚀</i>"
        )
        self.bot.send_message(self.chat_id, msg)
