import os
import sys
import signal
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from bot_core.telegram_bot import GTACoFounderBot
from bot_core.scheduler import CoFounderScheduler
from bot_core.config import GEMINI_MODEL

def main():
    print("=" * 60)
    print("🚀 [GTA VI CLIPPER STUDIO] STARTING CO-FOUNDER BOT (LANGGRAPH)")
    print("=" * 60)

    bot = GTACoFounderBot()
    scheduler = CoFounderScheduler(bot)
    scheduler.start()

    # Graceful shutdown handler
    def shutdown(signum, frame):
        print("\n[Bot] Shutting down gracefully...")
        bot.stop_polling()
        scheduler.running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    model_display = GEMINI_MODEL.replace("-", " ").title()

    # Initial test greeting to confirm bot online
    bot.send_message(
        bot.allowed_chat_id,
        "🟢 <b>Alex (Co-Founder Bot) Telah Aktif di VPS!</b>\n\n"
        f"Sistem otomasi kliping GTA VI dengan otak <b>LangGraph + {model_display}</b> siap digunakan 24/7.\n"
        "Gunakan tombol di bawah atau ketik chat bebas kapan pun!",
        reply_markup=bot.get_main_keyboard()
    )

    try:
        bot.start_polling()
    except KeyboardInterrupt:
        shutdown(None, None)

if __name__ == "__main__":
    main()
