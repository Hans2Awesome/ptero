/**
 * vars-server.js (v4)
 * - CRUD .env (add/edit/delete)
 * - Backup/Restore workflow n8n (JSON)
 * - Restart rolling (n8n -> gowa -> vars-ui) dengan env .env terbaru
 * Auth: Basic (VARUI_USER / VARUI_PASS)
 */
const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFile } = require('child_process');

const APP_PORT = process.env.VARUI_PORT || process.env.VARS_PORT || 11300;
const AUTH_USER = process.env.VARUI_USER || '';
const AUTH_PASS = process.env.VARUI_PASS || '';

if (!AUTH_USER || !AUTH_PASS) {
  console.error('[vars-ui] VARUI_USER / VARUI_PASS wajib diisi. Keluar.');
  process.exit(1);
}

const DOTENV_PATH = path.resolve(process.cwd(), '.env');
const PM2_BIN = path.resolve(process.cwd(), './node_modules/.bin/pm2');
const N8N_CLI = path.resolve(process.cwd(), './node_modules/.bin/n8n');
const BACKUP_DIR = path.resolve(process.cwd(), 'backups');
if (!fs.existsSync(BACKUP_DIR)) fs.mkdirSync(BACKUP_DIR, { recursive: true });

// -------- Auth (timing-safe, tanpa dependensi tambahan) --------
function safeEqual(a, b) {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
}
function parseBasic(header) {
  if (!header || !/^basic\s+/i.test(header)) return null;
  const decoded = Buffer.from(header.replace(/^basic\s+/i, '').trim(), 'base64').toString('utf8');
  const idx = decoded.indexOf(':');
  if (idx < 0) return null;
  return { name: decoded.slice(0, idx), pass: decoded.slice(idx + 1) };
}
function auth(req, res, next) {
  const c = parseBasic(req.headers.authorization);
  if (!c || !safeEqual(c.name, AUTH_USER) || !safeEqual(c.pass, AUTH_PASS)) {
    res.set('WWW-Authenticate', 'Basic realm="vars-ui"');
    return res.status(401).send('Authentication required.');
  }
  next();
}

// -------- .env helpers --------
const KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

