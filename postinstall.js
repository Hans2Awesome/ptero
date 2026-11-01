#!/usr/bin/env node
// postinstall.js — download binari user-space & render config.
// Semua kegagalan ditangkap: `npm install` tidak boleh gagal karena langkah opsional ini,
// karena panel menjalankan `npm install` di setiap start.

const fs = require('fs');
const path = require('path');
const https = require('https');
const cp = require('child_process');
const { parseDotenv } = require('./env-export');

function log(...a) { console.log('[postinstall]', ...a); }
function warn(...a) { console.log('[postinstall][WARN]', ...a); }

const ROOT = __dirname;

// .env dimuat di main() setelah ensureEnvFiles(), supaya nilai hasil generate ikut terpakai.
function loadEnvIntoProcess(envPath) {
  try {
    const parsed = parseDotenv(fs.readFileSync(envPath, 'utf8'));
    for (const [k, v] of Object.entries(parsed)) {
      if (process.env[k] === undefined) process.env[k] = v;
    }
    return true;
  } catch {
    return false;
  }
}

function randomSecret(bytes = 24) {
  return require('crypto').randomBytes(bytes).toString('base64url');
}

// Ganti satu baris `KEY=...` di teks .env. Mengembalikan teks baru.
function setEnvLine(text, key, value) {
  const re = new RegExp(`^${key}=.*$`, 'm');
  if (re.test(text)) return text.replace(re, `${key}=${value}`);
  return `${text.replace(/\n*$/, '')}\n${key}=${value}\n`;
}

// Buat .env dari .env.example bila belum ada, dengan secret acak.
// Tanpa ini, clone repo akan jalan dengan kredensial kosong/lemah.
function ensureEnvFiles() {
  const pairs = [
    {
      dir: ROOT,
      label: 'root .env',
      secrets: () => {
        const redisPass = randomSecret(18);
        const varuiPass = randomSecret(18);
        return {
          N8N_ENCRYPTION_KEY: randomSecret(24),
          REDIS_PASSWORD: redisPass,
          QUEUE_BULL_REDIS_PASSWORD: redisPass,
          VARUI_PASS: varuiPass,
          APP_BASIC_AUTH: `admin:${randomSecret(18)}`,
        };
      },
      announce: (generated) => {
        log('Kredensial dibuat untuk vars-ui — simpan sekarang:');
        log(`  VARUI_USER=${generated.__user}  VARUI_PASS=${generated.VARUI_PASS}`);
      },
    },
    {
      dir: path.join(ROOT, 'vendor', 'finapi'),
      label: 'vendor/finapi/.env',
      secrets: () => ({ SECRET_KEY: randomSecret(48) }),
    },
  ];

  for (const { dir, label, secrets, announce } of pairs) {
    const envPath = path.join(dir, '.env');
    const examplePath = path.join(dir, '.env.example');
    if (fs.existsSync(envPath)) continue;
    if (!fs.existsSync(examplePath)) {
      warn(`${label} tidak ada dan ${path.basename(examplePath)} juga tidak ada.`);
      continue;
    }

    let text = fs.readFileSync(examplePath, 'utf8');
    const generated = secrets();
    for (const [k, v] of Object.entries(generated)) text = setEnvLine(text, k, v);

    // User vars-ui diambil dari contoh, dipakai untuk pesan.
    generated.__user = (text.match(/^VARUI_USER=(.*)$/m) || [, ''])[1].trim();

    fs.writeFileSync(envPath, text, { encoding: 'utf8', mode: 0o600 });
    log(`${label} dibuat dari ${path.basename(examplePath)} dengan secret acak.`);
    if (announce) announce(generated);
  }
}
const BIN_DIR = path.join(ROOT, 'bin');

// ============================================================
// n8n — dipasang kondisional, karena npm install tidak bisa membaca .env.
// ENABLE_N8N=0 → n8n tidak dipasang sama sekali.
// ENABLE_N8N=1 → versi dipilih sesuai Node yang tersedia.
// ============================================================
const N8N_VERSIONS = {
  node24: '2.45.6', // engines: >=24.0.0
  node22: '2.35.7', // engines: >=22.22
};

function n8nVersionFor(nodeMajor) {
  if (nodeMajor >= 24) return N8N_VERSIONS.node24;
  if (nodeMajor >= 22) return N8N_VERSIONS.node22;
  return null;
}

