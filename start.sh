#!/bin/sh
# start.sh — runner proses untuk satu container (POSIX sh, tanpa bash)
set -eu

log() { printf '%s %s\n' "[$(date -u +%H:%M:%S)]" "$*"; }

########################################
# 1) Muat .env lewat parser Node
#    (hindari `source .env`: nilai ber-spasi / ber-# / CRLF merusak shell)
########################################
if [ -f .env ]; then
  eval "$(node env-export.js)"
elif [ -f .env.example ]; then
  log "[WARN] .env belum ada. Jalankan 'npm install' agar dibuat dari .env.example."
fi

mkdir -p logs/n8n-standalone logs/n8n-main logs/n8n-worker logs/n8n-webhook \
         logs/cf-tunnel logs/vars-ui logs/redis logs/finapi logs/bot-wa

########################################
# 2) Normalisasi toggle
########################################
is_on() {
  case "${1:-}" in
    on|1|true|yes) return 0 ;;
    *) return 1 ;;
  esac
}

if is_on "${N8N_QUEUE_MODE:-off}"; then QUEUE_ON=1; else QUEUE_ON=0; fi

# ENABLE_REDIS kosong = ikut Queue Mode
if [ -z "${ENABLE_REDIS:-}" ]; then
  ENABLE_REDIS="$QUEUE_ON"
  export ENABLE_REDIS
fi

# ENABLE_N8N_WEBHOOK kosong = 0 (webhook ikut n8n-main)
if [ -z "${ENABLE_N8N_WEBHOOK:-}" ]; then
  ENABLE_N8N_WEBHOOK=0
  export ENABLE_N8N_WEBHOOK
fi

# Queue mode tanpa Redis = n8n gagal start. Paksa Redis ON dan beri peringatan.
# Hanya relevan kalau n8n aktif.
if [ "$QUEUE_ON" = "1" ] && [ "${ENABLE_N8N:-1}" != "0" ] && [ "$ENABLE_REDIS" != "1" ]; then
  log "[WARN] N8N_QUEUE_MODE=on butuh Redis. ENABLE_REDIS dipaksa 1."
  ENABLE_REDIS=1
  export ENABLE_REDIS
fi

if [ -z "${WEBHOOK_URL:-}" ]; then
  if [ "$QUEUE_ON" = "1" ] && [ "$ENABLE_N8N_WEBHOOK" = "1" ]; then
    export WEBHOOK_URL="${N8NWEBHOOK_URL:-${N8N_EDITOR_BASE_URL:-}}"
  else
    export WEBHOOK_URL="${N8N_EDITOR_BASE_URL:-}"
  fi
fi

export N8N_PORT="${N8N_PORT:-11100}"
export N8N_WEBHOOK_PORT="${N8N_WEBHOOK_PORT:-11101}"

########################################
# 2b) Mode pairing bot WhatsApp
#     PM2 tidak meneruskan stdin, jadi pairing harus jalan langsung
#     di console panel. Alur: set BOT_WA_PAIR=1 → restart → ketik nomor
#     → tautkan dari HP → set BOT_WA_PAIR=0 → restart.
########################################
if [ "${ENABLE_BOT_WA:-0}" = "1" ] && [ "${BOT_WA_PAIR:-0}" = "1" ]; then
  # Siap = package.json ada dan npm install bot-wa pernah selesai.
  # node_modules/.package-lock.json hanya ditulis npm setelah install sukses.
  if [ ! -f ./bot-wa/package.json ] || [ ! -f ./bot-wa/node_modules/.package-lock.json ]; then
    log "[WARN] BOT_WA_PAIR=1 diabaikan: bot-wa belum siap (ZIP belum diekstrak atau npm install belum selesai)."
    log "[WARN] Upload ZIP ke bot-wa/, set ENABLE_BOT_WA=1, jalankan npm install, lalu ulangi."
  else
    log "[INFO] Mode pairing: console panel diserahkan ke bot-wa."
    log "[INFO] Set BOT_WA_PAIR=0 setelah folder bot-wa/session/ berisi creds.json."
    cd ./bot-wa
    exec node index.js --pairing
  fi
