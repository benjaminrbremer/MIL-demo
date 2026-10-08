/**
 * REQ-108: browser code talks only to the web server's /api routes.
 *
 * A static check of the files in client/: the browser must never know the
 * device's address, its /v1 API, or the token header. This can't prove
 * every possible URL, but it catches the realistic mistakes.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { WEB_DIR } from './helpers.js';

const CLIENT_DIR = join(WEB_DIR, 'client');

/** Every file under client/, as [relative path, text]. */
async function clientFiles() {
  const entries = await readdir(CLIENT_DIR, { recursive: true, withFileTypes: true });
  const files = entries.filter((entry) => entry.isFile());
  return Promise.all(
    files.map(async (entry) => {
      const path = join(entry.parentPath, entry.name);
      return [path.slice(CLIENT_DIR.length + 1), await readFile(path, 'utf8')];
    }),
  );
}

test('req_108: no client file mentions the device API, token, or address', async () => {
  for (const [name, text] of await clientFiles()) {
    assert.doesNotMatch(text, /x-device-token/i, `${name} mentions the token header`);
    assert.doesNotMatch(text, /\/v1\//, `${name} uses the device's /v1 API`);
    assert.doesNotMatch(text, /:8000\b/, `${name} names the device port`);
    assert.doesNotMatch(text, /\b100\.\d+\.\d+\.\d+\b/, `${name} names a Tailscale address`);
    assert.doesNotMatch(text, /mil-device/, `${name} names the device host`);
  }
});

test('req_108: only api.js calls fetch, and every API path starts with /api/', async () => {
  for (const [name, text] of await clientFiles()) {
    if (!name.endsWith('.js')) continue;
    if (name !== join('js', 'api.js')) {
      assert.doesNotMatch(text, /\bfetch\(/, `${name} calls fetch directly`);
    }
    for (const [, path] of text.matchAll(/getJson\(\s*["'`]([^"'`]*)/g)) {
      assert.ok(path.startsWith('/api/'), `${name} requests ${path}`);
    }
  }
});

test('req_108: the viewer opens slides only through /api/', async () => {
  // OpenSeadragon makes its own requests, starting from the URL given to
  // open(); its tile URLs are derived from that one.
  for (const [name, text] of await clientFiles()) {
    if (!name.endsWith('.js')) continue;
    for (const [, url] of text.matchAll(/\.open\(\s*["'`]([^"'`]*)/g)) {
      assert.ok(url.startsWith('/api/'), `${name} opens ${url}`);
    }
  }
});
