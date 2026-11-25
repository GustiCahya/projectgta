# Panduan Langkah Awal Eksekusi: Monetisasi GTA VI & Content Engineering

Dokumen ini merupakan panduan operasional praktis (*action plan*) untuk memulai bisnis media dan kliping otomatis GTA VI berdasarkan dokumen strategi bisnis dan repositori `gtavi-claudecode`.

---

## 1. Prinsip Utama: *Cashflow First, Owned Media Second*

Model bisnis ini memprioritaskan arus kas cepat sebelum menunggu persyaratan monetisasi resmi platform (AdSense/TikTok Creator Rewards):

```
[Fase 1: Validasi & Cashflow Cepat] ──► [Fase 2: Bangun Aset Kanal] ──► [Fase 3: Agensi B2B & Komunitas]
• Paid Clipping Campaigns               • YouTube Shorts AdSense        • Managed Clipping Retainer
• Payout: $0.50 - $2.00 / 1k views      • TikTok Creator Rewards        • Komunitas & Server RP
• Akun baru langsung bisa cuan          • Afiliasi Gaming Console
```

---

## 2. Rincian 5 Langkah Eksekusi Awal

### Langkah 1: Setup Fondasi Teknis (Local Environment)
Mempersiapkan pipeline pengolahan video otomatis di mesin lokal.

* **Status FFmpeg**: Sudah terpasang (`ffmpeg v9.0.1`).
* **Instalasi Python 3.12**:
  ```powershell
  winget install Python.Python.3.12 -e --source winget
  ```
* **Instalasi Dependensi Script** (di dalam folder `gtavi-claudecode`):
  ```powershell
  cd d:\projects\ProjectGTA\gtavi-claudecode
  python -m pip install -U -r requirements.txt
  ```

---

### Langkah 2: Pindai & Registrasi Platform Paid Clipping
Menentukan target kampanye yang akan membayar setiap 1.000 views sebelum memotong video.

1. **Whop Content Rewards**:
   * Akses: `https://whop.com/discover/` (cari keyword: *GTA 6*, *gaming clipping*, *streamer bounty*).
   * Catat: Rate per 1k views, sisa budget, dan batas maksimal per video/kreator.
2. **Clip.tech**:
   * Akses: `https://www.clip.tech/clippers`.
   * Cek daftar kampanye terbuka tanpa perlu login awal.
3. **Pilih 1–2 Kampanye Prioritas**:
   * Pilih streamer atau brand gaming dengan aturan klip yang jelas dan izin penggunaan konten terbuka.

---

### Langkah 3: Tentukan Niche & Setup Kanal Distribusi
Membangun akun publikasi yang terarah agar algoritma platform membaca audiens dengan tepat.

1. **Pilih 1 Niche Lane**:
   * *Lane A*: Tips, Easter Eggs, & Hidden Spots (retensi tinggi, tahan lama).
   * *Lane B*: Reaksi Streamer & Momen Lucu/Gagal (viralitas cepat, cocok untuk paid clipping).
   * *Lane C*: Analisis Kendaraan, Senjata, & Kustomisasi.
2. **Setup Akun Distribusi**:
   * Buat akun baru di **TikTok**, **YouTube Shorts**, dan **Instagram Reels** dengan nama/handle seragam.
3. **Inisialisasi File Operasional Workspace**:
   * Buat `campaigns.md` (pencatatan kampanye aktif).
   * Buat `scoreboard.csv` (pencatatan performa view & metrik 24h/72h).
   * Buat `payouts.csv` (pencatatan klaim pembayaran).

---

### Langkah 4: Uji Coba Produksi 1 Video Pertama (Proof of Concept)
Memastikan pipeline AI menghasilkan video berstandar tinggi yang lolos verifikasi kampanye.

1. **Ambil Sumber Video**:
   * Jalankan radar tren untuk mengambil VOD streamer yang relevan:
     ```powershell
     python scripts/trends.py --query "gta 6" --hours 24
     ```
2. **Deteksi Momen Menarik**:
   * Ekstraksi momen dengan lonjakan audio/chat:
     ```powershell
     python scripts/moments.py "<URL_YOUTUBE_ATAU_TWITCH>" --top 5
     ```
3. **Rendering Klip Vertikal (9:16)**:
   * Potong klip dengan layout vertikal, hook teks awal, dan takarir otomatis:
     ```powershell
     python scripts/cut.py jobs/<job_id> --pick 1 --layout facecam --hook "Rahasia yang dilewatkan semua orang"
     ```
4. **Verifikasi Kualitas**:
   * Hook muncul dalam 1 detik pertama.
   * Teks subtitle berada di dalam *safe area* (tidak tertutup ikon TikTok/Reels).
   * Durasi ideal: 15–30 detik.
   * Sertakan kredit streamer di caption/watermark.

---

### Langkah 5: Rutinitas Harian & Klaim Payout
Menjalankan siklus harian setelah alur terbukti stabil.

* **Minggu ke-1**: Produksi 2–3 klip per hari (hindari upload berlebihan pada akun baru agar tidak terdeteksi spam).
* **Minggu ke-2 dst**: Naikkan kapasitas ke 5–10 klip per hari.
* **Proses Klaim**: Setiap klip yang telah diposting segera disubmit link-nya ke dashboard Whop / Clip.tech untuk penghitungan payout.

---

## 3. Checklist Kepatuhan & Keamanan Akun

- [ ] **Bukan Re-upload Mentah**: Selalu gunakan kombinasi hook, takarir dinamis, atau layout reaksi (*transformative edit*).
- [ ] **Atribusi Jelas**: Cantumkan nama kreator/streamer di deskripsi video.
- [ ] **Bebas Konten Bocoran (No Leaks)**: Hindari materi ilegal/bocoran internal Rockstar yang berisiko terkena *copyright strike*.
- [ ] **Targetkan Geografis Bernilai Tinggi**: Jika memungkinkan, targetkan audiens Tier-1 (US/UK/AU) untuk memaksimalkan RPM.