fi

########################################
# 3) Info ringkas
########################################
[ -n "${CLOUDFLARE_TOKEN:-}" ] && log "[INFO] cloudflared: token detected" || true
log "[INFO] node  : $(node -v 2>/dev/null || echo unknown)"
log "[INFO] mode  : queue=$QUEUE_ON redis=$ENABLE_REDIS"
log "[INFO] ports : n8n=${N8N_PORT} webhook=${N8N_WEBHOOK_PORT} gowa=${GOWA_PORT:-11500} vars=${VARS_PORT:-11300}"

########################################
# 4) PM2 lokal
########################################
PM2="./node_modules/.bin/pm2"
if [ ! -x "$PM2" ]; then
  log "[PM2 ] installing local pm2…"
  npm install pm2 --no-audit --no-fund
fi
log "[PM2 ] version: $("$PM2" -v 2>/dev/null || echo unknown)"

########################################
# 5) Reset PM2 lama
########################################
"$PM2" delete all >/dev/null 2>&1 || true

########################################
# 6) Tentukan app yang dijalankan
########################################
CANDIDATES="vars-ui"

# n8n butuh binary hasil npm install (kondisional, lihat ENABLE_N8N)
if [ -x ./node_modules/.bin/n8n ]; then
  CANDIDATES="n8n $CANDIDATES"
else
  if [ "${ENABLE_N8N:-0}" = "1" ]; then
    log "[WARN] n8n diaktifkan tapi ./node_modules/.bin/n8n tidak ada → skip (jalankan npm install, cek ENABLE_N8N dan versi Node)"
  fi
fi

# gowa butuh binary hasil postinstall
if [ -x ./bin/gowa ]; then
  CANDIDATES="$CANDIDATES gowa"
else
  if is_on "${ENABLE_GOWA:-0}"; then log "[WARN] gowa diaktifkan tapi ./bin/gowa tidak ada → skip"; fi
fi

# redis butuh binary hasil postinstall
if [ -x ./bin/redis-server ]; then
  CANDIDATES="$CANDIDATES redis"
else
  if [ "$ENABLE_REDIS" = "1" ]; then log "[WARN] redis diaktifkan tapi ./bin/redis-server tidak ada → skip"; fi
fi

# cf-tunnel butuh token
if [ -n "${CLOUDFLARE_TOKEN:-}" ] && [ -x ./bin/cloudflared ]; then
  CANDIDATES="$CANDIDATES cf-tunnel"
fi

# finapi butuh venv hasil postinstall
if [ -x ./bin/finapi-venv/bin/python ] && [ -f ./vendor/finapi/backend/requirements.txt ]; then
  CANDIDATES="$CANDIDATES finapi"
else
  if [ "${ENABLE_FINAPI:-0}" = "1" ]; then
    log "[WARN] finapi diaktifkan tapi venv belum ada → skip (jalankan npm install)"
  fi
fi

# bot-wa butuh hasil ekstrak ZIP + npm install di dalam bot-wa/
# .package-lock.json = tanda npm install bot-wa selesai (bukan install separuh jalan)
if [ "${ENABLE_BOT_WA:-0}" = "1" ]; then
  if [ -f ./bot-wa/package.json ] && [ -f ./bot-wa/node_modules/.package-lock.json ]; then
    CANDIDATES="$CANDIDATES bot-wa"
  else
    log "[WARN] bot-wa diaktifkan tapi belum siap → skip (upload ZIP ke bot-wa/, lalu npm install)"
  fi
fi

contains() {
  case " $1 " in *" $2 "*) return 0 ;; *) return 1 ;; esac
}

APPS_LIST=""

if [ -n "${RUN_APPS:-}" ]; then
  # Override: hanya jalankan yang tertera (comma-separated)
  for name in $(printf '%s' "$RUN_APPS" | tr ',' ' '); do
    [ -z "$name" ] && continue
    if contains "$CANDIDATES" "$name"; then
      APPS_LIST="$APPS_LIST $name"
    else
      log "[WARN] '$name' tidak tersedia → skip"
    fi
  done
