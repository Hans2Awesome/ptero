# n8n + GOWA bundle (single container)

Satu container menjalankan beberapa proses lewat PM2. Entry point: `start.sh`.

## Komponen

| Proses PM2 | Fungsi | Syarat aktif |
|---|---|---|
| `n8n-s` | n8n mode biasa (default) | `ENABLE_N8N=1` + `N8N_QUEUE_MODE=off` |
| `n8n-main` / `n8n-worker` / `n8n-webhook` | n8n queue mode | `ENABLE_N8N=1` + `N8N_QUEUE_MODE=on` |
| `gowa` | WhatsApp REST API | `ENABLE_GOWA=1` + `./bin/gowa` |
| `redis` | Valkey/Redis lokal | `ENABLE_REDIS=1` + `./bin/redis-server` |
| `vars-ui` | Panel edit `.env` + backup workflow | `ENABLE_VARS=1` |
| `finapi` | FastAPI backend AppFinanceIndv | `ENABLE_FINAPI=1` + venv |
| `bot-wa` | Bot WhatsApp (Zapo/Neoxr) | `ENABLE_BOT_WA=1` + ZIP di `bot-wa/` |
| `cf-tunnel` | Cloudflare Tunnel | `CLOUDFLARE_TOKEN` + `./bin/cloudflared` |

## Setup di panel

1. Node.js **v22.16 atau lebih baru**. n8n dipasang kondisional (lihat bawah).
2. Upload seluruh isi folder ini ke `/home/container` (atau `git clone`).
3. CMD_RUN: **`npm start`** (bukan `npm install`). Panel menjalankan
   `/usr/local/bin/${CMD_RUN}`, jadi `npm start` valid dan `sh start.sh` tidak.
4. Start server. `npm install` akan menjalankan `postinstall.js` yang:
   - membuat `.env` dari `.env.example` bila belum ada, dengan secret acak
     (`N8N_ENCRYPTION_KEY`, `REDIS_PASSWORD`, `VARUI_PASS`, `APP_BASIC_AUTH`,
     `SECRET_KEY` finapi) dan mencetak `VARUI_USER` / `VARUI_PASS` ke console;
   - memasang `n8n` **hanya jika** `ENABLE_N8N=1`;
   - mengunduh `bin/gowa`, `bin/redis-server` (jika `ENABLE_REDIS=1`),
     `bin/cloudflared`;
   - menulis `redis/redis.conf`;
   - menyiapkan venv Python untuk `finapi`.

## n8n opsional (Node v23 vs v24)

`n8n` **tidak** ada di `dependencies` `package.json`. `postinstall.js` yang
memutuskan, karena `npm install` tidak bisa membaca `.env` di tengah resolusi
dependency.

| `ENABLE_N8N` | Node | Hasil |
|---|---|---|
| `0` | apa pun | n8n tidak dipasang, `npm install` tidak menyentuh registry untuk n8n |
| `1` | 22 / 23 | memasang `n8n@2.35.7` (`engines >=22.22`) |
| `1` | 24+ | memasang `n8n@2.45.6` (`engines >=24.0.0`) |
| `1` | < 22 | gagal dengan peringatan, n8n dilewati |

Alur upgrade saat Node v24 disetujui penyewa:

1. Ubah satu baris di `.env`: `ENABLE_N8N=0` → `ENABLE_N8N=1`.
2. Minta panel memakai Node v24, lalu jalankan `npm install` sekali
   (atau restart server, karena start panel menjalankan `npm install`).
3. `postinstall.js` memasang `n8n@2.45.6` otomatis, `start.sh` ikut
   menambahkan proses n8n ke PM2.

Tidak perlu mengubah `package.json`.

`start.sh` juga menjaga: kalau `ENABLE_N8N=1` tapi
`./node_modules/.bin/n8n` tidak ada, proses n8n dilewati dengan peringatan,
bukan membuat seluruh start gagal.

Jangan pakai seri n8n 1.x: sudah tidak dipatch (CVE-2025-68613).

## File yang TIDAK masuk repo

`.gitignore` mengecualikan file yang tidak boleh di-push:

| Path | Alasan |
|---|---|
| `.env`, `vendor/finapi/.env` | kredensial. Dibuat ulang dari `.env.example` |
| `vendor/finapi/*.sqlite3` | data pribadi. Skema dibuat ulang oleh migrasi |
| `bin/`, `logs/`, `node_modules/` | hasil unduhan / runtime |
| `bot-wa/` | kode bot + secret milik penjual, diupload manual |

Karena `.env` diabaikan, clone baru **wajib** menjalankan `npm install` sekali
supaya `.env` terbentuk. Kalau punya `.env` lama, upload manual.

