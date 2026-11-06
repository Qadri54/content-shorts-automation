# Content Shorts Automation

Sistem produksi konten YouTube Shorts otomatis yang menggunakan orkestrasi AI untuk menghasilkan video fakta unik berkualitas tinggi tanpa biaya langganan. Project ini memanfaatkan **CrewAI** sebagai framework orkestrasi multi-agent, **Gemini Flash** sebagai model AI generatif, dan tools video processing lokal untuk menghasilkan video siap upload.

## Table of Contents

1. [Orkestrasi AI dengan CrewAI](#orkestrasi-ai-dengan-crewai)
2. [Project Summary](#project-summary)
3. [Credential Setup](#credential-setup)
4. [Installation & Setup](#installation--setup)
5. [Usage](#usage)
6. [Output Structure](#output-structure)
7. [Fact-Checking System](#fact-checking-system)
8. [Customization](#customization)

---

## Orkestrasi AI dengan CrewAI

Project ini menggunakan **CrewAI** untuk mengatur tiga AI agent yang bekerja secara sekuensial dalam pipeline produksi konten:

1. **Scriptwriter Agent**: Agent pertama yang bertugas memilih topik dari daftar sub-tema dan menulis naskah 140-160 kata. Agent ini memahami tone channel, target durasi, dan struktur narasi yang engaging.

2. **Fact-Checker Agent**: Menerima output dari Scriptwriter dan memverifikasi setiap klaim faktual. Agent ini dapat mengoreksi, menghapus klaim yang tidak terverifikasi, atau menolak naskah sepenuhnya jika terlalu banyak masalah. Jika ditolak, sistem otomatis retry dengan topik berbeda (maksimal 3x).

3. **Visual & SEO Director Agent**: Agent terakhir yang memecah naskah menjadi scene-by-scene breakdown, menentukan keyword B-roll untuk setiap scene, membuat metadata SEO (judul/deskripsi/tags), dan memilih mood musik. Output agent ini menjadi blueprint lengkap untuk rendering video.

Setiap agent memiliki role, goal, dan tools spesifik yang didefinisikan dalam CrewAI, memastikan setiap tahap produksi dikerjakan oleh "spesialis" yang tepat.

---

## Project Summary

**Content Shorts Automation** adalah mesin konten YouTube Shorts otomatis yang menggabungkan:

- **AI Multi-Agent System (CrewAI + Gemini Flash)**: Menulis naskah, fact-checking, dan menyusun storyboard
- **Text-to-Speech (Edge-TTS)**: Voiceover bahasa Indonesia dengan suara natural
- **Video Asset Management (Pixabay + Pexels)**: Download B-roll otomatis dengan prioritas format portrait 9:16 dan fallback provider
- **Subtitle Generation (faster-whisper)**: Subtitle per-kata dengan timing presisi
- **Video Rendering (FFmpeg)**: Encoding H.264/AAC dengan audio normalization dan ducking

### Alur Produksi per Video

1. **Scriptwriter** memilih 1 fakta dari sub-tema yang sedang dirotasi, lalu menulis naskah 140–160 kata
2. **Fact-Checker** memeriksa setiap klaim: koreksi, hapus, atau tolak. Kalau ditolak, sistem otomatis mencari topik lain (maksimal 3x)
3. **Visual & SEO Director** memecah naskah menjadi 12–15 scene + keyword B-roll + judul/deskripsi/tags + mood musik
4. Voiceover per scene (id-ID-ArdiNeural). Kecepatan bicara disesuaikan otomatis agar durasi 50–59 detik
5. B-roll diambil dari **Pixabay** (prioritas utama) dengan fallback ke **Pexels** jika diperlukan. Prioritas portrait 9:16, otomatis center-crop jika horizontal
6. Subtitle per kata (huruf kapital, kata aktif kuning) dari faster-whisper, diselaraskan ke naskah asli
7. Render FFmpeg: H.264/AAC, 30fps, musik -18dB + ducking, loudness -14 LUFS

---

## Credential Setup

### 1. Setup Gemini API Key

1. Buka [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Login dengan akun Google Anda
3. Klik **"Get API Key"** atau **"Create API Key"**
4. Copy API key yang dihasilkan
5. Paste ke file `.env`:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

### 2. Setup Media Provider API Keys

Project ini mendukung **dua provider** untuk B-roll video: **Pixabay** (required) dan **Pexels** (optional fallback).

#### A. Pixabay API Key (Wajib)

**Pixabay adalah provider utama dan wajib diisi.**

1. Buka [Pixabay API Documentation](https://pixabay.com/api/docs/)
2. Daftar/login ke akun Pixabay
3. Scroll ke bagian **"Search Videos"** untuk melihat API key Anda
4. Copy API key (approval instan tanpa review)
5. Paste ke file `.env`:
   ```
   PIXABAY_API_KEY=your_pixabay_api_key_here
   ```

**Keuntungan Pixabay:**
- API key gratis dan instan (tanpa approval manual)
- Koleksi video stock berkualitas tinggi
- Rate limit cukup untuk produksi harian

#### B. Pexels API Key (Opsional - Fallback)

**Pexels berfungsi sebagai fallback jika Pixabay tidak menemukan video yang sesuai.**

1. Buka [Pexels API](https://www.pexels.com/api/)
2. Klik **"Get Started"** dan daftar akun
3. Verifikasi email Anda
4. Buka [API dashboard](https://www.pexels.com/api/) dan copy API key
5. Paste ke file `.env`:
   ```
   PEXELS_API_KEY=your_pexels_api_key_here
   ```

**Catatan:**
- Jika hanya Pixabay yang diisi, sistem akan tetap berjalan normal
- Jika kedua API key diisi, sistem akan menggunakan Pexels sebagai fallback otomatis
- Minimal satu dari PIXABAY_API_KEY atau PEXELS_API_KEY harus diisi

### 3. YouTube Authorization (Optional - untuk auto-upload)

> ⚠️ **PERINGATAN PENTING - DEFAULT UPLOAD ADALAH PUBLIC**
>
> Secara default, semua video yang di-upload dengan flag `--upload` akan langsung **PUBLIC** dan terlihat oleh semua orang. Jika Anda ingin review video terlebih dahulu sebelum publish:
> - Gunakan flag `--upload-private` untuk upload sebagai **private**
> - Atau ubah default di `.env`: `YOUTUBE_DEFAULT_PRIVACY=private`
>
> **Privacy levels yang tersedia:**
> - `public`: Video langsung terlihat semua orang (default)
> - `unlisted`: Video hanya bisa diakses lewat link
> - `private`: Video hanya terlihat oleh Anda

#### A. Konfigurasi Google Cloud Console

1. Buka [Google Cloud Console](https://console.cloud.google.com)
2. Pilih project Anda atau buat project baru
3. Di menu navigasi, pilih **"APIs & Services"** → **"Library"**
4. Cari dan aktifkan **"YouTube Data API v3"**
5. Klik **"ENABLE"**

#### B. Buat OAuth 2.0 Client ID

1. Di Google Cloud Console, pilih **"APIs & Services"** → **"Credentials"**
2. Klik **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. Jika diminta, konfigurasi OAuth consent screen terlebih dahulu:
   - User Type: **External**
   - App name: bebas (contoh: "YT Shorts Factory")
   - User support email: email Anda
   - Developer contact: email Anda
   - **Penting:** Tambahkan **Test users** di tab "Test users" (masukkan email YouTube channel Anda)
4. Kembali ke **"Credentials"** → **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
5. Application type: **"Desktop app"**
6. Name: bebas (contoh: "YT Shorts Desktop Client")
7. Klik **"CREATE"**
8. Download file JSON yang dihasilkan

#### C. Simpan Client Secret

1. Rename file JSON yang di-download menjadi `client_secret.json`
2. Simpan di folder: `config/client_secret.json`

Format file harus seperti ini:
```json
{
    "installed": {
        "client_id": "your-client-id.apps.googleusercontent.com",
        "project_id": "your-project-id",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "GOCSPX-xxxxxxxxxxxx",
        "redirect_uris": ["http://localhost:8090/", "urn:ietf:wg:oauth:2.0:oob"]
    }
}
```

#### D. Jalankan Authentication Script

**Rekomendasi: Gunakan Manual Mode (lebih stabil di Windows)**

```bash
# Aktifkan virtual environment terlebih dahulu
.venv/Scripts/activate

# Jalankan script manual authentication
python scripts/setup_youtube_manual.py
```

**Langkah-langkah:**
1. Script akan menampilkan URL authorization
2. Copy URL tersebut dan buka di browser
3. Login dengan akun YouTube Anda
4. Klik **"Allow"** untuk memberikan akses
5. Google akan menampilkan **authorization code**
6. Copy code tersebut
7. Paste code ke terminal dan tekan Enter
8. Credentials akan tersimpan di `config/youtube_credentials.json`

**Alternatif: Automatic Browser Mode (jika manual tidak berhasil)**
```bash
python scripts/setup_youtube.py
```

> **Catatan:** Jika app masih dalam mode "Testing", hanya test users yang ditambahkan di OAuth consent screen yang bisa login. Untuk production, submit app untuk verification di Google Cloud Console.

#### E. Verifikasi Setup

Setelah authentication berhasil, test upload sebagai private terlebih dahulu:
```bash
python main.py --count 1 --upload-private
```

---

## Installation & Setup

```bash
# Clone repository dengan nama yang benar
git clone https://github.com/Qadri54/content-shorts-automation.git
cd content-shorts-automation

# Setup Python virtual environment
py -3.13 -m venv .venv
.venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Lalu edit .env dan isi minimal:
# - GEMINI_API_KEY
# - PIXABAY_API_KEY (wajib)
# - PEXELS_API_KEY (opsional untuk fallback)

# Verifikasi semua komponen
python main.py --check
```

**Requirements:**
- Python 3.11+
- FFmpeg wajib ada di PATH: `winget install Gyan.FFmpeg`
- Minimal Pixabay API key (Pexels opsional)

---

## Usage

### CLI Commands Reference

```bash
# Generate 1 video (default)
python main.py

# Generate multiple videos dengan jeda antar video
python main.py --count 3

# Force sub-tema tertentu (nama dari data/channel.json)
python main.py --sub-theme "Luar Angkasa"

# Blueprint only: naskah + metadata saja, tanpa render video
python main.py --blueprint-only

# Cleanup: hapus file temporary setelah render sukses
python main.py --count 3 --cleanup

# Upload ke YouTube (PUBLIC - HATI-HATI!)
python main.py --upload

# Upload ke YouTube sebagai PRIVATE (untuk review dulu)
python main.py --upload-private

# Check environment: verifikasi API keys, FFmpeg, model Gemini
python main.py --check

# Verbose mode: tampilkan detail proses agent CrewAI
python main.py --verbose
```

### Kombinasi Praktis

```bash
# Produksi batch 5 video dengan cleanup otomatis
python main.py --count 5 --cleanup

# Generate + review lokal sebelum upload manual
python main.py --count 1
# (review video di data/output/, lalu upload manual lewat YouTube Studio)

# Generate + auto-upload private untuk QA
python main.py --count 3 --upload-private --cleanup

# Testing: blueprint only tanpa render (hemat waktu saat testing naskah)
python main.py --sub-theme "Teknologi" --blueprint-only --verbose
```

---

## Output Structure

Setiap video dihasilkan di folder timestamped: `data/output/<YYYYMMDD_HHMMSS>_<slug>/`

### File Output Utama

```
data/output/20241106_193045_gurita-punya-tiga-jantung/
├── gurita-punya-tiga-jantung.mp4    # Video final siap upload (H.264/AAC, 1080x1920, 30fps)
├── metadata.txt                      # Judul, deskripsi, tags + ringkasan fact-check
├── thumbnail.png                     # Thumbnail otomatis (frame pertama video)
├── blueprint.json                    # Full production blueprint dari Visual & SEO Director
├── factcheck.json                    # Detailed fact-check report dengan per-claim verification
├── youtube_upload.json               # Upload result (jika menggunakan --upload)
│
├── subtitles/
│   ├── subtitles.srt                # Subtitle SRT (bisa diupload sebagai CC)
│   └── subtitles.ass                # Subtitle ASS dengan styling (embedded di video)
│
├── audio/
│   ├── scene_001.mp3                # TTS per scene
│   ├── scene_002.mp3
│   └── ...
│
├── clips/
│   ├── scene_001.mp4                # B-roll video per scene
│   ├── scene_002.mp4
│   └── ...
│
└── scenes/
    ├── scene_001_rendered.mp4       # Rendered scene dengan audio + subtitle
    ├── scene_002_rendered.mp4
    └── ...
```

### metadata.txt Format

File `metadata.txt` berisi semua informasi yang diperlukan untuk upload manual:

```
=== YOUTUBE METADATA ===

JUDUL (70 karakter):
Gurita Punya Tiga Jantung! Ini Alasannya 🐙

DESKRIPSI:
Fakta unik tentang gurita yang jarang diketahui...
[deskripsi lengkap]

TAGS:
fakta unik, gurita, hewan laut, sains, edukasi
[10-15 tags]

=== HASIL FACT-CHECK ===

Verdict: APPROVED
Confidence: 0.92

Claim Verification:
1. ✓ VERIFIED: Gurita memiliki tiga jantung
   Source: Marine Biology Research Institute
   
2. ✓ VERIFIED: Dua jantung untuk insang, satu untuk tubuh
   Source: National Geographic Ocean Studies
   
[detail per-claim verification]
```

### File untuk Review Manual

- `metadata.txt`: Copy-paste untuk YouTube upload manual
- `subtitles/subtitles.srt`: Bisa diupload sebagai closed captions
- `factcheck.json`: Detail verification untuk audit fact-checking

### File untuk Debugging

- `blueprint.json`: Full structured data dari AI agents
- `audio/`, `clips/`, `scenes/`: Intermediate files (bisa dihapus dengan `--cleanup`)

---

## Fact-Checking System

Sistem fact-checking menggunakan **Fact-Checker Agent** yang memverifikasi setiap klaim faktual dalam naskah sebelum video diproduksi.

### Verdict Types

**APPROVED**
- Semua klaim terverifikasi atau berhasil dikoreksi
- Confidence score ≥ 0.7 (minimum threshold)
- Video dapat dilanjutkan ke tahap produksi

**REVISED**
- Beberapa klaim dikoreksi atau dihapus
- Final script masih layak diproduksi
- Confidence score ≥ 0.7

**REJECTED**
- Terlalu banyak klaim yang tidak terverifikasi
- Confidence score < 0.7
- Naskah ditolak, sistem otomatis retry dengan topik berbeda
- **Maximum 3 retry attempts** per video

### Claim Status

Setiap klaim dalam naskah akan diberi status:

- **verified**: Klaim benar dan terverifikasi dari sumber terpercaya
- **corrected**: Klaim diperbaiki untuk akurasi (misal: angka, tanggal, nama)
- **removed**: Klaim tidak bisa diverifikasi dan dihapus dari naskah final

### Fact-Check Report Structure

File `factcheck.json` berisi structured data dengan format:

```json
{
  "verdict": "APPROVED | REVISED | REJECTED",
  "confidence": 0.92,
  "final_script": "Naskah yang sudah diverifikasi dan dikoreksi...",
  "claims": [
    {
      "claim": "Gurita memiliki tiga jantung",
      "status": "verified",
      "note": "Fakta benar, didukung oleh penelitian marine biology",
      "source_hint": "Marine Biology Research, National Geographic"
    },
    {
      "claim": "Gurita dapat mengubah warna dalam 0.3 detik",
      "status": "corrected",
      "note": "Waktu sebenarnya adalah ~0.3-0.5 detik, bukan instant",
      "source_hint": "Journal of Experimental Biology"
    },
    {
      "claim": "Gurita bisa hidup 100 tahun",
      "status": "removed",
      "note": "Tidak akurat - usia maksimal gurita adalah 3-5 tahun",
      "source_hint": "Marine Biology Textbook"
    }
  ],
  "reason": "Script approved dengan minor corrections pada timing dan angka"
}
```

### Retry Logic

Jika naskah mendapat verdict **REJECTED**:

1. **Attempt 1**: Topik A → REJECTED → discard
2. **Attempt 2**: Topik B (berbeda) → fact-check lagi
3. **Attempt 3**: Topik C (berbeda) → last attempt
4. **After 3 fails**: Raise error, video tidak diproduksi

Sistem otomatis memilih topik berbeda dari sub-tema yang sama pada setiap retry untuk menghindari masalah yang sama.

### Best Practices

✅ **Selalu baca bagian "HASIL FACT-CHECK" di metadata.txt**
- Periksa claims yang di-correct untuk memastikan akurasi
- Review confidence score (semakin tinggi semakin baik)
- Tonton video sebelum upload untuk verifikasi final

✅ **Gunakan --verbose untuk debugging fact-check**
```bash
python main.py --verbose
```
Flag ini menampilkan reasoning agent saat melakukan fact-checking.

⚠️ **AI tetap bisa salah**
- Fact-checker Agent menggunakan knowledge cutoff model LLM
- Untuk topik sangat baru atau niche, lakukan verifikasi manual
- Confidence score < 0.85 sebaiknya di-review manual sebelum upload

---

## Customization

### Channel Profile & Sub-Themes

Edit `data/channel.json` untuk mengatur:
- Nama channel dan niche
- Sub-tema (topic categories) yang akan dirotasi
- Content guidelines dan banned topics
- Hashtag defaults
- Tone dan style narasi

```json
{
  "channel_id": "faktaunik_id",
  "channel_name": "Fakta Unik Indonesia",
  "niche": "Fakta Unik",
  "sub_themes": [
    {
      "name": "Hewan & Alam",
      "description": "Fakta unik tentang hewan dan fenomena alam",
      "examples": ["Gurita punya 3 jantung", "Pohon tertinggi di dunia"]
    }
  ]
}
```

### Background Music

Letakkan file musik bebas royalti di `data/music/<mood>/`:

**Mood yang tersedia:**
- `mysterious/`: Musik misterius untuk fakta menakjubkan
- `curious/`: Musik curious untuk fakta science
- `upbeat/`: Musik upbeat untuk fakta fun/lighthearted
- `dramatic/`: Musik dramatic untuk fakta serius
- `calm/`: Musik calm untuk fakta nature/relax

**Format support**: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.aac`

Sistem akan memilih random dari folder mood yang dipilih oleh Visual & SEO Director agent. Lihat `data/music/README.txt` untuk rekomendasi sumber musik gratis.

### Custom Fonts

1. Download file font `.ttf` (contoh: Poppins, Montserrat, Bebas Neue)
2. Letakkan di folder `data/fonts/`
3. Set di `.env`:
   ```
   SUBTITLE_FONT=Poppins Bold
   SUBTITLE_FONT_SIZE=88
   ```

### Environment Configuration

Edit `.env` untuk fine-tuning:

```bash
# Model AI
GEMINI_MODEL=gemini/gemini-2.5-flash
LLM_TEMPERATURE=0.7              # Kreativitas (0.0-1.0)

# Target durasi video
TARGET_MIN_SECONDS=50            # Minimum durasi
TARGET_MAX_SECONDS=59            # Maximum durasi (untuk Shorts <60s)

# TTS Voice & Speed
TTS_VOICE=id-ID-ArdiNeural       # Edge-TTS voice ID
TTS_BASE_RATE=8                  # Base speaking rate (%)

# Whisper Model (transcription)
WHISPER_MODEL=base               # tiny | base | small
WHISPER_DEVICE=cpu               # cpu | cuda
WHISPER_COMPUTE_TYPE=int8        # int8 | float16 | float32

# Subtitle styling
SUBTITLE_FONT=Arial Black
SUBTITLE_FONT_SIZE=88
SUBTITLE_MAX_WORDS=3             # Maksimal kata per line

# Background music
MUSIC_VOLUME_DB=-18              # Volume musik relatif terhadap voice

# Batch settings
DELAY_BETWEEN_RUNS=5             # Jeda antar video (detik) untuk rate limiting

# YouTube upload
YOUTUBE_DEFAULT_PRIVACY=public   # public | unlisted | private
YOUTUBE_CATEGORY=27              # 27 = Education
```

### Video Quality Settings

Untuk mengubah quality encoding, edit di `config/settings.py`:

```python
video_width: int = 1080
video_height: int = 1920
video_fps: int = 30
video_crf: int = 20              # Lower = higher quality (18-23 recommended)
video_preset: str = "medium"     # ultrafast, fast, medium, slow, veryslow
```

---

## Troubleshooting

### Common Issues

**"PIXABAY_API_KEY belum diisi"**
- Pastikan `.env` sudah di-copy dari `.env.example`
- Isi minimal `PIXABAY_API_KEY` (wajib)
- Jalankan `python main.py --check` untuk verifikasi

**"ffmpeg tidak ditemukan di PATH"**
- Install FFmpeg: `winget install Gyan.FFmpeg`
- Restart terminal setelah install
- Verify: `ffmpeg -version`

**"Video ditolak setelah 3 attempts"**
- Sub-tema terlalu spesifik atau controversial
- Coba sub-tema lain: `python main.py --sub-theme "Tema Lain"`
- Atau adjust content guidelines di `data/channel.json`

**B-roll video tidak ditemukan**
- Pixabay tidak menemukan hasil untuk keyword
- Jika punya Pexels API key, akan otomatis fallback
- Adjust keyword strategy di channel guidelines
- Atau gunakan keyword bahasa Inggris yang lebih generic

**YouTube upload gagal**
- Pastikan `config/client_secret.json` dan `config/youtube_credentials.json` ada
- Re-run authentication: `python scripts/setup_youtube_manual.py`
- Check quota limit di Google Cloud Console (default 10k units/day)

---

## License & Attribution

Pastikan mematuhi terms of service dari:
- **Pixabay**: [Terms of Service](https://pixabay.com/service/terms/)
- **Pexels**: [License](https://www.pexels.com/license/)
- Background music: Gunakan hanya musik bebas royalti atau yang sudah Anda miliki lisensinya

> **Disclaimer:** AI-generated content tetap bisa mengandung kesalahan. Selalu review naskah dan fact-check report sebelum publishing. Pemilik channel bertanggung jawab penuh atas konten yang di-upload.

---

## Contributing

Contributions welcome! Please:
1. Fork repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

## Support

Repository: https://github.com/Qadri54/content-shorts-automation

For issues, bug reports, or feature requests, please open an issue on GitHub.