function setupN8n() {
  const runApps = String(process.env.RUN_APPS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const disabled = process.env.ENABLE_N8N === '0'
    || (runApps.length > 0 && !runApps.includes('n8n'));

  const bin = path.join(ROOT, 'node_modules', '.bin', 'n8n');

  if (disabled) {
    if (fs.existsSync(bin)) {
      log('n8n disabled (ENABLE_N8N=0) — package lama dibiarkan, tidak dihapus.');
    } else {
      log('n8n disabled (ENABLE_N8N=0) — tidak dipasang.');
    }
    return;
  }

  if (fs.existsSync(bin)) {
    log('n8n sudah terpasang di node_modules.');
    return;
  }

  const major = parseInt(process.versions.node.split('.')[0], 10);
  const version = n8nVersionFor(major);
  if (!version) {
    warn(`Node v${process.versions.node} terlalu lama untuk n8n (butuh >=22). Set ENABLE_N8N=0.`);
    return;
  }

  log(`Memasang n8n@${version} (Node v${process.versions.node})…`);
  cp.execFileSync(
    process.env.NPM_BIN || 'npm',
    ['install', `n8n@${version}`, '--no-save', '--no-audit', '--no-fund'],
    { cwd: ROOT, stdio: 'inherit', timeout: 1200000 },
  );
  log('n8n siap.');
}

function downloadFollow(url, out, redirects = 0) {
  return new Promise((resolve, reject) => {
    if (redirects > 8) return reject(new Error('too many redirects'));
    const req = https.get(url, { headers: { 'User-Agent': 'node' } }, (res) => {
      const { statusCode, headers } = res;
      if (statusCode >= 300 && statusCode < 400 && headers.location) {
        res.resume();
        return downloadFollow(new URL(headers.location, url).toString(), out, redirects + 1)
          .then(resolve, reject);
      }
      if (statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${statusCode} ${url}`));
      }
      const tmp = `${out}.part`;
      const file = fs.createWriteStream(tmp);
      res.pipe(file);
      file.on('finish', () => {
        file.close(() => {
          try { fs.renameSync(tmp, out); } catch (e) { return reject(e); }
          resolve();
        });
      });
      file.on('error', (e) => { try { fs.unlinkSync(tmp); } catch {} reject(e); });
    });
    req.on('error', reject);
    req.setTimeout(60000, () => req.destroy(new Error('timeout')));
  });
}

function isELF(p) {
  try {
    const fd = fs.openSync(p, 'r');
    const b = Buffer.alloc(4);
    fs.readSync(fd, b, 0, 4, 0);
    fs.closeSync(fd);
    return b[0] === 0x7f && b[1] === 0x45 && b[2] === 0x4c && b[3] === 0x46;
  } catch { return false; }
}

function existsNonEmpty(p) {
  try { return fs.statSync(p).size > 0; } catch { return false; }
}

const ARCH = process.arch; // 'x64' | 'arm64'
const IS_AMD64 = ARCH === 'x64' || ARCH === 'amd64';

// ============================================================
// Redis / Valkey
// ============================================================
function pickRedisUrl() {
  const explicit = (process.env.REDIS_BINARY_URL || '').trim();
  if (explicit) return explicit;
  if (IS_AMD64) return (process.env.REDIS_BINARY_URL_AMD64 || '').trim();
  if (ARCH === 'arm64') return (process.env.REDIS_BINARY_URL_ARM64 || '').trim();
  return '';
}

async function setupRedis() {
  if (process.env.ENABLE_REDIS !== '1') {
    log('Redis disabled (ENABLE_REDIS != 1).');
    return;
  }

  fs.mkdirSync(BIN_DIR, { recursive: true });
  const outBin = path.join(BIN_DIR, 'redis-server');

  // Buang file yang bukan ELF (mis. hasil ekstrak arsip yang salah)
  if (fs.existsSync(outBin) && !isELF(outBin)) {
    try { fs.unlinkSync(outBin); } catch {}
  }

  if (!fs.existsSync(outBin)) {
    const url = pickRedisUrl();
    if (!url) {
      warn(`Tidak ada URL redis-server untuk arch ${ARCH}. Set REDIS_BINARY_URL_${ARCH.toUpperCase()}.`);
    } else {
      log('Fetching redis-server from', url);
      const tmpTar = path.join(BIN_DIR, 'redis-download');
      const tmpDir = path.join(BIN_DIR, '.extract-redis');
      await downloadFollow(url, tmpTar);

      if (/\.(tar\.gz|tgz)$/i.test(url)) {
        fs.rmSync(tmpDir, { recursive: true, force: true });
        fs.mkdirSync(tmpDir, { recursive: true });
        try {
          cp.execFileSync('tar', ['-xzf', tmpTar, '-C', tmpDir], { stdio: 'inherit' });
        } catch (e) {
          fs.rmSync(tmpTar, { force: true });
          throw new Error('tar extract failed (pastikan `tar` tersedia di image)');
        }
        fs.rmSync(tmpTar, { force: true });

        const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
          const p = path.join(dir, d.name);
          return d.isDirectory() ? walk(p) : [p];
        });
        const files = walk(tmpDir);
        const cand = files.find((p) => /(^|\/)(valkey-server|redis-server)$/.test(p))
          || files.filter((p) => isELF(p)).sort((a, b) => fs.statSync(b).size - fs.statSync(a).size)[0];
        if (!cand) throw new Error('Binary not found inside archive');
        fs.copyFileSync(cand, outBin);
        fs.chmodSync(outBin, 0o755);
        fs.rmSync(tmpDir, { recursive: true, force: true });
      } else {
        fs.renameSync(tmpTar, outBin);
        fs.chmodSync(outBin, 0o755);
      }
    }
  }

  if (existsNonEmpty(outBin) && !isELF(outBin)) {
    warn('./bin/redis-server bukan ELF binary. Hapus file dan perbaiki URL.');
  } else if (existsNonEmpty(outBin)) {
    log('redis-server ready:', outBin);
  }

  // ---- render redis.conf ----
  const confDir = path.join(ROOT, 'redis');
  const dataDirRel = process.env.REDIS_DATA_DIR || 'redis/data';
  const dataDir = path.join(ROOT, dataDirRel);
  fs.mkdirSync(confDir, { recursive: true });
  fs.mkdirSync(dataDir, { recursive: true });

  const pw = process.env.REDIS_PASSWORD || '';
  const port = process.env.REDIS_PORT || '6379';
  const bind = process.env.REDIS_BIND || '127.0.0.1';
  const aof = process.env.REDIS_APPENDONLY || 'yes';
  const maxMemMB = parseInt(process.env.REDIS_MAXMEMORY_MB || '512', 10);
  const logfile = (process.env.REDIS_LOGFILE || '').trim();
  const saveRaw = (process.env.REDIS_SAVE || '900 1 300 10 60 10000').trim().split(/\s+/);

  let saveLines = '';
  for (let i = 0; i + 1 < saveRaw.length; i += 2) {
    const a = saveRaw[i];
    const b = saveRaw[i + 1];
    if (a && b) saveLines += `save ${a} ${b}\n`;
  }

  // CATATAN: BullMQ (queue mode n8n) mensyaratkan maxmemory-policy `noeviction`.
  // `allkeys-lru` bisa menghapus job dari antrean sebelum dieksekusi.
  const conf = `# Auto-generated by postinstall.js — DO NOT EDIT
port ${port}
bind ${bind}
protected-mode yes
daemonize no
dir ${dataDirRel}
${saveLines}timeout 0
tcp-keepalive 60
logfile ${logfile || '""'}
databases 16
maxmemory ${maxMemMB}mb
maxmemory-policy noeviction
appendonly ${aof}
appendfsync everysec
${pw ? `requirepass ${pw}\n` : ''}pidfile ""
`;
  fs.writeFileSync(path.join(confDir, 'redis.conf'), conf, 'utf8');
  log('Wrote redis/redis.conf (maxmemory-policy noeviction)');
}

// ============================================================
// cloudflared
// ============================================================
async function setupCloudflared() {
  const runApps = String(process.env.RUN_APPS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const skip = process.env.ENABLE_TUNNEL === '0'
    || (runApps.length > 0 && !runApps.includes('cf-tunnel'));
  if (skip) {
    log('Skip cloudflared (disabled by env).');
    return;
  }
  if (!process.env.CLOUDFLARE_TOKEN && !process.env.CLOUDFLARE_TOKEN_VARS) {
    log('Skip cloudflared (no CLOUDFLARE_TOKEN).');
    return;
  }

  fs.mkdirSync(BIN_DIR, { recursive: true });
  const out = path.join(BIN_DIR, 'cloudflared');
  if (existsNonEmpty(out)) return;

  const name = ARCH === 'arm64' ? 'cloudflared-linux-arm64' : 'cloudflared-linux-amd64';
  log('Downloading cloudflared…');
  await downloadFollow(`https://github.com/cloudflare/cloudflared/releases/latest/download/${name}`, out);
  fs.chmodSync(out, 0o755);
  log('cloudflared ready:', out);
}

// ============================================================
// GOWA (go-whatsapp-web-multidevice)
// ============================================================
function getJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'node', Accept: 'application/vnd.github+json' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return getJson(new URL(res.headers.location, url).toString()).then(resolve, reject);
      }
      let data = '';
      res.on('data', (d) => (data += d));
      res.on('end', () => {
        if (res.statusCode !== 200) return reject(new Error(`HTTP ${res.statusCode} ${url}`));
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function setupGowa() {
  const runApps = String(process.env.RUN_APPS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const skip = process.env.ENABLE_GOWA === '0'
    || process.env.SKIP_GOWA === '1'
    || (runApps.length > 0 && !runApps.includes('gowa'));

  if (skip) {
    log('Skip GOWA (disabled by env).');
    return;
  }
  if (!IS_AMD64) {
    warn(`GOWA hanya tersedia untuk linux amd64, arch sekarang: ${ARCH}. Set SKIP_GOWA=1 atau sediakan ./bin/gowa manual.`);
    return;
  }

  fs.mkdirSync(BIN_DIR, { recursive: true });
  const out = path.join(BIN_DIR, 'gowa');
  if (existsNonEmpty(out)) return;

  log('Resolving GOWA latest asset…');
  const rel = await getJson('https://api.github.com/repos/aldinokemal/go-whatsapp-web-multidevice/releases/latest');
  const assets = rel.assets || [];

  const pick = assets.find((a) => {
    const n = (a.name || '').toLowerCase();
    return n.includes('linux') && (n.includes('amd64') || n.includes('x86_64')) && n.endsWith('.zip');
  }) || assets.find((a) => {
    const n = (a.name || '').toLowerCase();
    return n.includes('linux') && (n.includes('amd64') || n.includes('x86_64'));
  });
  if (!pick) throw new Error('No linux amd64 asset found in latest release');

  const tmp = path.join(BIN_DIR, pick.name);
  log('Downloading GOWA:', pick.name);
  await downloadFollow(pick.browser_download_url, tmp);

  if (tmp.toLowerCase().endsWith('.zip')) {
    // adm-zip dipakai supaya tidak butuh `unzip` di image
    const AdmZip = require('adm-zip');
    const zip = new AdmZip(tmp);
    let entry = zip.getEntries().find((e) => !e.isDirectory && /(^|\/)whatsapp$/.test(e.entryName));
    if (!entry) {
      entry = zip.getEntries().filter((e) => !e.isDirectory).sort((a, b) => b.header.size - a.header.size)[0];
    }
    if (!entry) throw new Error('Binary not found inside ZIP');
    fs.writeFileSync(out, entry.getData());
    fs.rmSync(tmp, { force: true });
  } else {
    fs.renameSync(tmp, out);
  }
  fs.chmodSync(out, 0o755);
  log('GOWA ready:', out);
}

// ============================================================
// FinAPI — FastAPI backend (Python) untuk AppFinanceIndv
// ============================================================
const FINAPI_DIR = path.join(ROOT, 'vendor', 'finapi');
const FINAPI_REQ = path.join(FINAPI_DIR, 'backend', 'requirements.txt');
const FINAPI_VENV = path.join(BIN_DIR, 'finapi-venv');
const FINAPI_MARKER = path.join(FINAPI_VENV, '.requirements.sha256');

function run(bin, args, opts = {}) {
  return cp.execFileSync(bin, args, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 900000,
    ...opts,
  });
}

function tryRun(bin, args, opts = {}) {
  try {
    return { ok: true, out: run(bin, args, opts) };
  } catch (e) {
    return { ok: false, out: `${(e.stdout || '')}${(e.stderr || '')}${e.message}` };
  }
}

// Python 3.11+ dari image, kalau ada.
function systemPython() {
  for (const bin of ['python3', 'python']) {
    const r = tryRun(bin, ['-c', 'import sys; print(sys.version_info >= (3, 11))']);
    if (r.ok && r.out.trim() === 'True') return bin;
  }
  return null;
}

// Deteksi libc runtime supaya aset python-build-standalone cocok.
function libcKind() {
  try {
    const report = process.report.getReport();
    return report.header.glibcVersionRuntime ? 'gnu' : 'musl';
  } catch {
    return 'gnu';
  }
}

async function downloadPortablePython() {
  const target = path.join(BIN_DIR, 'python-build', 'bin', 'python3');
  if (existsNonEmpty(target)) return target;

  const arch = ARCH === 'arm64' ? 'aarch64' : 'x86_64';
  const libc = libcKind();
  log(`Menyiapkan Python portabel (${arch}, ${libc})…`);

  const rel = await getJson('https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest');
  const assets = rel.assets || [];
  const want = new RegExp(`^cpython-3\\.13\\..+-${arch}-unknown-linux-${libc}-install_only\\.tar\\.gz$`);
  const pick = assets.find((a) => want.test(a.name || ''));
  if (!pick) throw new Error(`Aset python-build-standalone tidak ditemukan (${arch}/${libc})`);

  const tgz = path.join(BIN_DIR, 'python-build.tar.gz');
  const tmpDir = path.join(BIN_DIR, '.extract-python');
  await downloadFollow(pick.browser_download_url, tgz);

  fs.rmSync(tmpDir, { recursive: true, force: true });
  fs.mkdirSync(tmpDir, { recursive: true });
  try {
    cp.execFileSync('tar', ['-xzf', tgz, '-C', tmpDir], { stdio: 'inherit' });
  } finally {
    fs.rmSync(tgz, { force: true });
  }

  fs.rmSync(path.join(BIN_DIR, 'python-build'), { recursive: true, force: true });
  fs.renameSync(path.join(tmpDir, 'python'), path.join(BIN_DIR, 'python-build'));
  fs.rmSync(tmpDir, { recursive: true, force: true });

  if (!existsNonEmpty(target)) throw new Error('python3 tidak ditemukan setelah ekstrak');
  log('Python portabel siap:', target);
  return target;
}

function venvWorks() {
  const r = tryRun(path.join(FINAPI_VENV, 'bin', 'python'), ['-c', 'import sys; print(sys.version_info >= (3, 11))']);
  return r.ok && r.out.trim() === 'True';
}

function buildVenv(py) {
  fs.rmSync(FINAPI_VENV, { recursive: true, force: true });
  log('Membuat venv finapi…');
  cp.execFileSync(py, ['-m', 'venv', FINAPI_VENV], { stdio: 'inherit', timeout: 300000 });
}

function installFinapiDeps() {
  const hash = require('crypto')
    .createHash('sha256')
    .update(fs.readFileSync(FINAPI_REQ))
    .digest('hex');

  if (fs.existsSync(FINAPI_MARKER) && fs.readFileSync(FINAPI_MARKER, 'utf8').trim() === hash) {
    log('finapi: dependencies sudah terpasang.');
    return;
  }

  log('finapi: memasang dependencies (bisa beberapa menit)…');
  cp.execFileSync(
    path.join(FINAPI_VENV, 'bin', 'python'),
    ['-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '-r', FINAPI_REQ],
    { stdio: 'inherit', timeout: 900000 },
  );
  fs.writeFileSync(FINAPI_MARKER, `${hash}\n`, 'utf8');
  log('finapi: dependencies siap.');
}

async function setupFinapi() {
  const runApps = String(process.env.RUN_APPS || '').split(',').map((s) => s.trim()).filter(Boolean);
  const skip = process.env.ENABLE_FINAPI === '0'
    || (runApps.length > 0 && !runApps.includes('finapi'));

  if (skip) {
    log('Skip FinAPI (disabled by env).');
    return;
  }
  if (!fs.existsSync(FINAPI_REQ)) {
    warn('Skip FinAPI: vendor/finapi/backend/requirements.txt tidak ada.');
    return;
  }

  // Kalau venv sudah ada dan deps-nya cocok, selesai.
  if (venvWorks()) {
    installFinapiDeps();
    return;
  }

  const candidates = [];
  const sys = systemPython();
  if (sys) candidates.push(sys);

  for (let attempt = 0; attempt < 2; attempt++) {
    let py = candidates[attempt] || null;
    if (!py) py = await downloadPortablePython();

    try {
      buildVenv(py);
      installFinapiDeps();
      log(`finapi: siap memakai ${py}`);
      return;
    } catch (e) {
      // Python sistem sering tidak bisa memakai wheel glibc (mis. image Alpine).
      warn(`finapi: gagal dengan ${py} (${e && e.message ? e.message.split('\n')[0] : e}). Coba Python portabel.`);
      fs.rmSync(FINAPI_MARKER, { force: true });
    }
  }

  throw new Error('venv finapi tidak bisa disiapkan');
}

// ============================================================
(async () => {
  try {
    ensureEnvFiles();
  } catch (e) {
    warn(`ensureEnvFiles gagal: ${e && e.message ? e.message : e}`);
  }
  loadEnvIntoProcess(path.join(ROOT, '.env'));
  loadEnvIntoProcess(path.join(ROOT, 'vendor', 'finapi', '.env'));

  const steps = [
    ['n8n', setupN8n],
    ['redis', setupRedis],
    ['cloudflared', setupCloudflared],
    ['gowa', setupGowa],
    ['finapi', setupFinapi],
  ];
  for (const [name, fn] of steps) {
    try {
      await fn();
    } catch (e) {
      warn(`${name} setup failed: ${e && e.message ? e.message : e}`);
    }
  }
  log('done');
})();
