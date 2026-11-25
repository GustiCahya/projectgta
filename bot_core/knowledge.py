from pathlib import Path
from bot_core.config import DOCS_DIR, BASE_DIR

SKILLS_DIR = BASE_DIR / "gtavi-claudecode" / "skills"

def load_skills_knowledge() -> str:
    """
    Loads core clipping skills transferred from the gtavi-claudecode plugin:
    - twitch-reaction: Facecam on top, gameplay on bottom, viral title on seam.
    - hook-writer: Formulaic on-screen hooks (numbers, curiosity gap, streamer reaction).
    - moment-finder: Most replayed heatmap, audio spikes, Whisper transcript scoring.
    - clip-cutter: 1080x1920 (9:16) vertical layout, word-by-word dynamic subtitles.
    - rule-check: SOP compliance (duration 15-60s, safe-area, 1080x1920, no watermarks).
    - trend-radar: Views per hour velocity ranking for fresh source discovery.
    - stream-finder: Live stream tracking on YouTube and Twitch.
    - multilang: Multi-language subtitle translation (ID, ES, PT, DE).
    - playbook: 25 master rules of viral faceless gaming channels.
    """
    skills_summary = []
    
    key_skills = [
        ("twitch-reaction", "Layout Split-Screen: Muka streamer di atas (730px), gameplay di bawah (1190px), judul viral di seam/tengah."),
        ("hook-writer", "Formula Hook Viral: [STREAMER] [REACTION VERB] [WHAT HAPPENED] dengan CAPS di 2-3 kata kunci. Kurang dari 50 karakter."),
        ("moment-finder", "Deteksi Momen: Analisis YouTube Most Replayed heatmap + lonjakan audio loudness RMS + transkrip Whisper."),
        ("clip-cutter", "Standar Render: Vertikal 9:16 (1080x1920), dynamic word captions safe area TikTok/Reels."),
        ("rule-check", "SOP Kualitas: Durasi 15-60s, aspect ratio 9:16, audio jernih ternormalisasi, aman dari banned leaks."),
        ("trend-radar", "Radar Tren: Memindai video dengan views/jam tertinggi dalam 24-48 jam."),
        ("stream-finder", "Pencari Live: Memantau live stream aktif di YouTube dan Twitch dengan penonton terbanyak."),
        ("multilang", "Multi-Bahasa: Translasi otomatis subtitle klip ke Bahasa Indonesia, Spanyol, Portugis."),
        ("playbook", "Playbook Viral: 25 aturan monetisasi video pendek, pacing cepat, hook 2 detik pertama.")
    ]
    
    for skill_name, desc in key_skills:
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        extra = ""
        if skill_file.exists():
            try:
                txt = skill_file.read_text(encoding="utf-8", errors="replace")
                # Grab first 400 chars of instructions
                lines = [l for l in txt.splitlines() if not l.startswith("---") and l.strip()]
                extra = " ".join(lines[:4])[:300]
            except Exception:
                pass
        skills_summary.append(f"- **{skill_name.upper()}**: {desc} {extra}")
        
    return "\n".join(skills_summary)

def load_business_knowledge() -> str:
    """
    Reads key summaries from master planning documents.
    """
    knowledge = []
    
    docs_to_read = [
        ("Master Strategy & Roadmap", DOCS_DIR / "rencana_bisnis_monetisasi_gta_vi.md"),
        ("SOP Operasional & Master Plan B2B", DOCS_DIR / "rencana_bisnis_sop_operasional_gta_vi_content_b2b_ecosystem.md"),
        ("Daftar Kampanye Whop/Clip.tech", DOCS_DIR / "campaigns.md"),
        ("Panduan Langkah Eksekusi Praktis", DOCS_DIR / "panduan_langkah_awal_eksekusi.md")
    ]
    
    for title, doc_path in docs_to_read:
        if doc_path.exists():
            try:
                content = doc_path.read_text(encoding="utf-8", errors="replace")
                # Read first 1200 chars of each to avoid bloated token context
                knowledge.append(f"### [DOKUMEN BISNIS: {title}]\n{content[:1200]}\n")
            except Exception as e:
                knowledge.append(f"### [DOKUMEN BISNIS: {title} (Error: {e})]\n")
                
    return "\n".join(knowledge)

def get_co_founder_system_prompt() -> str:
    docs_context = load_business_knowledge()
    skills_context = load_skills_knowledge()
    
    return f"""Kamu adalah **Alex**, Co-Founder & Head of Content Engineering di agensi media clipping GTA VI bersama partner usahamu (user).
Kamu memiliki seluruh keterampilan (skills) penuh dari sistem clipping project GTA VI (gtavi-claudecode).

### Keterampilan Utama (Full Skills Suite):
{skills_context}

### Format Video Wajib (Standar Reaksi Streamer):
- **JIKA ADA STREAMER**: Muka streamer di atas (facecam crop), game di bawah, dan judul hook di garis batas tengah (seam).
- **JIKA HANYA GAMEPLAY**: Format vertikal 9:16 (1080x1920) dengan blur background yang estetis.
- **HOOK & JUDUL**: Mengikuti formula `hook-writer`: pendek, huruf kapital pada 2-3 kata kunci, memicu rasa penasaran tinggi, 1 emoji.
- **SUBTITLE**: Subtitle dinamis kata-per-kata yang aman dari icon UI TikTok/Reels/Shorts.

### Prinsip Utama & Gaya:
1. **Action-Oriented & Anti Basa-Basi**: Jika partner meminta membuat video, memotong klip, atau menyebut nama streamer (misal: 'IShowSpeed', 'Windah', 'buat video lucu', 'potong video'), JANGAN MENANYAKAN PILIHAN BERBELIT-BELIT atau berputar-putar di persiapan! Langsung eksekusi pipeline clipping dengan layout 'react'.
2. **Nada Bicara**: Santai tapi kompeten, street-smart, dan to-the-point. Panggil partner dengan "Bro" atau "Partner". Gunakan bahasa Indonesia kasual yang natural dan enerjik.
3. **Fokus Cashflow**: Target utama kita adalah Fase 1 (Paid Clipping Bounty Whop/Clip.tech dengan payout $1-$2.5 per 1k views).

### Dokumen & SOP Bisnis:
{docs_context}
"""