Semua source backend AppFinanceIndv (`vendor/finapi/backend/app/`,
`vendor/finapi/finance_core/`, `requirements.txt`) ikut ter-track.

## Login n8n

n8n 1.0+ **tidak lagi memakai** `N8N_BASIC_AUTH_*`. Buat akun owner lewat
editor saat pertama kali dibuka (`/setup`).

## Ganti kredensial wajib

Kalau `.env` dibuat otomatis, secret sudah acak. Yang masih perlu diisi manual
karena tidak bisa digenerate:

- `CLOUDFLARE_TOKEN` (tunnel tidak jalan tanpa ini)
- `DB_POSTGRESDB_*` (hanya untuk queue mode)
- `TB1_TELEGRAM_BOT_TOKEN` / `TB2_TELEGRAM_BOT_TOKEN` (bot nonaktif tanpa token)
- `N8N_HOST`, `N8N_EDITOR_BASE_URL`, `CORS_ORIGINS` (sesuaikan domain)
- `vendor/finapi/.env`: `ENVIRONMENT=production` bila sudah publik, dan
  `CORS_ORIGINS` sesuai origin app

Jangan mengganti `N8N_ENCRYPTION_KEY` setelah n8n menyimpan credential: nilai
lama tidak akan bisa didekripsi.

## Queue mode

Butuh Redis **dan** Postgres. Redis ditulis dengan `maxmemory-policy noeviction`
karena BullMQ bisa kehilangan job jika key dievakuasi.

```
N8N_QUEUE_MODE=on
ENABLE_REDIS=1
```

Tanpa `ENABLE_REDIS=1`, `start.sh` memaksa Redis ON dan memberi peringatan.

## FinAPI (backend AppFinanceIndv)

Berjalan sebagai proses PM2 terpisah di container yang sama.

```
vendor/finapi/
  backend/app/         FastAPI (routes, auth, models)
  backend/requirements.txt
  finance_core/        domain bersama (import dari root repo)
  bot04.sqlite3        database (data ikut)
  .env                 SECRET_KEY, DATABASE_PATH, CORS
```

Cara kerja:

1. `postinstall.js` mendeteksi `python3` (>=3.11). Kalau tidak ada atau venv-nya
   gagal (mis. tidak ada `ensurepip`, atau wheel glibc tidak cocok di image musl),
   ia mengunduh **python-build-standalone** ke `bin/python-build/` — tanpa root.
2. Venv dibuat di `bin/finapi-venv/`, dependency dipasang dari
   `backend/requirements.txt`. Hash requirements disimpan sebagai marker, jadi
   `npm install` berikutnya tidak memasang ulang.
3. PM2 menjalankan: `bin/finapi-venv/bin/python -m uvicorn backend.app.main:app`
   dengan `cwd=vendor/finapi` dan `interpreter: 'none'`.

Port default `11011` (internal, `127.0.0.1`). Tunnel di Cloudflare harus menunjuk
`http://localhost:11011`. Contoh yang dipakai:
`api-finindv.nikahbos.web.id -> http://localhost:11011`.

Aplikasi mobile (APK) memakai base URL:
`https://api-finindv.nikahbos.web.id`

## Bot WhatsApp (`bot-wa/`)

Kode bot **tidak** ada di repo ini. `bot-wa/` masuk `.gitignore`. Panel harus
mendapat ZIP-nya secara manual.

### Upload dan aktifkan

1. Upload ZIP bot ke `bot-wa/` di panel, nama bebas, misal
   `bot-wa/NusantaraProject - 01.zip`.
2. Set di `.env`:

   ```
   ENABLE_BOT_WA=1
   ```

3. Jalankan `npm install` (atau restart server). `postinstall.js` akan:
   - mengekstrak ZIP ke `bot-wa/` (menolak entry yang keluar folder);
   - menjalankan `npm install --ignore-scripts` di dalam `bot-wa/`
     (1124 paket, sekitar 1 GB);
   - menjalankan `npm rebuild canvas canvacord` untuk modul yang butuh
     skrip native.

Kalau `bot-wa/` tidak ada, kosong, atau `ENABLE_BOT_WA=0`, semuanya dilewati.
Tidak ada error, `npm install` tetap selesai normal.

### Pairing sekali (wajib)

PM2 tidak meneruskan `stdin`, jadi pairing tidak bisa lewat PM2. Alurnya:

1. `.env`: `BOT_WA_PAIR=1`, lalu restart server.
   `start.sh` menyerahkan console panel langsung ke bot.
2. Console menampilkan `› Nomor WhatsApp:`. Ketik nomor berawalan `62`,
   misal `6285257129838`. Kode pairing muncul di console.
