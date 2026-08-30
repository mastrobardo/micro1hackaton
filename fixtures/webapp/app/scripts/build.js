'use strict';

// Minimal build: syntax-check every src/**/*.js, then stage src/ + public/ into dist/.
// No bundler — the fixture ships plain files. Exits non-zero on any parse error.

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const DIST = path.join(ROOT, 'dist');

function walk(dir, filter) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full, filter));
    else if (filter(full)) out.push(full);
  }
  return out;
}

const jsFiles = walk(path.join(ROOT, 'src'), (f) => f.endsWith('.js'));
for (const f of jsFiles) {
  execFileSync(process.execPath, ['--check', f], { stdio: 'inherit' });
}
console.log(`checked ${jsFiles.length} source files`);

fs.rmSync(DIST, { recursive: true, force: true });
for (const sub of ['src', 'public']) {
  fs.cpSync(path.join(ROOT, sub), path.join(DIST, sub), { recursive: true });
}
console.log(`build ok -> ${path.relative(process.cwd(), DIST)}`);