function parseDotenvContent(content) {
  const lines = [];
  content.split(/\r?\n/).forEach((raw) => {
    if (raw.trim() === '') return lines.push({ type: 'blank', raw });
    if (/^\s*#/.test(raw)) return lines.push({ type: 'comment', raw });
    const m = raw.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (m) {
      const key = m[1];
      let value = m[2] || '';
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      } else {
        // Nilai tanpa kutip: komentar inline hanya jika didahului spasi.
        // Harus sama dengan parser di env-export.js.
        value = value.replace(/\s+#.*$/, '').trim();
      }
      return lines.push({ type: 'kv', key, value, raw });
    }
    lines.push({ type: 'other', raw });
  });
  return { lines };
}
function readEnvFile() {
  let content = '';
  try { content = fs.readFileSync(DOTENV_PATH, 'utf8'); } catch { content = ''; }
  return parseDotenvContent(content);
}
function serializeDotenv(lines) {
  return lines.map((l) => {
    if (l.type === 'kv') {
      // Kutip nilai yang ber-spasi / ber-karakter khusus agar tidak rusak saat di-parse ulang.
      const needsQuote = /[\s#'"\\$`]/.test(l.value);
      const v = needsQuote ? JSON.stringify(l.value) : l.value;
      return `${l.key}=${v}`;
    }
    return l.raw;
  }).join('\n') + '\n';
}
function writeEnvFile(modify) {
  const { lines } = readEnvFile();
  const ctx = { lines };
  modify(ctx);
  const out = serializeDotenv(ctx.lines);
  const tmp = `${DOTENV_PATH}.tmp`;
  fs.writeFileSync(tmp, out, { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(tmp, DOTENV_PATH);
}
function buildEnvOverlayFromDotenv() {
  const { lines } = readEnvFile();
  const obj = {};
  for (const l of lines) if (l.type === 'kv') obj[l.key] = l.value;
  return obj;
}

// -------- shell helpers --------
function run(bin, args, opts = {}) {
  return new Promise((resolve, reject) => {
    execFile(bin, args, { cwd: process.cwd(), timeout: 120000, ...opts }, (err, stdout, stderr) => {
      if (err) return reject(new Error((stderr || '').trim() || err.message));
      resolve({ stdout, stderr });
    });
  });
}

// Nama proses PM2 yang benar-benar jalan, mengikuti mode aktif.
function activeProcessNames() {
  const overlay = buildEnvOverlayFromDotenv();
  const names = [];
  if (overlay.ENABLE_N8N !== '0') {
    const queueOn = /^(on|1|true|yes)$/i.test(overlay.N8N_QUEUE_MODE || 'off');
    if (queueOn) {
      names.push('n8n-main', 'n8n-worker');
      if (overlay.ENABLE_N8N_WEBHOOK === '1') names.push('n8n-webhook');
    } else {
      names.push('n8n-s');
    }
  }
  if (overlay.ENABLE_GOWA === '1') names.push('gowa');
  if (overlay.ENABLE_FINAPI === '1') names.push('finapi');
  if (overlay.ENABLE_BOT_WA === '1') names.push('bot-wa');
  names.push('vars-ui');
  return names;
}

async function n8nExportAll(outFile) {
  const tries = [
    ['export:workflow', '--all', `--output=${outFile}`],
    ['export:workflows', '--all', `--output=${outFile}`],
  ];
  let last;
  for (const args of tries) {
    try { return await run(N8N_CLI, args); } catch (e) { last = e; }
  }
  throw last || new Error('n8n export failed');
}
async function n8nImportFrom(inFile, overwrite = false) {
  const extra = overwrite ? ['--overwrite'] : [];
  const tries = [
    ['import:workflow', `--input=${inFile}`, ...extra],
    ['import:workflows', `--input=${inFile}`, ...extra],
  ];
  let last;
  for (const args of tries) {
    try { return await run(N8N_CLI, args); } catch (e) { last = e; }
  }
  throw last || new Error('n8n import failed');
}

// -------- App --------
const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '25mb' }));
app.use(auth);
app.use(express.static(path.join(__dirname, 'public')));

app.get('/health', (req, res) => res.json({ ok: true }));

app.get('/api/env', (req, res) => {
  const { lines } = readEnvFile();
  const items = [];
  for (const l of lines) if (l.type === 'kv') items.push({ key: l.key, value: l.value });
  res.json({ items });
});

app.post('/api/env', (req, res) => {
  let { key, value } = req.body || {};
  if (!key || typeof key !== 'string' || !KEY_RE.test(key)) return res.status(400).json({ error: 'Invalid key.' });
  if (typeof value !== 'string') value = String(value ?? '');
  writeEnvFile((ctx) => {
    for (const l of ctx.lines) {
      if (l.type === 'kv' && l.key === key) { l.value = value; return; }
    }
    if (ctx.lines.length && ctx.lines[ctx.lines.length - 1].type !== 'blank') ctx.lines.push({ type: 'blank', raw: '' });
    ctx.lines.push({ type: 'kv', key, value });
  });
  res.json({ ok: true });
});

app.put('/api/env/:key', (req, res) => {
  const oldKey = req.params.key;
  let { key, value } = req.body || {};
  if (!key || typeof key !== 'string' || !KEY_RE.test(key)) return res.status(400).json({ error: 'Invalid key.' });
  if (typeof value !== 'string') value = String(value ?? '');
  let found = false;
  writeEnvFile((ctx) => {
    for (const l of ctx.lines) {
      if (l.type === 'kv' && l.key === oldKey) { l.key = key; l.value = value; found = true; break; }
    }
    if (!found) {
      if (ctx.lines.length && ctx.lines[ctx.lines.length - 1].type !== 'blank') ctx.lines.push({ type: 'blank', raw: '' });
      ctx.lines.push({ type: 'kv', key, value });
    }
  });
  res.json({ ok: true, upsert: !found });
});

app.delete('/api/env/:key', (req, res) => {
  const delKey = req.params.key;
  let removed = false;
  writeEnvFile((ctx) => {
    const out = [];
    for (const l of ctx.lines) {
      if (l.type === 'kv' && l.key === delKey) { removed = true; continue; }
      out.push(l);
    }
    ctx.lines = out;
  });
  res.json({ ok: true, removed });
});

// Restart rolling: reload satu per satu, lanjut walau ada yang gagal.
app.post('/api/restart', (req, res) => {
  res.status(202).json({ ok: true, message: 'Rolling reload started' });
  setTimeout(async () => {
    const overlay = buildEnvOverlayFromDotenv();
    const envMerged = { ...process.env, ...overlay };
    const errors = [];
    for (const name of activeProcessNames()) {
      try {
        await run(PM2_BIN, ['reload', name, '--update-env'], { env: envMerged });
        console.log(`[restart] reloaded ${name}`);
      } catch (e) {
        errors.push(`${name}: ${e.message}`);
        console.error(`[restart] ${name} failed:`, e.message);
      }
    }
    if (errors.length) console.error('[restart] selesai dengan error:', errors.join(' | '));
  }, 200);
});

// ===== n8n Workflows Backup & Restore =====
app.get('/api/workflows/backup', async (req, res) => {
  try {
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const outFile = path.join(BACKUP_DIR, `n8n-workflows-${ts}.json`);
    await n8nExportAll(outFile);
    const stat = fs.statSync(outFile);
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Content-Disposition', `attachment; filename="${path.basename(outFile)}"`);
    res.setHeader('Content-Length', stat.size);
    fs.createReadStream(outFile).pipe(res);
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

app.post('/api/workflows/restore', async (req, res) => {
  try {
    const overwrite = String(req.query.overwrite || 'false') === 'true';
    const content = (req.body && (req.body.content || req.body.data)) || '';
    if (!content || typeof content !== 'string') {
      return res.status(400).json({ ok: false, error: 'Body must include "content" as JSON string' });
    }
    const tmp = path.join(BACKUP_DIR, `restore-${Date.now()}.json`);
    fs.writeFileSync(tmp, content, 'utf8');
    await n8nImportFrom(tmp, overwrite);
    res.json({ ok: true, restored: true, overwrite });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Backup .env
app.get('/api/env/download', (req, res) => {
  try {
    const buf = fs.readFileSync(DOTENV_PATH);
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Content-Disposition', 'attachment; filename=".env.backup"');
    res.send(buf);
  } catch {
    res.status(404).send('No .env found');
  }
});

// UI (fallback SPA) — middleware agar kompatibel Express 4 maupun 5
app.use((req, res, next) => {
  if (req.method !== 'GET' || req.path.startsWith('/api/')) return next();
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 404 untuk sisanya
app.use((req, res) => res.status(404).json({ ok: false, error: 'Not found' }));

app.listen(APP_PORT, () => console.log(`[vars-ui] on :${APP_PORT}`));
