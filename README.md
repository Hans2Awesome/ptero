# n8n + GOWA bundle (single container)

Satu container menjalankan beberapa proses lewat PM2. Entry point: `start.sh`.

## Komponen

| Proses PM2 | Fungsi | Syarat aktif |
|---|---|---|
| `n8n-s` | n8n mode biasa (default) | `N8N_QUEUE_MODE=off` |
| `n8n-main` / `n8n-worker` / `n8n-webhook` | n8n queue mode | `N8N_QUEUE_MODE=on` |
| `gowa` | WhatsApp REST API | `ENABLE_GOWA=1` + `./bin/gowa` |
| `redis` | Valkey/Redis lokal | `ENABLE_REDIS=1` + `./bin/redis-server` |
| `vars-ui` | Panel edit `.env` + backup workflow | `ENABLE_VARS=1` |
| `finapi` | FastAPI backend AppFinanceIndv | `ENABLE_FINAPI=1` + venv |
| `cf-tunnel` | Cloudflare Tunnel | `CLOUDFLARE_TOKEN` + `./bin/cloudflared` |

## Setup di panel

1. Node.js **v24** (n8n 2.45.6 butuh `>=24.0.0`).
2. Upload seluruh isi folder ini ke `/home/container` (atau `git clone`).
3. CMD_RUN: **`npm start`** (bukan `npm install`). Panel menjalankan
   `/usr/local/bin/${CMD_RUN}`, jadi `npm start` valid dan `sh start.sh` tidak.
4. Start server. `npm install` akan menjalankan `postinstall.js` yang:
   - membuat `.env` dari `.env.example` bila belum ada, dengan secret acak
     (`N8N_ENCRYPTION_KEY`, `REDIS_PASSWORD`, `VARUI_PASS`, `APP_BASIC_AUTH`,
     `SECRET_KEY` finapi) dan mencetak `VARUI_USER` / `VARUI_PASS` ke console;
   - mengunduh `bin/gowa`, `bin/redis-server` (jika `ENABLE_REDIS=1`),
     `bin/cloudflared`;
   - menulis `redis/redis.conf`;
   - menyiapkan venv Python untuk `finapi`.

Jika Node belum bisa v24, turunkan `n8n` di `package.json` ke `2.35.7`
(butuh `>=22.22`). Jangan pakai seri 1.x: sudah tidak dipatch.

## File yang TIDAK masuk repo

`.gitignore` mengecualikan file yang tidak boleh di-push:

| Path | Alasan |
|---|---|
| `.env`, `vendor/finapi/.env` | kredensial. Dibuat ulang dari `.env.example` |
| `vendor/finapi/*.sqlite3` | data pribadi. Skema dibuat ulang oleh migrasi |
| `bin/`, `logs/`, `node_modules/` | hasil unduhan / runtime |

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

Port default `11600` (internal, `127.0.0.1`). Karena panel hanya memetakan
`SERVER_PORT`, akses dari luar lewat cloudflared: tambahkan hostname di tunnel
yang menunjuk `http://127.0.0.1:11600`.

Ganti `SECRET_KEY`, `ENVIRONMENT`, dan `CORS_ORIGINS` di `vendor/finapi/.env`
sebelum dipakai publik. `ENVIRONMENT=production` mewajibkan `SECRET_KEY` >= 32
karakter.

Verifikasi:

```
curl http://127.0.0.1:11600/
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
postinstall.js        unduh binari, render redis.conf, siapkan venv finapi
ecosystem.config.js   definisi proses PM2
vars-server.js        API + UI edit .env
public/index.html     UI vars-ui
vendor/finapi/        backend FastAPI AppFinanceIndv (vendored)
bin/                  binari hasil unduhan (gitignore)
logs/                 log per proses
```
