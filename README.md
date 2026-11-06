# Yt Shorts Factory

Sistem produksi konten YouTube Shorts otomatis yang menggunakan orkestrasi AI untuk menghasilkan video fakta unik berkualitas tinggi tanpa biaya langganan. Project ini memanfaatkan **CrewAI** sebagai framework orkestrasi multi-agent, **Gemini Flash** sebagai model AI generatif, dan tools video processing lokal untuk menghasilkan video siap upload.

## Orkestrasi AI dengan CrewAI

Project ini menggunakan **CrewAI** untuk mengatur tiga AI agent yang bekerja secara sekuensial dalam pipeline produksi konten:

1. **Scriptwriter Agent**: Agent pertama yang bertugas memilih topik dari daftar sub-tema dan menulis naskah 140-160 kata. Agent ini memahami tone channel, target durasi, dan struktur narasi yang engaging.

2. **Fact-Checker Agent**: Menerima output dari Scriptwriter dan memverifikasi setiap klaim faktual. Agent ini dapat mengoreksi, menghapus klaim yang tidak terverifikasi, atau menolak naskah sepenuhnya jika terlalu banyak masalah. Jika ditolak, sistem otomatis retry dengan topik berbeda (maksimal 3x).

3. **Visual & SEO Director Agent**: Agent terakhir yang memecah naskah menjadi scene-by-scene breakdown, menentukan keyword B-roll untuk setiap scene, membuat metadata SEO (judul/deskripsi/tags), dan memilih mood musik. Output agent ini menjadi blueprint lengkap untuk rendering video.

Setiap agent memiliki role, goal, dan tools spesifik yang didefinisikan dalam CrewAI, memastikan setiap tahap produksi dikerjakan oleh "spesialis" yang tepat.

---

## Table of Contents

1. [Project Summary](#project-summary)
2. [Credential Setup](#credential-setup) *(akan diupdate)*
3. [Installation & Setup](#installation--setup)
4. [Usage](#usage)
5. [Output Structure](#output-structure)
6. [Customization](#customization)

---

## Project Summary

**Yt Shorts Factory** adalah mesin konten YouTube Shorts otomatis yang menggabungkan:

- **AI Multi-Agent System (CrewAI + Gemini Flash)**: Menulis naskah, fact-checking, dan menyusun storyboard
- **Text-to-Speech (Edge-TTS)**: Voiceover bahasa Indonesia dengan suara natural
- **Video Asset Management (Pixabay API)**: Download B-roll otomatis dengan prioritas format portrait 9:16
- **Subtitle Generation (faster-whisper)**: Subtitle per-kata dengan timing presisi
- **Video Rendering (FFmpeg)**: Encoding H.264/AAC dengan audio normalization dan ducking

### Alur Produksi per Video

1. **Scriptwriter** memilih 1 fakta dari sub-tema yang sedang dirotasi, lalu menulis naskah 140–160 kata
2. **Fact-Checker** memeriksa setiap klaim: koreksi, hapus, atau tolak. Kalau ditolak, sistem otomatis mencari topik lain (maksimal 3x)
3. **Visual & SEO Director** memecah naskah menjadi 12–15 scene + keyword B-roll + judul/deskripsi/tags + mood musik
4. Voiceover per scene (id-ID-ArdiNeural). Kecepatan bicara disesuaikan otomatis agar durasi 50–59 detik
5. B-roll diambil dari **Pixabay Video API** (prioritas portrait 9:16, otomatis center-crop jika horizontal)
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

### 2. Setup Pixabay API Key

1. Buka [Pixabay API](https://pixabay.com/api/docs/)
2. Daftar/login ke akun Pixabay
3. Scroll ke bagian **"Search Videos"** untuk melihat API key Anda
4. Copy API key
5. Paste ke file `.env`:
   ```
   PIXABAY_API_KEY=your_api_key_here
   ```

### 3. YouTube Authorization (Optional - untuk auto-upload)

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

```powershell
# Aktifkan virtual environment terlebih dahulu
.\.venv\Scripts\Activate.ps1

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
```powershell
python scripts/setup_youtube.py
```

> **Catatan:** Jika app masih dalam mode "Testing", hanya test users yang ditambahkan di OAuth consent screen yang bisa login. Untuk production, submit app untuk verification di Google Cloud Console.

#### E. Verifikasi Setup

Setelah authentication berhasil, test upload:
```powershell
python main.py --count 1 --upload
```

---

## Installation & Setup

```powershell
cd yt-shorts-factory
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # lalu isi GEMINI_API_KEY & PIXABAY_API_KEY
python main.py --check      # verifikasi semua komponen
```

FFmpeg wajib ada di PATH (`winget install Gyan.FFmpeg`).

---

## Usage

```powershell
python main.py                          # 1 video
python main.py --count 3                # 3 video berurutan (jeda 5 detik)
python main.py --sub-theme "Luar Angkasa"
python main.py --blueprint-only         # naskah + metadata saja, tanpa render
python main.py --count 3 --cleanup      # hapus file sementara setelah render
python main.py --verbose                # tampilkan proses agent
```

---

## Output Structure

`data/output/<tanggal>_<judul>/`:
- `<judul>.mp4`: video final siap upload
- `metadata.txt`: judul, deskripsi, tags (tinggal copy-paste) + ringkasan fact-check
- `blueprint.json`, `factcheck.json`: hasil agent
- `subtitles/subtitles.srt`: bisa diupload sebagai CC

---

## Customization

- `data/channel.json`: nama channel, sub-tema, aturan konten, hashtag, suara
- `data/music/<mood>/`: musik latar bebas royalti (lihat `data/music/README.txt`)
- `data/fonts/`: taruh file font .ttf custom, lalu set `SUBTITLE_FONT` di `.env`
- `.env`: model Gemini, durasi target, ukuran subtitle, volume musik, dll.

> **Penting:** AI tetap bisa salah. Selalu baca bagian *HASIL FACT-CHECK* di `metadata.txt` dan tonton videonya sebelum upload.
