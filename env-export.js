#!/usr/bin/env node
// env-export.js — parser .env kecil, dipakai dua tempat:
//   1) dijalankan langsung: cetak `export KEY='value'` untuk di-eval oleh /bin/sh (start.sh)
//   2) di-require: module.exports.parseDotenv(raw) → objek (postinstall.js)
// Ditulis sendiri supaya perilakunya konsisten dan tidak butuh dependensi.
const fs = require('fs');
const path = require('path');

function parseDotenv(raw) {
  const out = {};
  for (const rawLine of String(raw).split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const m = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!m) continue;
    const key = m[1];
    let value = m[2];

    const quote = value[0];
    if (quote === '"' || quote === "'") {
      const end = value.indexOf(quote, 1);
      if (end > 0) {
        value = value.slice(1, end);
        if (quote === '"') {
          value = value
            .replace(/\\n/g, '\n')
            .replace(/\\r/g, '\r')
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, '\\');
        }
        out[key] = value;
        continue;
      }
    }
    // Nilai tanpa kutip: buang komentar inline hanya jika didahului spasi.
    out[key] = value.replace(/\s+#.*$/, '').trim();
  }
  return out;
}

function shQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

module.exports = { parseDotenv, shQuote };

if (require.main === module) {
  let raw = '';
  try {
    raw = fs.readFileSync(path.resolve(process.cwd(), '.env'), 'utf8');
  } catch {
    process.exit(0);
  }

  // Pipe bisa ditutup lebih awal (mis. `| head`); jangan crash.
  process.stdout.on('error', (e) => {
    if (e.code === 'EPIPE') process.exit(0);
    throw e;
  });

  for (const [key, value] of Object.entries(parseDotenv(raw))) {
    process.stdout.write(`export ${key}=${shQuote(value)}\n`);
  }
}