else
  for name in $CANDIDATES; do
    case "$name" in
      n8n)      flag="${ENABLE_N8N:-1}" ;;
      redis)    flag="$ENABLE_REDIS" ;;
      gowa)     flag="${ENABLE_GOWA:-1}" ;;
      vars-ui)  flag="${ENABLE_VARS:-1}" ;;
      cf-tunnel) flag="${ENABLE_TUNNEL:-1}" ;;
      finapi)   flag="${ENABLE_FINAPI:-0}" ;;
      bot-wa)   flag="${ENABLE_BOT_WA:-0}" ;;
      *)        flag=1 ;;
    esac
    if [ "$flag" = "1" ]; then
      APPS_LIST="$APPS_LIST $name"
    else
      log "[INFO] $name: disabled via .env"
    fi
  done
fi

if [ -z "$APPS_LIST" ]; then
  log "[WARN] Tidak ada app aktif. Menjalankan vars-ui saja."
  APPS_LIST=" vars-ui"
fi

# Ekspansi n8n → proses sesuai Queue Mode
EXPANDED=""
for name in $APPS_LIST; do
  if [ "$name" = "n8n" ]; then
    if [ "$QUEUE_ON" = "1" ]; then
      EXPANDED="$EXPANDED n8n-main n8n-worker"
      if [ "$ENABLE_N8N_WEBHOOK" = "1" ]; then
        EXPANDED="$EXPANDED n8n-webhook"
      fi
    else
      EXPANDED="$EXPANDED n8n-s"
    fi
  else
    EXPANDED="$EXPANDED $name"
  fi
done

# Rapikan jadi daftar koma
APPS=$(printf '%s' "$EXPANDED" | tr -s ' ' | sed 's/^ //; s/ $//; s/ /,/g')
log "[INFO] PM2 will start: $APPS"

########################################
# 7) Folder data kondisional
########################################
if [ "${ENABLE_GOWA:-0}" = "1" ]; then
  mkdir -p gowa
  chmod 700 gowa 2>/dev/null || true
fi
if [ "$ENABLE_REDIS" = "1" ]; then
  mkdir -p "${REDIS_DATA_DIR:-redis/data}"
fi

########################################
# 8) Start PM2
########################################
if ! "$PM2" start ecosystem.config.js --only "$APPS" --update-env; then
  log "[ERR ] PM2 gagal start apps: $APPS"
  exit 1
fi

########################################
# 9) pm2-logrotate
########################################
PM2_HOME="${HOME:-/home/container}/.pm2"
if [ ! -d "${PM2_HOME}/modules/pm2-logrotate" ]; then
  "$PM2" install pm2-logrotate >/dev/null 2>&1 || true
fi
"$PM2" set pm2-logrotate:max_size 5M >/dev/null 2>&1 || true
"$PM2" set pm2-logrotate:retain 7 >/dev/null 2>&1 || true
"$PM2" set pm2-logrotate:compress false >/dev/null 2>&1 || true
"$PM2" set pm2-logrotate:workerInterval 60 >/dev/null 2>&1 || true
"$PM2" set pm2-logrotate:rotateInterval '0 0 * * *' >/dev/null 2>&1 || true

########################################
# 10) Tahan proses utama & teruskan log
#     `pm2 logs` bersifat follow; kalau daemon mati, proses ini keluar
#     dan container restart sesuai kebijakan panel.
########################################
# LOG_TARGET hanya dipakai kalau prosesnya memang ikut dijalankan.
LOG_ARGS=""
if [ -n "${LOG_TARGET:-}" ]; then
  case ",${APPS}," in
    *",${LOG_TARGET},"*) LOG_ARGS="$LOG_TARGET" ;;
    *) log "[INFO] LOG_TARGET=$LOG_TARGET tidak aktif, menampilkan semua log" ;;
  esac
fi

# shellcheck disable=SC2086
exec "$PM2" logs --raw --lines "${BOT_LOG_LINES:-200}" $LOG_ARGS
