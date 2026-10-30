const path = require('path');

const env = { ...process.env };
const CF_TOKEN = process.env.CLOUDFLARE_TOKEN || process.env.CLOUDFLARE_TOKEN_VARS;
const WEB1_PORT = process.env.WEB1_PORT || '11410';
const WEB1_HOST = process.env.WEB1_HOST || '0.0.0.0';

const LOG_ROOT = process.env.LOG_ROOT || path.join(__dirname, 'logs');
const logCfg = (name) => ({
  out_file: path.join(LOG_ROOT, name, 'out.log'),
  error_file: path.join(LOG_ROOT, name, 'err.log'),
  merge_logs: false,
});

const runApps = String(process.env.RUN_APPS || '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);
const wants = (name) => runApps.length === 0 || runApps.includes(name);

module.exports = {
  apps: [
    // --- n8n standalone (mode biasa, tanpa queue) ---
    {
      name: 'n8n-s',
      script: './node_modules/.bin/n8n',
      args: 'start',
      env: {
        ...env,
        EXECUTIONS_MODE: 'regular',
        N8N_LOG_LEVEL: process.env.N8N_LOG_LEVEL || 'info',
      },
      ...logCfg('n8n-standalone'),
      autorestart: true,
      restart_delay: 5000,
      max_memory_restart: process.env.N8N_MAIN_MAX_MEMORY || '1200M',
    },

    // --- n8n main (UI/API/webhook) ---
    {
      name: 'n8n-main',
      script: './node_modules/.bin/n8n',
      args: 'start',
      env: {
        ...env,
        EXECUTIONS_MODE: 'queue',
      },
      ...logCfg('n8n-main'),
      autorestart: true,
      restart_delay: 5000,
      max_memory_restart: process.env.N8N_MAIN_MAX_MEMORY || '1200M',
    },

    // --- n8n worker ---
    // Health check DIMATIKAN: beberapa instance fork tidak bisa bind port yang sama.
    {
      name: 'n8n-worker',
      script: './node_modules/.bin/n8n',
      args: `worker --concurrency=${process.env.N8N_WORKER_CONCURRENCY || 4}`,
      instances: parseInt(process.env.N8N_WORKERS || '1', 10),
      exec_mode: 'fork',
      env: {
        ...env,
        EXECUTIONS_MODE: 'queue',
        QUEUE_HEALTH_CHECK_ACTIVE: 'false',
      },
      ...logCfg('n8n-worker'),
      autorestart: true,
      restart_delay: 5000,
      max_memory_restart: process.env.N8N_WORKER_MAX_MEMORY || '900M',
    },

    // --- (opsional) n8n webhook processor terpisah ---
    {
      name: 'n8n-webhook',
      script: './node_modules/.bin/n8n',
      args: 'webhook',
      env: {
        ...env,
        EXECUTIONS_MODE: 'queue',
        N8N_PORT: process.env.N8N_WEBHOOK_PORT || '11101',
      },
      ...logCfg('n8n-webhook'),
      autorestart: true,
      restart_delay: 5000,
      max_memory_restart: process.env.N8N_MAIN_MAX_MEMORY || '1200M',
    },

    // --- gowa (kondisional: binary harus ada) ---
    ...(process.env.ENABLE_GOWA === '1' && wants('gowa')
      ? [
          {
            name: 'gowa',
            script: './bin/gowa',
            args: `rest --port=${process.env.GOWA_PORT || 11500}`,
            cwd: __dirname,
            ...logCfg('gowa'),
            env,
            autorestart: true,
            restart_delay: 3000,
            max_memory_restart: process.env.GOWA_MAX_MEMORY || '400M',
          },
        ]
      : []),

    // --- redis (kondisional: binary harus ada) ---
    ...(process.env.ENABLE_REDIS === '1' && wants('redis')
      ? [
          {
            name: 'redis',
            script: path.join(__dirname, 'bin', 'redis-server'),
            args: path.join(__dirname, 'redis', 'redis.conf'),
            cwd: __dirname,
            ...logCfg('redis'),
            env,
            autorestart: true,
            restart_delay: 3000,
            max_memory_restart: process.env.REDIS_MAX_MEMORY_RESTART || '1200M',
          },
        ]
      : []),

    // --- vars-ui (.env editor) ---
    {
      name: 'vars-ui',
      script: 'node',
      args: 'vars-server.js',
      cwd: __dirname,
      ...logCfg('vars-ui'),
      env,
      autorestart: true,
      restart_delay: 3000,
      max_memory_restart: '200M',
    },

    // --- finapi (FastAPI backend AppFinanceIndv) ---
    // interpreter 'none': script adalah binary/venv python, bukan file JS.
    ...(process.env.ENABLE_FINAPI === '1'
      && require('fs').existsSync(path.join(__dirname, 'bin', 'finapi-venv', 'bin', 'python'))
      && wants('finapi')
      ? [
          {
            name: 'finapi',
            interpreter: 'none',
            script: path.join(__dirname, 'bin', 'finapi-venv', 'bin', 'python'),
            args: [
              '-m', 'uvicorn', 'backend.app.main:app',
              '--host', process.env.FINAPI_HOST || '127.0.0.1',
              '--port', String(process.env.FINAPI_PORT || 11600),
              '--proxy-headers',
            ],
            cwd: path.join(__dirname, 'vendor', 'finapi'),
            ...logCfg('finapi'),
            env: {
              ...env,
              PYTHONUNBUFFERED: '1',
              PYTHONDONTWRITEBYTECODE: '1',
            },
            autorestart: true,
            restart_delay: 3000,
            max_memory_restart: process.env.FINAPI_MAX_MEMORY || '250M',
          },
        ]
      : []),

    // --- website-1 (Next.js, kondisional: folder harus ada) ---
    ...(require('fs').existsSync(path.join(__dirname, 'web', '1', 'package.json')) && wants('website-1')
      ? [
          {
            name: 'website-1',
            cwd: './web/1',
            script: 'node_modules/next/dist/bin/next',
            args: ['start', '-p', String(WEB1_PORT), '-H', WEB1_HOST],
            ...logCfg('website-1'),
            env: {
              ...env,
              NODE_ENV: 'production',
              NEXT_TELEMETRY_DISABLED: env.NEXT_TELEMETRY_DISABLED || '1',
              BASE_URL: env.WEB1_BASE_URL || '',
            },
            autorestart: true,
            restart_delay: 3000,
            max_memory_restart: '512M',
          },
        ]
      : []),

    // --- cloudflare tunnel (aktif kalau token + binary ada) ---
    // Token dikirim lewat env TUNNEL_TOKEN, bukan argumen: argumen proses
    // terlihat di `ps` oleh semua user di container.
    ...(CF_TOKEN && require('fs').existsSync(path.join(__dirname, 'bin', 'cloudflared'))
      ? [
          {
            name: 'cf-tunnel',
            script: './bin/cloudflared',
            args: 'tunnel --no-autoupdate run',
            cwd: __dirname,
            ...logCfg('cf-tunnel'),
            env: { ...env, TUNNEL_TOKEN: CF_TOKEN },
            autorestart: true,
            restart_delay: 5000,
          },
        ]
      : []),
  ],
};
