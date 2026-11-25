# Daftar Kampanye Paid Clipping Aktif & Terverifikasi

Dokumen ini mencatat kampanye clipping yang aktif, tarif pembayaran (RPM), sisa alokasi dana, serta aturan teknis yang dipahami oleh skrip validasi `scripts/check.py`.

---

## 1. Aturan Validasi Skrip Otomatis (`check.py`)
Skrip `check.py` membaca baris parameter di bawah ini secara otomatis sebelum menyetujui video untuk diunggah:

* **min_seconds**: 15
* **max_seconds**: 55
* **required_hashtags**: #GTA6 #GTAVI #GamingClips
* **required_mention**: @ContentRewards

---

## 2. Tabel Kampanye Paid Clipping Terbuka (Live)

| No | Nama Kampanye / Streamer | Platform | Tarif / 1K Views | Batas / Cap Reward | Status Budget | Link Sumber | Aturan Utama |
|---|---|---|---|---|---|---|---|
| 1 | **Whop Content Rewards (Gaming Pool)** | TikTok, Shorts, Reels | **$1,00 - $2,50** | Max $250 / video | Aktif (Pool Berjalan) | [Whop Discover](https://whop.com/discover/) | Wajib hook di 3 detik awal, resolusi 9:16, cantumkan sumber asli. |
| 2 | **Clip.tech Creator Bounty** | TikTok, Instagram Reels | **$0,80 - $1,50** | Max $150 / video | Aktif (Rolling) | [Clip.tech Clippers](https://www.clip.tech/clippers) | Durasi 15-60s, akun publik, dilarang re-upload tanpa modifikasi teks/suara. |
| 3 | **Community Streamer Bounties (Twitch/Kick)** | YouTube Shorts, TikTok | **$0,50 - $1,00** | Max $100 / video | Aktif | [Content Rewards](https://contentrewards.com/) | Khusus memotong momen reaksi lucu/fails streamer dengan tag akun resmi. |

---

## 3. Checklist Kepatuhan Konten Sebelum Submit

- [ ] Durasi klip berada di antara 15 hingga 55 detik.
- [ ] Format video vertikal 1080x1920 (9:16).
- [ ] Subtitle dinamis dan jelas terlihat tanpa tertutup UI TikTok/Reels.
- [ ] Bebas dari konten bocoran (*no leaks*), cheat ilegal (*mod menu*), dan materi bajakan.
- [ ] Link postingan segera didaftarkan ke dashboard platform dalam waktu 24 jam setelah tayang.

---
*Terakhir diperbarui: 24 November 2026*