3. Tautkan dari HP: WhatsApp → Perangkat tertaut → Tautkan perangkat →
   Tautkan dengan nomor telepon.
4. Setelah `bot-wa/session/creds.json` terbentuk, ubah `BOT_WA_PAIR=0`
   dan restart. Bot sekarang dijalankan PM2 seperti proses lain.

Session tersimpan di `bot-wa/session/` (gitignored, jangan dihapus: menghapus
artinya pairing ulang).

### Syarat dari pembuat script

- **Node 22** (tertulis di `MIGRASI_ZAPO.md`; `engines` di `bot-wa/package.json`
  adalah `^22.12.0 || >=24.0.0`). Node 23 di luar range: pakai 22 atau 24.
- **IP server dan nomor bot harus terdaftar di database penjual.** Dua gate:
  - L1 saat boot: `start.js` mengambil IP publik lalu memanggil
    `https://db.apiastra.biz.id/api`. IP tidak terdaftar → bot `exit 1`
    sebelum pairing.
  - L2 saat pairing: `function/pairing.js` memverifikasi nomor WhatsApp.
    Nomor tidak terdaftar → `exit 1`.

  Daftarkan IP panel dan nomor bot ke AstraHost (kontak di script:
  `085183329477`) sebelum `ENABLE_BOT_WA=1`.
- Dashboard bot memakai port internal `5000` (hardcoded di `index.js`). Tidak
  bentrok dengan finapi `11011`, vars `11300`, gowa `11500`.
- Install dependency bot memakai `--ignore-scripts` lalu `npm rebuild canvas
  canvacord`. Alasannya: `better-sqlite3@13` tidak punya skrip install sendiri,
  sehingga npm menjalankan `node-gyp` default dan gagal di container tanpa
  `make`/`gcc`. Prebuilt N-API `better-sqlite3`, `sharp`, dan `@roamhq/wrtc`
  sudah ikut di paket, jadi tetap jalan.

### Catatan keamanan

`bot-wa/settings.js` berisi token GitHub, API key Pterodactyl (`ptla_`/`ptlc_`),
dan belasan API key pihak ketiga. Itu sebabnya folder ini tidak di-push.
`start.js`, `handler.js`, dan `lib/ai.js` di dalam ZIP juga ter-obfuscate dan
tidak bisa diaudit. Jangan pakai `run.js` sebagai entry panel: file itu
menjalankan `spawn('bash')`.

## Token Cloudflare Tunnel

Token disimpan di **root `.env`**, baris `CLOUDFLARE_TOKEN=`. Ingress/hostname
dikonfigurasi di dashboard Cloudflare (Zero Trust → Networks → Tunnels), bukan
di file lokal, karena tunnel dijalankan mode token.

Ambil token dari: Zero Trust → Networks → Tunnels → pilih tunnel →
Configure → bagian install connector (string panjang `eyJ...`).

Catatan:
- `.env` **tidak** ikut ter-push ke GitHub (gitignore). Token harus diisi manual
  di panel, atau lewat variabel `CLOUDFLARE_TOKEN` dari panel.
- `cf-tunnel` hanya jalan kalau `CLOUDFLARE_TOKEN` terisi **dan**
  `bin/cloudflared` ada (diunduh postinstall.js).
- Semua hostname tunnel memakai satu token. Kalau `api-finindv.nikahbos.web.id`
  dibuat di tunnel yang sama dengan `n8n.zieghart.web.id`, cukup satu token.

## Verifikasi finapi

Verifikasi:

```
curl http://127.0.0.1:11011/
{"status":"online","app":"Personal Finance API","version":"1.0.0","docs_url":"/docs"}
```

## Catatan n8n 2.x

- `N8N_RUNNERS_ENABLED` deprecated (runner aktif by default).
- `N8N_BLOCK_ENV_ACCESS_IN_NODE` default `true`; `.env` di sini set `false`
  agar `$env` tetap bisa dipakai di Code node.
- `N8N_DEFAULT_BINARY_DATA_MODE=default` dihapus; dipakai `filesystem`.
- `OFFLOAD_MANUAL_EXECUTIONS_TO_WORKERS` dihapus.

## Struktur

```
start.sh              entry point (POSIX sh)
env-export.js         parser .env, dipakai start.sh + postinstall.js
postinstall.js        unduh binari, render redis.conf, siapkan venv finapi,
                      ekstrak ZIP bot-wa + npm install kondisional
ecosystem.config.js   definisi proses PM2
vars-server.js        API + UI edit .env
public/index.html     UI vars-ui
vendor/finapi/        backend FastAPI AppFinanceIndv (vendored)
bot-wa/               bot WhatsApp, diupload manual (gitignore)
bin/                  binari hasil unduhan (gitignore)
logs/                 log per proses
```
